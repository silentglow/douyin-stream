from __future__ import annotations
"""转写运行记录仓库 - transcribe_runs 表的所有操作

每个 run 代表一次对某个视频、在某个通义账号上的完整转写尝试。
stage 字段记录当前进行到哪一阶段，record_id / gen_record_id 在上传成功后持久化，
使得上传后任意环节失败时，下一次重试可以从 uploaded 阶段恢复，不再重传文件。
"""

import sqlite3
import uuid
from datetime import datetime
from typing import Any, Optional, Union

from media_tools.db.core import get_db_connection
from media_tools.logger import get_logger

logger = get_logger(__name__)


# 上传完成、且尚未落盘的中间阶段 —— 这些阶段的 run 可以在下一次尝试时被复用
RESUMABLE_STAGES = ("uploaded", "transcribing", "exporting", "downloading")

TERMINAL_STAGES = ("saved", "failed")

NON_RESUMABLE_ERROR_TYPES = ("service_unavailable", "unsupported_format")


class TranscribeRunRepository:
    """transcribe_runs 表的访问层"""

    @staticmethod
    def create(
        *,
        asset_id: str,
        video_path: str,
        account_id: str,
        task_id: Optional[str] = None,
    ) -> str:
        run_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO transcribe_runs
                    (run_id, asset_id, video_path, account_id, task_id, stage, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)
                """,
                (run_id, asset_id, video_path, account_id, task_id, now, now),
            )
        return run_id

    @staticmethod
    def find_resumable(asset_id: str, account_id: str) -> Optional[dict[str, Any]]:
        """查找该 asset 在该 account 上可以续做的 run。

        命中条件：gen_record_id 已持久化，且：
          - stage 属于 RESUMABLE_STAGES（上传后的中间态），或
          - stage='failed' 但 error_stage 落在 RESUMABLE_STAGES 中
            （上传后挂的失败 run，gen_record_id 还在 Qwen 端有效，可以复用）
        终态 'saved' 不返回（已成功，无需续做）。
        不可续传的错误类型（如 service_unavailable）不返回，因为云端记录已是终态。
        """
        resumable_placeholders = ",".join(["?"] * len(RESUMABLE_STAGES))
        non_resumable_placeholders = ",".join(["?"] * len(NON_RESUMABLE_ERROR_TYPES))
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"""
                SELECT run_id, stage, record_id, gen_record_id, batch_id, export_task_id, export_url
                FROM transcribe_runs
                WHERE asset_id = ? AND account_id = ?
                  AND gen_record_id IS NOT NULL AND gen_record_id != ''
                  AND (
                    stage IN ({resumable_placeholders})
                    OR (stage = 'failed' AND error_stage IN ({resumable_placeholders})
                        AND (error_type IS NULL OR error_type = '' OR error_type NOT IN ({non_resumable_placeholders})))
                  )
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (asset_id, account_id, *RESUMABLE_STAGES, *RESUMABLE_STAGES, *NON_RESUMABLE_ERROR_TYPES),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def update_stage(
        run_id: str,
        stage: str,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        """推进 stage，并可选地写入 record_id / gen_record_id / batch_id 等附加字段。"""
        extra = extra or {}
        allowed = {"record_id", "gen_record_id", "batch_id", "export_task_id", "export_url", "transcript_path"}
        set_clauses = ["stage = ?", "updated_at = ?"]
        params: list[Any] = [stage, datetime.now().isoformat()]
        for key in allowed:
            if key in extra and extra[key] is not None:
                set_clauses.append(f"{key} = ?")
                params.append(str(extra[key]))
        params.append(run_id)
        with get_db_connection() as conn:
            conn.execute(
                f"UPDATE transcribe_runs SET {', '.join(set_clauses)} WHERE run_id = ?",
                params,
            )

    @staticmethod
    def mark_saved(run_id: str, transcript_path: str) -> None:
        with get_db_connection() as conn:
            conn.execute(
                """
                UPDATE transcribe_runs
                SET stage = 'saved', transcript_path = ?, updated_at = ?, last_error = NULL, error_stage = NULL, error_type = NULL
                WHERE run_id = ?
                """,
                (transcript_path, datetime.now().isoformat(), run_id),
            )

    @staticmethod
    def mark_failed(
        run_id: str,
        error_stage: str,
        error_type: str,
        last_error: str,
    ) -> None:
        with get_db_connection() as conn:
            conn.execute(
                """
                UPDATE transcribe_runs
                SET stage = 'failed', error_stage = ?, error_type = ?, last_error = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (error_stage, error_type, last_error[:2000], datetime.now().isoformat(), run_id),
            )

    @staticmethod
    def get(run_id: str) -> Optional[dict[str, Any]]:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM transcribe_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def find_saved_for_asset(asset_id: str) -> Optional[dict[str, Any]]:
        """查询某个 asset 是否已经有成功落盘的 run。用于跨任务去重。

        仅返回 transcript_path 非空的有效记录，避免空文件/损坏文件被判定为成功。
        """
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT run_id, transcript_path, account_id
                FROM transcribe_runs
                WHERE asset_id = ? AND stage = 'saved'
                  AND transcript_path IS NOT NULL AND transcript_path != ''
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (asset_id,),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def aggregate_failures(days: int = 7) -> list[dict[str, Any]]:
        """统计最近 N 天内 stage='failed' 的 run，按 (error_type, error_stage) 分桶。

        返回示例:
            [
              {"error_type": "quota", "error_stage": "transcribing", "count": 12,
               "last_seen": "2026-05-04T10:23:11", "sample_error": "..."},
              {"error_type": "network", "error_stage": "uploading", "count": 5, ...},
            ]

        排序：count 倒序，再按 last_seen 倒序。
        sample_error 取桶内最新一条的 last_error（截断到 200 字），便于在前端
        失败聚合表格里直接看到"长这样"的错误样本。
        """
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=max(1, days))).isoformat()
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT
                    COALESCE(error_type, 'unknown') AS error_type,
                    COALESCE(error_stage, 'unknown') AS error_stage,
                    COUNT(*) AS count,
                    MAX(updated_at) AS last_seen
                FROM transcribe_runs
                WHERE stage = 'failed'
                  AND updated_at >= ?
                GROUP BY error_type, error_stage
                ORDER BY count DESC, last_seen DESC
                """,
                (cutoff,),
            ).fetchall()
            buckets: list[dict[str, Any]] = []
            for r in rows:
                # 取该桶里最新的一条错误样本
                sample = conn.execute(
                    """
                    SELECT last_error FROM transcribe_runs
                    WHERE stage = 'failed'
                      AND COALESCE(error_type, 'unknown') = ?
                      AND COALESCE(error_stage, 'unknown') = ?
                      AND updated_at >= ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (r["error_type"], r["error_stage"], cutoff),
                ).fetchone()
                sample_error = (sample["last_error"] if sample else None) or ""
                buckets.append({
                    "error_type": r["error_type"],
                    "error_stage": r["error_stage"],
                    "count": int(r["count"]),
                    "last_seen": r["last_seen"],
                    "sample_error": sample_error[:200],
                })
        return buckets

    @staticmethod
    def find_failed_record_ids(asset_id: str, account_id: str = "") -> list[str]:
        """查找某个 asset 失败 run 的 record_id，用于云端清理。

        只返回 stage='failed' 且 record_id 非空的 run，
        排除已成功（saved）的 run。
        传入 account_id 时只返回该账号下的记录，避免跨账号 cookie 删除失败。
        """
        with get_db_connection() as conn:
            if account_id:
                rows = conn.execute(
                    """
                    SELECT DISTINCT record_id
                    FROM transcribe_runs
                    WHERE asset_id = ?
                      AND account_id = ?
                      AND stage = 'failed'
                      AND record_id IS NOT NULL
                      AND record_id != ''
                    """,
                    (asset_id, account_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT DISTINCT record_id
                    FROM transcribe_runs
                    WHERE asset_id = ?
                      AND stage = 'failed'
                      AND record_id IS NOT NULL
                      AND record_id != ''
                    """,
                    (asset_id,),
                ).fetchall()
        return [row[0] for row in rows if row[0]]

    @staticmethod
    def find_failed_record_ids_for_video(video_path: str, account_id: str = "") -> list[str]:
        """查找某个视频路径失败 run 的 record_id，用于云端清理。

        当 asset_id 不可用时，通过 video_path 回退查找。
        传入 account_id 时只返回该账号下的记录，避免跨账号 cookie 删除失败。
        """
        with get_db_connection() as conn:
            if account_id:
                rows = conn.execute(
                    """
                    SELECT DISTINCT record_id
                    FROM transcribe_runs
                    WHERE video_path = ?
                      AND account_id = ?
                      AND stage = 'failed'
                      AND record_id IS NOT NULL
                      AND record_id != ''
                    """,
                    (video_path, account_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT DISTINCT record_id
                    FROM transcribe_runs
                    WHERE video_path = ?
                      AND stage = 'failed'
                      AND record_id IS NOT NULL
                      AND record_id != ''
                    """,
                    (video_path,),
                ).fetchall()
        return [row[0] for row in rows if row[0]]

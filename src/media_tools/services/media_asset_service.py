from __future__ import annotations
"""media_assets 表的统一访问服务。

历史上 media_assets 由 4 处分别 INSERT/UPDATE（douyin downloader、本地上传、扫盘 worker、
transcript reconciler），导致失败状态从未被任何一处写入。本服务把"转写完成 / 转写失败 /
按状态发现待重试"等关键写入和查询集中起来，让 media_assets 真正成为业务真相源。

不强制其它写入点立即迁移；orchestrator 优先切到本服务，新功能（如 B 站入库、
retry-failed-assets API）直接基于本服务构建。
"""

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

from media_tools.store.db import get_db_connection, update_fts_for_asset
from media_tools.logger import get_logger

logger = get_logger(__name__)


_AWEME_ID_RE = re.compile(r"\d{15,}")


def _resolve_asset_id_from_video_path(video_path: Path) -> Optional[str]:
    """根据视频文件名启发式定位 asset_id。

    抖音 aweme 文件名带 15+ 位数字，命中即返回；本地上传等无 aweme 的视频返回 None，
    调用方需要走 video_path / title 的 LIKE 兜底匹配。
    """
    matches = _AWEME_ID_RE.findall(video_path.name)
    return matches[0] if matches else None


class MediaAssetService:
    """media_assets 表的写入与发现层"""

    # ---------- 解析 ----------

    @staticmethod
    def find_asset_id_for_video_path(video_path: Path) -> Optional[str]:
        """三段式 fallback 找出视频对应的 asset_id。

        1) 文件名带 15+ 位数字 -> 抖音 aweme
        2) DB 里按 video_path / title 模糊匹配
        3) 找不到返回 None（调用方应允许"无 asset_id 也能跑"）
        """
        guessed = _resolve_asset_id_from_video_path(video_path)
        if guessed:
            return guessed
        try:
            with get_db_connection() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT asset_id FROM media_assets
                    WHERE video_path LIKE ? OR title LIKE ?
                    ORDER BY update_time DESC
                    LIMIT 1
                    """,
                    (f"%{video_path.name}%", f"%{video_path.stem}%"),
                ).fetchone()
            return row["asset_id"] if row else None
        except sqlite3.Error as e:
            logger.warning(f"find_asset_id_for_video_path({video_path}) 失败: {e}")
            return None

    # ---------- 写入：下载入库 ----------

    @staticmethod
    def mark_downloaded(
        *,
        asset_id: str,
        creator_uid: str,
        title: str,
        video_path: str,
        source_platform: str,
        source_url: str = "",
        folder_path: str = "",
        duration: Optional[int] = None,
        video_status: str = "downloaded",
    ) -> None:
        """新视频下载完成后入库。已存在则只更新 video_path / source_platform / status。"""
        now = datetime.now().isoformat()
        try:
            with get_db_connection() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO media_assets
                        (asset_id, creator_uid, source_url, title, duration,
                         video_path, video_status,
                         transcript_status, source_platform, folder_path,
                         create_time, update_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                    """,
                    (
                        asset_id, creator_uid, source_url, title, duration,
                        video_path, video_status,
                        source_platform, folder_path,
                        now, now,
                    ),
                )
                conn.execute(
                    """
                    UPDATE media_assets
                    SET video_path = ?,
                        video_status = ?,
                        source_platform = COALESCE(NULLIF(?, ''), source_platform),
                        update_time = ?
                    WHERE asset_id = ?
                      AND (COALESCE(video_path, '') != ? OR COALESCE(video_status, '') != ?)
                    """,
                    (video_path, video_status, source_platform, now, asset_id, video_path, video_status),
                )
        except sqlite3.Error as e:
            logger.warning(f"mark_downloaded({asset_id}) 失败: {e}")

    # ---------- 写入：转写生命周期 ----------

    @staticmethod
    def mark_transcribe_running(asset_id: str, task_id: Optional[str] = None) -> None:
        """转写开始时记录 last_task_id；不强制使用，目前主要给 retry-failed-assets 复用。"""
        if not asset_id:
            return
        try:
            with get_db_connection() as conn:
                conn.execute(
                    """
                    UPDATE media_assets
                    SET last_task_id = COALESCE(?, last_task_id),
                        transcript_status = CASE WHEN transcript_status = 'completed' THEN transcript_status ELSE 'pending' END,
                        update_time = CURRENT_TIMESTAMP
                    WHERE asset_id = ?
                    """,
                    (task_id, asset_id),
                )
        except sqlite3.Error as e:
            logger.warning(f"mark_transcribe_running({asset_id}) 失败: {e}")

    @staticmethod
    def mark_transcribe_completed(
        *,
        video_path: Path,
        transcript_path: Optional[Path],
        output_dir: Path,
        preview: str = "",
        full_text: str = "",
    ) -> None:
        """转写成功：写入 transcript_path / preview / text，清除任何旧错误。"""
        if transcript_path:
            try:
                transcript_name = str(transcript_path.relative_to(output_dir.resolve()))
            except ValueError:
                transcript_name = transcript_path.name
        else:
            transcript_name = ""

        asset_id = _resolve_asset_id_from_video_path(video_path)
        try:
            with get_db_connection() as conn:
                if asset_id:
                    conn.execute(
                        """
                        UPDATE media_assets
                        SET transcript_path = ?, transcript_status = 'completed',
                            transcript_preview = ?, transcript_text = ?,
                            transcript_last_error = NULL, transcript_error_type = NULL,
                            transcript_failed_at = NULL,
                            update_time = CURRENT_TIMESTAMP
                        WHERE asset_id = ?
                        """,
                        (transcript_name, preview, full_text, asset_id),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE media_assets
                        SET transcript_path = ?, transcript_status = 'completed',
                            transcript_preview = ?, transcript_text = ?,
                            transcript_last_error = NULL, transcript_error_type = NULL,
                            transcript_failed_at = NULL,
                            update_time = CURRENT_TIMESTAMP
                        WHERE video_path LIKE ? OR title LIKE ?
                        """,
                        (transcript_name, preview, full_text,
                         f"%{video_path.name}%", f"%{video_path.stem}%"),
                    )

                if asset_id:
                    try:
                        title_row = conn.execute(
                            "SELECT title FROM media_assets WHERE asset_id = ?", (asset_id,)
                        ).fetchone()
                        title = title_row[0] if title_row else ""
                        update_fts_for_asset(asset_id, title, full_text)
                    except sqlite3.Error as fts_err:
                        logger.warning(f"FTS 索引更新失败 ({asset_id}): {fts_err}")
        except sqlite3.Error as e:
            logger.warning(f"mark_transcribe_completed({video_path}) 失败: {e}")

    @staticmethod
    def mark_transcribe_failed(
        *,
        video_path: Path,
        error_type: str,
        error_message: str,
        task_id: Optional[str] = None,
    ) -> None:
        """转写失败：写入错误类型/信息，retry_count +1，failed_at 戳为当前时间。"""
        err_text = (error_message or "")[:500]
        asset_id = _resolve_asset_id_from_video_path(video_path)
        try:
            with get_db_connection() as conn:
                if asset_id:
                    conn.execute(
                        """
                        UPDATE media_assets
                        SET transcript_status = 'failed',
                            transcript_last_error = ?,
                            transcript_error_type = ?,
                            transcript_retry_count = COALESCE(transcript_retry_count, 0) + 1,
                            transcript_failed_at = CURRENT_TIMESTAMP,
                            last_task_id = COALESCE(?, last_task_id),
                            update_time = CURRENT_TIMESTAMP
                        WHERE asset_id = ?
                        """,
                        (err_text, error_type, task_id, asset_id),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE media_assets
                        SET transcript_status = 'failed',
                            transcript_last_error = ?,
                            transcript_error_type = ?,
                            transcript_retry_count = COALESCE(transcript_retry_count, 0) + 1,
                            transcript_failed_at = CURRENT_TIMESTAMP,
                            last_task_id = COALESCE(?, last_task_id),
                            update_time = CURRENT_TIMESTAMP
                        WHERE video_path LIKE ? OR title LIKE ?
                        """,
                        (err_text, error_type, task_id,
                         f"%{video_path.name}%", f"%{video_path.stem}%"),
                    )
        except sqlite3.Error as e:
            logger.warning(f"mark_transcribe_failed({video_path}) 失败: {e}")

    # ---------- 发现：按状态查待处理 ----------

    @staticmethod
    def find_pending_to_transcribe(
        *,
        creator_uid: Optional[str] = None,
        platform: Optional[str] = None,
        error_types: Optional[list[str]] = None,
        only_failed: bool = False,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """按业务真相源找应该被（重新）转写的视频。

        - only_failed=True 时只取 transcript_status='failed' 的；否则同时包含 'pending' / 'none'
        - error_types 仅在 only_failed=True 时生效
        - 仅返回 video_status IN ('downloaded', 'pending') 的资产
        """
        clauses: list[str] = ["video_status IN ('downloaded', 'pending')"]
        params: list[Any] = []

        if only_failed:
            clauses.append("transcript_status = 'failed'")
            if error_types:
                placeholders = ",".join(["?"] * len(error_types))
                clauses.append(f"transcript_error_type IN ({placeholders})")
                params.extend(error_types)
        else:
            clauses.append("transcript_status IN ('failed', 'pending', 'none')")

        if creator_uid:
            clauses.append("creator_uid = ?")
            params.append(creator_uid)
        if platform:
            clauses.append("source_platform = ?")
            params.append(platform)

        sql = f"""
            SELECT asset_id, creator_uid, title, video_path, video_status,
                   transcript_status, transcript_error_type, transcript_last_error,
                   transcript_retry_count, transcript_failed_at,
                   source_platform, folder_path, last_task_id
            FROM media_assets
            WHERE {' AND '.join(clauses)}
            ORDER BY transcript_failed_at DESC, update_time DESC
            LIMIT ?
        """
        params.append(limit)

        try:
            with get_db_connection() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as e:
            logger.warning(f"find_pending_to_transcribe 失败: {e}")
            return []

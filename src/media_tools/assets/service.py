from __future__ import annotations

"""assets 域服务：media_assets 表的统一访问与状态更新。"""

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from media_tools.logger import get_logger
from media_tools.store.db import get_db_connection, get_table_columns, update_fts_for_asset

logger = get_logger(__name__)

_AWEME_ID_RE = re.compile(r"\d{15,}")


def _escape_like(s: str) -> str:
    """转义 LIKE 通配符，防止文件名中的 % 和 _ 被当作通配符。"""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _resolve_asset_id_from_video_path(video_path: Path) -> str | None:
    """根据视频文件名启发式定位 asset_id。"""
    matches = _AWEME_ID_RE.findall(video_path.name)
    return matches[0] if matches else None


class MediaAssetService:
    """media_assets 表的写入与发现层"""

    @staticmethod
    def find_asset_id_for_video_path(video_path: Path) -> str | None:
        """三段式 fallback 找出视频对应的 asset_id。"""
        guessed = _resolve_asset_id_from_video_path(video_path)
        if guessed:
            return guessed
        try:
            with get_db_connection() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT asset_id FROM media_assets
                    WHERE video_path LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\'
                    ORDER BY update_time DESC
                    LIMIT 1
                    """,
                    (f"%{_escape_like(video_path.name)}%", f"%{_escape_like(video_path.stem)}%"),
                ).fetchone()
            return row["asset_id"] if row else None
        except sqlite3.Error as e:
            logger.warning(f"find_asset_id_for_video_path({video_path}) 失败: {e}")
            return None

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
        duration: int | None = None,
        video_status: str = "downloaded",
    ) -> None:
        """新视频下载完成后入库。"""
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
                        asset_id,
                        creator_uid,
                        source_url,
                        title,
                        duration,
                        video_path,
                        video_status,
                        source_platform,
                        folder_path,
                        now,
                        now,
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
                      AND NOT (video_status = 'archived' AND ? = 'pending')
                    """,
                    (video_path, video_status, source_platform, now, asset_id, video_path, video_status, video_status),
                )
        except sqlite3.Error as e:
            logger.warning(f"mark_downloaded({asset_id}) 失败: {e}")

    @staticmethod
    def mark_archived(video_path: Path) -> int:
        """转写成功并删除源视频后调用：将 media_assets.video_status 标为 'archived'。

        Returns: 受影响的行数。
        """
        from media_tools.core.config import get_download_path

        try:
            downloads_root = get_download_path()
            resolved = video_path.resolve()
            try:
                rel = str(resolved.relative_to(downloads_root.resolve()))
            except ValueError:
                rel = video_path.name
            absolute = str(resolved)
            now = datetime.now().isoformat()
            with get_db_connection() as conn:
                has_source_url = "source_url" in get_table_columns(conn, "media_assets")
                if has_source_url:
                    cur = conn.execute(
                        """
                        UPDATE media_assets
                        SET video_status = 'archived', update_time = ?
                        WHERE (video_path = ? OR source_url = ?)
                          AND video_status IN ('downloaded', 'pending')
                        """,
                        (now, rel, absolute),
                    )
                else:
                    cur = conn.execute(
                        """
                        UPDATE media_assets
                        SET video_status = 'archived', update_time = ?
                        WHERE video_path = ? AND video_status IN ('downloaded', 'pending')
                        """,
                        (now, rel),
                    )
                if cur.rowcount == 0:
                    basename_like = f"%/{_escape_like(video_path.name)}"
                    if has_source_url:
                        cur = conn.execute(
                            """
                            UPDATE media_assets
                            SET video_status = 'archived', update_time = ?
                            WHERE (video_path LIKE ? ESCAPE '\\' OR source_url LIKE ? ESCAPE '\\')
                              AND video_status IN ('downloaded', 'pending')
                            """,
                            (now, basename_like, basename_like),
                        )
                    else:
                        cur = conn.execute(
                            """
                            UPDATE media_assets
                            SET video_status = 'archived', update_time = ?
                            WHERE video_path LIKE ? ESCAPE '\\' AND video_status IN ('downloaded', 'pending')
                            """,
                            (now, basename_like),
                        )
                return cur.rowcount or 0
        except sqlite3.Error as e:
            logger.warning(f"mark_archived({video_path}) 失败: {e}")
            return 0

    @staticmethod
    def mark_transcribe_running(asset_id: str, task_id: str | None = None) -> None:
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
        transcript_path: Path | None,
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

        # 优先用三段式 fallback 找 asset_id，避免只依赖文件名正则
        asset_id = MediaAssetService.find_asset_id_for_video_path(video_path)
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
                    # 兜底：只更新最可能的一条（最近更新的），避免批量污染
                    cur = conn.execute(
                        """
                        UPDATE media_assets
                        SET transcript_path = ?, transcript_status = 'completed',
                            transcript_preview = ?, transcript_text = ?,
                            transcript_last_error = NULL, transcript_error_type = NULL,
                            transcript_failed_at = NULL,
                            update_time = CURRENT_TIMESTAMP
                        WHERE rowid = (
                            SELECT rowid FROM media_assets
                            WHERE video_path LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\'
                            ORDER BY update_time DESC
                            LIMIT 1
                        )
                        """,
                        (
                            transcript_name,
                            preview,
                            full_text,
                            f"%{_escape_like(video_path.name)}%",
                            f"%{_escape_like(video_path.stem)}%",
                        ),
                    )
                    if cur.rowcount == 0:
                        logger.warning(
                            f"mark_transcribe_completed: 无法定位 asset，跳过更新 "
                            f"(video_path={video_path}, transcript_path={transcript_path})"
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
        task_id: str | None = None,
    ) -> None:
        """转写失败：写入错误类型/信息，retry_count +1，failed_at 戳为当前时间。"""
        err_text = (error_message or "")[:500]
        # 优先用三段式 fallback 找 asset_id，避免只依赖文件名正则
        asset_id = MediaAssetService.find_asset_id_for_video_path(video_path)
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
                    # 兜底：只更新最可能的一条（最近更新的），避免批量污染
                    cur = conn.execute(
                        """
                        UPDATE media_assets
                        SET transcript_status = 'failed',
                            transcript_last_error = ?,
                            transcript_error_type = ?,
                            transcript_retry_count = COALESCE(transcript_retry_count, 0) + 1,
                            transcript_failed_at = CURRENT_TIMESTAMP,
                            last_task_id = COALESCE(?, last_task_id),
                            update_time = CURRENT_TIMESTAMP
                        WHERE rowid = (
                            SELECT rowid FROM media_assets
                            WHERE video_path LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\'
                            ORDER BY update_time DESC
                            LIMIT 1
                        )
                        """,
                        (
                            err_text,
                            error_type,
                            task_id,
                            f"%{_escape_like(video_path.name)}%",
                            f"%{_escape_like(video_path.stem)}%",
                        ),
                    )
                    if cur.rowcount == 0:
                        logger.warning(f"mark_transcribe_failed: 无法定位 asset，跳过更新 (video_path={video_path})")
        except sqlite3.Error as e:
            logger.warning(f"mark_transcribe_failed({video_path}) 失败: {e}")

    @staticmethod
    def find_pending_to_transcribe(
        *,
        creator_uid: str | None = None,
        platform: str | None = None,
        error_types: list[str] | None = None,
        only_failed: bool = False,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = ["video_status IN ('downloaded', 'pending', 'archived')"]
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
            WHERE {" AND ".join(clauses)}
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


class AssetUpdateService:
    """media_assets 转写状态的统一更新入口（含 preview 提取）。"""

    @staticmethod
    def mark_transcribe_completed(
        video_path: Path,
        transcript_path: Path | None,
        output_dir: Path,
    ) -> None:
        try:
            from media_tools.transcribe.preview import extract_transcript_preview, extract_transcript_text

            preview = extract_transcript_preview(transcript_path) if transcript_path else ""
            full_text = extract_transcript_text(transcript_path) if transcript_path else ""
            MediaAssetService.mark_transcribe_completed(
                video_path=video_path,
                transcript_path=transcript_path,
                output_dir=output_dir,
                preview=preview,
                full_text=full_text,
            )
        except (OSError, ValueError) as e:
            logger.warning(f"更新 media_assets 转写状态失败: {e}")

    @staticmethod
    def mark_transcribe_failed(
        video_path: Path,
        error_type: str,
        error_message: str,
    ) -> None:
        try:
            MediaAssetService.mark_transcribe_failed(
                video_path=video_path,
                error_type=error_type,
                error_message=error_message,
            )
        except (OSError, ValueError) as e:
            logger.warning(f"写回 media_assets 失败状态失败: {e}")

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _try_cleanup_disk_files(conn: sqlite3.Connection, asset_ids: list[str]) -> None:
    """尝试清理资产对应的磁盘文件（失败不影响 DB 清理）。"""
    if not asset_ids:
        return
    try:
        from media_tools.assets.file_ops import delete_asset_files
        placeholders = ",".join("?" * len(asset_ids))
        rows = conn.execute(
            f"SELECT creator_uid, source_url, video_path, transcript_path FROM media_assets WHERE asset_id IN ({placeholders})",
            asset_ids,
        ).fetchall()
        for row in rows:
            try:
                delete_asset_files(row[0], row[1] or "", row[2] or "", row[3] or "")
            except (OSError, RuntimeError) as e:
                logger.warning(f"GC 清理磁盘文件失败 asset={row[0]}: {e}")
    except (ImportError, OSError) as e:
        logger.warning(f"GC 跳过磁盘清理: {e}")


def cleanup_stale_assets(conn: sqlite3.Connection) -> dict[str, int]:
    deleted_assets = conn.execute("SELECT asset_id FROM media_assets WHERE video_status='deleted'").fetchall()
    deleted_count = 0
    if deleted_assets:
        deleted_ids = [row[0] for row in deleted_assets]
        _try_cleanup_disk_files(conn, deleted_ids)
        placeholders = ",".join("?" * len(deleted_ids))
        conn.execute(f"DELETE FROM assets_fts WHERE asset_id IN ({placeholders})", deleted_ids)
        conn.execute(f"DELETE FROM media_assets WHERE asset_id IN ({placeholders})", deleted_ids)
        deleted_count = len(deleted_ids)
        logger.info(f"Cleaned up {deleted_count} deleted media assets")

    stale_pending_cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    stale_assets = conn.execute(
        "SELECT asset_id FROM media_assets WHERE transcript_status='pending' AND create_time < ?",
        (stale_pending_cutoff,),
    ).fetchall()
    stale_pending_count = 0
    if stale_assets:
        stale_ids = [row[0] for row in stale_assets]
        _try_cleanup_disk_files(conn, stale_ids)
        placeholders = ",".join("?" * len(stale_ids))
        conn.execute(f"DELETE FROM assets_fts WHERE asset_id IN ({placeholders})", stale_ids)
        conn.execute(f"DELETE FROM media_assets WHERE asset_id IN ({placeholders})", stale_ids)
        stale_pending_count = len(stale_ids)
        logger.info(f"Cleaned up {stale_pending_count} stale pending media assets")

    conn.commit()
    return {"deleted_assets": deleted_count, "stale_pending_assets": stale_pending_count}


# --- Cloud cleanup (merged from services/cloud_cleanup_service.py) ---

from pathlib import Path
from typing import Optional

from media_tools.logger import get_logger

logger_cc = get_logger(__name__ + ".cloud")


class CloudCleanupService:
    """清理云端残留的失败转写记录。"""

    @staticmethod
    async def cleanup(video_path: Path, *, account_id: Optional[str] = None) -> None:
        """清理指定视频的云端失败记录。"""
        from media_tools.assets.service import MediaAssetService
        from media_tools.transcribe.run_service import TranscribeRunService

        asset_id = MediaAssetService.find_asset_id_for_video_path(video_path)

        record_ids = TranscribeRunService.get_failed_record_ids(
            asset_id=asset_id,
            video_path=str(video_path),
            account_id=account_id or "",
        )
        if not record_ids:
            return

        try:
            from media_tools.accounts.auth_state import resolve_qwen_cookie_string
            from media_tools.transcribe.flow import delete_record
            from media_tools.common.http import RequestsApiContext

            from media_tools.transcribe.config import load_config
            auth_state_path = load_config().paths.auth_state_path
            cookie_string = resolve_qwen_cookie_string(
                auth_state_path=auth_state_path,
                account_id=account_id or "",
            )
            if not cookie_string.strip():
                logger_cc.warning("云端清理跳过：无法获取有效 cookie")
                return

            api = RequestsApiContext()
            for record_id in record_ids:
                try:
                    await delete_record(record_id, api, cookie_string=cookie_string)
                    logger_cc.info(f"已清理云端记录 {record_id}")
                except Exception as e:
                    logger_cc.warning(f"清理云端记录 {record_id} 失败: {e}")
        except Exception as e:
            logger_cc.warning(f"云端清理整体失败: {e}")

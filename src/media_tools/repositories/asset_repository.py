from __future__ import annotations
"""素材数据访问层 - 所有 media_assets 表的操作集中在这里"""

import sqlite3
from typing import Any, Optional, Union

from media_tools.db.core import get_db_connection


class AssetRepository:
    """素材仓库 - media_assets 表的所有操作"""

    @staticmethod
    def list_by_creator(creator_uid: str, limit: int = 500) -> list[dict[str, Any]]:
        """按创作者查询素材"""
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT asset_id, creator_uid, title, video_status, transcript_status, transcript_path, transcript_preview, folder_path, is_read, is_starred, create_time, update_time FROM media_assets WHERE creator_uid = ? ORDER BY create_time DESC LIMIT ?",
                (creator_uid, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def find_by_id(asset_id: str) -> Optional[dict[str, Any]]:
        """按 ID 查询素材"""
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT asset_id, creator_uid, title, video_status, transcript_status, transcript_path, transcript_preview, folder_path, is_read, is_starred, create_time, update_time FROM media_assets WHERE asset_id = ? LIMIT 1",
                (asset_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def get_transcript_path(asset_id: str) -> Optional[str]:
        """获取素材转写路径"""
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT transcript_path FROM media_assets WHERE asset_id = ?",
                (asset_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    @staticmethod
    def delete(asset_id: str) -> None:
        """删除素材"""
        with get_db_connection() as conn:
            conn.execute("DELETE FROM media_assets WHERE asset_id = ?", (asset_id,))

    @staticmethod
    def mark_read(asset_id: str, is_read: bool) -> None:
        """标记已读状态"""
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE media_assets SET is_read = ? WHERE asset_id = ?",
                (1 if is_read else 0, asset_id),
            )

    @staticmethod
    def mark_starred(asset_id: str, is_starred: bool) -> None:
        """标记收藏状态"""
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE media_assets SET is_starred = ? WHERE asset_id = ?",
                (1 if is_starred else 0, asset_id),
            )

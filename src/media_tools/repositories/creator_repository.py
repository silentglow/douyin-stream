from __future__ import annotations
"""创作者数据访问层 - 所有 creators 表的操作集中在这里"""

import sqlite3
from typing import Any, Optional, Union

from media_tools.db.core import get_db_connection, get_table_columns


class CreatorRepository:
    """创作者仓库 - creators 表的所有操作"""

    @staticmethod
    def list_all() -> list[dict[str, Any]]:
        """获取所有创作者"""
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT uid, sec_user_id, nickname, avatar, bio, homepage_url, platform, sync_status, last_fetch_time FROM creators ORDER BY nickname"
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def find_by_id(uid: str) -> Optional[dict[str, Any]]:
        """按 ID 查询创作者"""
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT uid, sec_user_id, nickname, avatar, bio, homepage_url, platform, sync_status, last_fetch_time FROM creators WHERE uid = ? LIMIT 1",
                (uid,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def exists(uid: str) -> bool:
        """检查创作者是否存在"""
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT 1 FROM creators WHERE uid = ?", (uid,))
            return cursor.fetchone() is not None

    @staticmethod
    def create(
        uid: str,
        sec_user_id: str,
        nickname: str,
        homepage_url: str = "",
        platform: str = "douyin",
    ) -> None:
        """创建创作者"""
        with get_db_connection() as conn:
            # 检查是否有 homepage_url 列
            columns = get_table_columns(conn, "creators")
            if "homepage_url" in columns:
                conn.execute(
                    "INSERT OR IGNORE INTO creators (uid, sec_user_id, nickname, homepage_url, platform, sync_status) VALUES (?, ?, ?, ?, ?, 'active')",
                    (uid, sec_user_id, nickname, homepage_url, platform),
                )
            else:
                conn.execute(
                    "INSERT OR IGNORE INTO creators (uid, sec_user_id, nickname, platform, sync_status) VALUES (?, ?, ?, ?, 'active')",
                    (uid, sec_user_id, nickname, platform),
                )

    @staticmethod
    def update(
        uid: str,
        sec_user_id: Optional[str] = None,
        nickname: Optional[str] = None,
        homepage_url: Optional[str] = None,
    ) -> None:
        """更新创作者信息"""
        with get_db_connection() as conn:
            columns = get_table_columns(conn, "creators")
            if homepage_url is not None and "homepage_url" in columns:
                conn.execute(
                    "UPDATE creators SET sec_user_id = ?, nickname = ?, homepage_url = ? WHERE uid = ?",
                    (sec_user_id, nickname, homepage_url, uid),
                )
            elif nickname is not None:
                conn.execute(
                    "UPDATE creators SET nickname = ? WHERE uid = ?",
                    (nickname, uid),
                )

    @staticmethod
    def delete(uid: str) -> None:
        """删除创作者"""
        with get_db_connection() as conn:
            conn.execute("DELETE FROM creators WHERE uid = ?", (uid,))

    @staticmethod
    def update_last_fetch_time(uid: str) -> None:
        """更新上次同步时间"""
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE creators SET last_fetch_time = CURRENT_TIMESTAMP WHERE uid = ?",
                (uid,),
            )

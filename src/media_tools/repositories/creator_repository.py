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

    @staticmethod
    def list_with_stats(*, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """查询创作者列表并聚合素材统计信息。"""
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            creator_columns = get_table_columns(conn, "creators")
            platform_select = "c.platform" if "platform" in creator_columns else "'douyin' AS platform"
            platform_group = ", c.platform" if "platform" in creator_columns else ""
            homepage_select = (
                "COALESCE(NULLIF(c.homepage_url, ''), CASE WHEN c.platform = 'douyin' THEN 'https://www.douyin.com/user/' || c.sec_user_id ELSE '' END) AS homepage_url"
                if "homepage_url" in creator_columns
                else "'' AS homepage_url"
            )
            homepage_group = ", c.homepage_url" if "homepage_url" in creator_columns else ""
            cursor = conn.execute(
                f"""
                SELECT
                    c.uid,
                    c.nickname,
                    c.sec_user_id,
                    {platform_select},
                    c.sync_status,
                    c.avatar,
                    c.bio,
                    {homepage_select},
                    c.last_fetch_time,
                    COUNT(ma.asset_id) AS asset_count,
                    COALESCE(SUM(CASE WHEN ma.video_status = 'downloaded' THEN 1 ELSE 0 END), 0) AS downloaded_videos_count,
                    COALESCE(SUM(CASE WHEN ma.transcript_status = 'completed' THEN 1 ELSE 0 END), 0) AS transcript_completed_count,
                    COALESCE(SUM(CASE WHEN ma.transcript_status = 'completed' AND (ma.is_read = 0 OR ma.is_read IS NULL) THEN 1 ELSE 0 END), 0) AS unread_completed_count,
                    COALESCE(SUM(CASE WHEN ma.transcript_status IN ('pending', 'none') AND ma.video_status IN ('downloaded', 'pending') THEN 1 ELSE 0 END), 0) AS transcript_pending_count,
                    COALESCE(SUM(CASE WHEN ma.transcript_status = 'failed' AND ma.video_status IN ('downloaded', 'pending') THEN 1 ELSE 0 END), 0) AS transcript_failed_count
                FROM creators c
                LEFT JOIN media_assets ma ON ma.creator_uid = c.uid
                GROUP BY c.uid, c.nickname, c.sec_user_id{platform_group}, c.sync_status, c.avatar, c.bio{homepage_group}, c.last_fetch_time
                ORDER BY
                    CASE WHEN c.last_fetch_time IS NULL THEN 1 ELSE 0 END,
                    c.last_fetch_time DESC,
                    c.nickname COLLATE NOCASE ASC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def upsert_bilibili_creator(
        uid: str,
        sec_user_id: str,
        nickname: str,
        homepage_url: str = "",
    ) -> bool:
        """插入或更新 Bilibili 创作者。返回 True 表示新插入，False 表示更新。"""
        with get_db_connection() as conn:
            creator_columns = get_table_columns(conn, "creators")
            cursor = conn.execute("SELECT uid FROM creators WHERE uid = ?", (uid,))
            exists = cursor.fetchone() is not None

            if exists:
                # 已存在则更新
                if "homepage_url" in creator_columns:
                    conn.execute(
                        (
                            "UPDATE creators SET sec_user_id = ?, nickname = ?, homepage_url = ?"
                            + (", platform = 'bilibili'" if "platform" in creator_columns else "")
                            + " WHERE uid = ?"
                        ),
                        (sec_user_id, nickname, homepage_url, uid),
                    )
                else:
                    conn.execute(
                        (
                            "UPDATE creators SET sec_user_id = ?, nickname = ?"
                            + (", platform = 'bilibili'" if "platform" in creator_columns else "")
                            + " WHERE uid = ?"
                        ),
                        (sec_user_id, nickname, uid),
                    )
            else:
                # 不存在则插入
                if "homepage_url" in creator_columns and "platform" in creator_columns:
                    conn.execute(
                        "INSERT INTO creators (uid, sec_user_id, nickname, homepage_url, platform, sync_status) VALUES (?, ?, ?, ?, 'bilibili', 'active')",
                        (uid, sec_user_id, nickname, homepage_url),
                    )
                elif "homepage_url" in creator_columns:
                    conn.execute(
                        "INSERT INTO creators (uid, sec_user_id, nickname, homepage_url, sync_status) VALUES (?, ?, ?, ?, 'active')",
                        (uid, sec_user_id, nickname, homepage_url),
                    )
                elif "platform" in creator_columns:
                    conn.execute(
                        "INSERT INTO creators (uid, sec_user_id, nickname, platform, sync_status) VALUES (?, ?, ?, 'bilibili', 'active')",
                        (uid, sec_user_id, nickname),
                    )
                else:
                    conn.execute(
                        "INSERT INTO creators (uid, sec_user_id, nickname, sync_status) VALUES (?, ?, ?, 'active')",
                        (uid, sec_user_id, nickname),
                    )
            conn.commit()
            return not exists

    @staticmethod
    def delete_with_assets(uid: str) -> tuple[Optional[str], list[dict[str, Any]]]:
        """级联删除创作者及其素材。返回 (nickname, assets_list) 用于后续文件清理。"""
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")

            cursor = conn.execute("SELECT nickname FROM creators WHERE uid = ?", (uid,))
            creator = cursor.fetchone()
            if not creator:
                conn.rollback()
                return None, []

            nickname = creator["nickname"]

            cursor = conn.execute(
                "SELECT asset_id, video_path, transcript_path FROM media_assets WHERE creator_uid = ?",
                (uid,),
            )
            assets = [dict(row) for row in cursor.fetchall()]

            asset_ids = [a["asset_id"] for a in assets if a["asset_id"]]
            if asset_ids:
                placeholders = ",".join("?" * len(asset_ids))
                conn.execute(f"DELETE FROM assets_fts WHERE asset_id IN ({placeholders})", asset_ids)
            conn.execute("DELETE FROM media_assets WHERE creator_uid = ?", (uid,))
            conn.execute("DELETE FROM creators WHERE uid = ?", (uid,))
            conn.commit()
            return nickname, assets

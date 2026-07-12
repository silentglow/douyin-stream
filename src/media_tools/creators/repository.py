from __future__ import annotations

"""创作者数据访问层 - 所有 creators 表的操作集中在这里"""

import sqlite3
from typing import Any

from media_tools.store.db import get_db_connection, get_table_columns


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
    def find_by_id(uid: str) -> dict[str, Any] | None:
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
        sec_user_id: str | None = None,
        nickname: str | None = None,
        homepage_url: str | None = None,
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
    def toggle_auto_sync(uid: str, auto_sync: bool) -> None:
        """切换创作者自动同步状态"""
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE creators SET auto_sync = ? WHERE uid = ?",
                (1 if auto_sync else 0, uid),
            )

    @staticmethod
    def set_all_auto_sync(auto_sync: bool) -> int:
        """批量设置全部创作者的自动同步状态，返回受影响行数。"""
        with get_db_connection() as conn:
            cur = conn.execute(
                "UPDATE creators SET auto_sync = ?",
                (1 if auto_sync else 0,),
            )
            return int(cur.rowcount or 0)

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
            auto_sync_select = "c.auto_sync" if "auto_sync" in creator_columns else "0 AS auto_sync"
            auto_sync_group = ", c.auto_sync" if "auto_sync" in creator_columns else ""
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
                    {auto_sync_select},
                    COUNT(ma.asset_id) AS asset_count,
                    COALESCE(SUM(CASE WHEN ma.video_status IN ('downloaded', 'archived') THEN 1 ELSE 0 END), 0) AS downloaded_videos_count,
                    COALESCE(SUM(CASE WHEN ma.transcript_status = 'completed' THEN 1 ELSE 0 END), 0) AS transcript_completed_count,
                    COALESCE(SUM(CASE WHEN ma.transcript_status = 'completed' AND (ma.is_read = 0 OR ma.is_read IS NULL) THEN 1 ELSE 0 END), 0) AS unread_completed_count,
                    COALESCE(SUM(CASE WHEN ma.transcript_status IN ('pending', 'none') AND ma.video_status IN ('downloaded', 'pending') THEN 1 ELSE 0 END), 0) AS transcript_pending_count,
                    COALESCE(SUM(CASE WHEN ma.transcript_status = 'failed' AND ma.video_status IN ('downloaded', 'pending') THEN 1 ELSE 0 END), 0) AS transcript_failed_count
                FROM creators c
                LEFT JOIN media_assets ma ON ma.creator_uid = c.uid
                GROUP BY c.uid, c.nickname, c.sec_user_id{platform_group}, c.sync_status, c.avatar, c.bio{homepage_group}, c.last_fetch_time{auto_sync_group}
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
    @staticmethod
    def _upsert_platform_creator(
        platform: str,
        uid: str,
        sec_user_id: str,
        nickname: str,
        homepage_url: str = "",
        avatar: str = "",
    ) -> bool:
        """插入或更新平台创作者（列按实际 schema 动态拼装）。返回 True 表示新插入。"""
        with get_db_connection() as conn:
            creator_columns = get_table_columns(conn, "creators")
            cursor = conn.execute("SELECT uid FROM creators WHERE uid = ?", (uid,))
            exists = cursor.fetchone() is not None

            # 可选列：仅当表里存在时写入；avatar 为空时不覆盖已有头像
            optional: list[tuple[str, str]] = []
            if "homepage_url" in creator_columns:
                optional.append(("homepage_url", homepage_url))
            if "avatar" in creator_columns and avatar:
                optional.append(("avatar", avatar))

            if exists:
                sets = ["sec_user_id = ?", "nickname = ?"]
                params: list[str] = [sec_user_id, nickname]
                for col, val in optional:
                    sets.append(f"{col} = ?")
                    params.append(val)
                if "platform" in creator_columns:
                    sets.append("platform = ?")
                    params.append(platform)
                params.append(uid)
                conn.execute(f"UPDATE creators SET {', '.join(sets)} WHERE uid = ?", params)
            else:
                cols = ["uid", "sec_user_id", "nickname"]
                params = [uid, sec_user_id, nickname]
                for col, val in optional:
                    cols.append(col)
                    params.append(val)
                if "platform" in creator_columns:
                    cols.append("platform")
                    params.append(platform)
                cols.append("sync_status")
                params.append("active")
                placeholders = ", ".join("?" for _ in cols)
                conn.execute(f"INSERT INTO creators ({', '.join(cols)}) VALUES ({placeholders})", params)
            conn.commit()
            return not exists

    @staticmethod
    def upsert_bilibili_creator(
        uid: str,
        sec_user_id: str,
        nickname: str,
        homepage_url: str = "",
        avatar: str = "",
    ) -> bool:
        """插入或更新 Bilibili 创作者。返回 True 表示新插入，False 表示更新。"""
        return CreatorRepository._upsert_platform_creator(
            "bilibili", uid, sec_user_id, nickname, homepage_url=homepage_url, avatar=avatar
        )

    @staticmethod
    def upsert_youtube_creator(
        uid: str,
        sec_user_id: str,
        nickname: str,
        homepage_url: str = "",
        avatar: str = "",
    ) -> bool:
        """插入或更新 YouTube 创作者。返回 True 表示新插入，False 表示更新。"""
        return CreatorRepository._upsert_platform_creator(
            "youtube", uid, sec_user_id, nickname, homepage_url=homepage_url, avatar=avatar
        )

    @staticmethod
    def unfollow_keep_content(uid: str) -> dict[str, Any] | None:
        """停止关注但保留素材/文稿。

        - auto_sync = 0（不再增量同步）
        - sync_status = 'unfollowed'（列表可区分「已停跟」）
        - 不删除 media_assets / 磁盘文件
        """
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT uid, nickname FROM creators WHERE uid = ?",
                (uid,),
            ).fetchone()
            if not row:
                return None
            asset_count = conn.execute(
                "SELECT COUNT(*) AS c FROM media_assets WHERE creator_uid = ?",
                (uid,),
            ).fetchone()["c"]
            conn.execute(
                """
                UPDATE creators
                SET auto_sync = 0,
                    sync_status = 'unfollowed'
                WHERE uid = ?
                """,
                (uid,),
            )
            conn.commit()
            return {
                "uid": row["uid"],
                "nickname": row["nickname"],
                "asset_count": int(asset_count or 0),
            }

    @staticmethod
    def refollow(uid: str) -> bool:
        """将已停跟创作者恢复为跟进中（不自动开 auto_sync）。"""
        with get_db_connection() as conn:
            cur = conn.execute(
                """
                UPDATE creators
                SET sync_status = 'active'
                WHERE uid = ? AND sync_status = 'unfollowed'
                """,
                (uid,),
            )
            conn.commit()
            return (cur.rowcount or 0) > 0

    @staticmethod
    def delete_with_assets(uid: str) -> tuple[str | None, list[dict[str, Any]]]:
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

    @staticmethod
    def search_by_name_or_bio(query: str, limit: int = 10) -> list[dict[str, Any]]:
        """按昵称或简介搜索创作者（LIKE 匹配）。"""
        pattern = f"%{query}%"
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT
                    'creator' as type,
                    uid as id,
                    nickname as title,
                    platform as subtitle,
                    sync_status as status
                FROM creators
                WHERE nickname LIKE ? OR bio LIKE ?
                ORDER BY nickname
                LIMIT ?
                """,
                (pattern, pattern, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

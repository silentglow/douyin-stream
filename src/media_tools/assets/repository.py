from __future__ import annotations
"""素材数据访问层 - 所有 media_assets 表的操作集中在这里"""

import sqlite3
from typing import Any, Optional, Union

from media_tools.store.db import get_db_connection, get_table_columns
from media_tools.assets.file_ops import get_source_url_column


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
    def count_pending_transcribe_by_creator(creator_uid: str) -> int:
        """统计创作者下待转写的素材数量（video_status 为 downloaded/pending 且 transcript_status 为 pending/none/failed）。"""
        with get_db_connection() as conn:
            cursor = conn.execute(
                """SELECT COUNT(1)
                   FROM media_assets
                   WHERE creator_uid = ?
                     AND video_status IN ('downloaded', 'pending')
                     AND transcript_status IN ('pending', 'none', 'failed')""",
                (creator_uid,),
            )
            row = cursor.fetchone()
            return int(row[0] or 0) if row else 0

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

    # ---------- list / search ----------

    @staticmethod
    def list_with_filters(
        *,
        creator_uid: Optional[str] = None,
        status_filter: Optional[list[str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """按条件查询素材列表（支持创作者和转写状态过滤）。"""
        base_sql = (
            "SELECT asset_id, creator_uid, title, video_status, transcript_status, "
            "transcript_path, transcript_preview, folder_path, is_read, is_starred, "
            "transcript_error_type, transcript_last_error, transcript_retry_count, "
            "transcript_failed_at, source_platform, last_task_id, "
            "create_time, update_time FROM media_assets"
        )
        where_clauses: list[str] = []
        params: list = []
        if creator_uid:
            where_clauses.append("creator_uid = ?")
            params.append(creator_uid)
        if status_filter:
            placeholders = ",".join(["?"] * len(status_filter))
            where_clauses.append(f"transcript_status IN ({placeholders})")
            params.extend(status_filter)

        sql = base_sql
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        sql += " ORDER BY update_time DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def search_fts_lite(query: str, limit: int = 10) -> list[dict[str, Any]]:
        """FTS5 全局搜索（精简字段，用于跨类型搜索）。"""
        safe_q = query.replace('"', '""')
        fts_query = f'"{safe_q}"*'
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT
                    'asset' as type,
                    ma.asset_id as id,
                    ma.title,
                    c.nickname as subtitle,
                    ma.transcript_status as status
                FROM media_assets ma
                INNER JOIN assets_fts f ON ma.asset_id = f.asset_id
                LEFT JOIN creators c ON ma.creator_uid = c.uid
                WHERE assets_fts MATCH ?
                ORDER BY ma.create_time DESC
                LIMIT ?
                """,
                (fts_query, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def search_fts(query: str) -> list[dict[str, Any]]:
        """FTS5 全文搜索素材标题和转写内容。query 应已清洗。"""
        safe_q = query.replace('"', '""')
        fts_query = f'"{safe_q}"*'
        like_pattern = f"%{query}%"

        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT a.asset_id, a.creator_uid, a.title, a.video_status, a.transcript_status,
                       a.transcript_path, a.transcript_preview, a.folder_path, a.is_read, a.is_starred,
                       a.create_time, a.update_time,
                       CASE WHEN LOWER(a.title) LIKE LOWER(?) THEN 'title' ELSE 'content' END AS match_type
                FROM media_assets a
                INNER JOIN assets_fts f ON a.asset_id = f.asset_id
                WHERE assets_fts MATCH ?
                ORDER BY
                  CASE WHEN LOWER(a.title) LIKE LOWER(?) THEN 0 ELSE 1 END,
                  a.update_time DESC
                LIMIT 50
                """,
                (like_pattern, fts_query, like_pattern),
            )
            return [dict(row) for row in cursor.fetchall()]

    # ---------- export ----------

    @staticmethod
    def find_by_ids_for_export(asset_ids: list[str]) -> list[dict[str, Any]]:
        """按 ID 列表查询可导出的素材（需有 transcript_path）。"""
        if not asset_ids:
            return []
        placeholders = ",".join("?" * len(asset_ids))
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                f"SELECT asset_id, title, transcript_path FROM media_assets WHERE asset_id IN ({placeholders}) AND transcript_path IS NOT NULL",
                asset_ids,
            )
            return [dict(row) for row in cursor.fetchall()]

    # ---------- delete helpers ----------

    @staticmethod
    def find_for_deletion(asset_id: str) -> Optional[dict[str, Any]]:
        """查询单条素材用于删除（含 source_url 兼容性处理）。"""
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            source_url_select = get_source_url_column(conn)
            cursor = conn.execute(
                f"SELECT creator_uid, {source_url_select} video_path, transcript_path FROM media_assets WHERE asset_id = ?",
                (asset_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def delete_with_fts(asset_id: str, *, conn: Optional[sqlite3.Connection] = None) -> None:
        """从 media_assets 和 assets_fts 中删除素材。可传入已有连接以参与外部事务。"""
        if conn is not None:
            conn.execute("DELETE FROM assets_fts WHERE asset_id = ?", (asset_id,))
            conn.execute("DELETE FROM media_assets WHERE asset_id = ?", (asset_id,))
        else:
            with get_db_connection() as conn:
                conn.execute("DELETE FROM assets_fts WHERE asset_id = ?", (asset_id,))
                conn.execute("DELETE FROM media_assets WHERE asset_id = ?", (asset_id,))

    @staticmethod
    def find_for_bulk_deletion(asset_ids: list[str]) -> list[dict[str, Any]]:
        """批量查询素材用于删除。"""
        if not asset_ids:
            return []
        placeholders = ",".join("?" * len(asset_ids))
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            source_url_select = get_source_url_column(conn)
            cursor = conn.execute(
                f"SELECT asset_id, creator_uid, {source_url_select} video_path, transcript_path FROM media_assets WHERE asset_id IN ({placeholders})",
                asset_ids,
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def bulk_delete_with_fts(asset_ids: list[str], *, conn: Optional[sqlite3.Connection] = None) -> int:
        """批量删除素材（含 FTS），返回删除行数。可传入已有连接以参与外部事务。"""
        if not asset_ids:
            return 0
        placeholders = ",".join("?" * len(asset_ids))
        if conn is not None:
            conn.execute(f"DELETE FROM assets_fts WHERE asset_id IN ({placeholders})", asset_ids)
            cursor = conn.execute(
                f"DELETE FROM media_assets WHERE asset_id IN ({placeholders})",
                asset_ids,
            )
            return cursor.rowcount
        with get_db_connection() as conn:
            conn.execute(f"DELETE FROM assets_fts WHERE asset_id IN ({placeholders})", asset_ids)
            cursor = conn.execute(
                f"DELETE FROM media_assets WHERE asset_id IN ({placeholders})",
                asset_ids,
            )
            return cursor.rowcount

    # ---------- mark ----------

    @staticmethod
    def mark_asset(asset_id: str, *, is_read: Optional[bool] = None, is_starred: Optional[bool] = None) -> int:
        """标记素材，返回受影响的行数。"""
        if is_read is None and is_starred is None:
            return 0
        updates: list[str] = []
        params: list = []
        if is_read is not None:
            updates.append("is_read = ?")
            params.append(is_read)
        if is_starred is not None:
            updates.append("is_starred = ?")
            params.append(is_starred)
        updates.append("update_time = CURRENT_TIMESTAMP")
        params.append(asset_id)

        with get_db_connection() as conn:
            cursor = conn.execute(f"UPDATE media_assets SET {', '.join(updates)} WHERE asset_id = ?", params)
            return cursor.rowcount

    @staticmethod
    def bulk_mark(
        asset_ids: list[str],
        *,
        is_read: Optional[bool] = None,
        is_starred: Optional[bool] = None,
    ) -> int:
        """批量标记素材，返回更新的行数。"""
        if is_read is None and is_starred is None:
            return 0
        if not asset_ids:
            return 0

        set_clauses: list[str] = []
        set_params: list = []
        if is_read is not None:
            set_clauses.append("is_read = ?")
            set_params.append(is_read)
        if is_starred is not None:
            set_clauses.append("is_starred = ?")
            set_params.append(is_starred)
        set_clauses.append("update_time = CURRENT_TIMESTAMP")

        updated = 0
        with get_db_connection() as conn:
            for start in range(0, len(asset_ids), 500):
                chunk = asset_ids[start:start + 500]
                placeholders = ",".join("?" * len(chunk))
                sql = f"UPDATE media_assets SET {', '.join(set_clauses)} WHERE asset_id IN ({placeholders})"
                cursor = conn.execute(sql, (*set_params, *chunk))
                updated += cursor.rowcount
        return updated

    # ---------- cleanup ----------

    @staticmethod
    def list_all_for_cleanup() -> list[dict[str, Any]]:
        """查询所有素材用于清理检查（含 source_url 兼容性处理）。"""
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            source_url_select = get_source_url_column(conn)
            cursor = conn.execute(
                f"SELECT asset_id, creator_uid, {source_url_select} video_path, transcript_path FROM media_assets"
            )
            return [dict(row) for row in cursor.fetchall()]

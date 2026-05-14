from __future__ import annotations
"""FTS5 全文搜索索引管理"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def _ensure_fts_table(conn: sqlite3.Connection) -> None:
    """Create assets_fts FTS5 virtual table if it doesn't exist."""
    from .core import get_table_columns

    if get_table_columns(conn, "assets_fts"):
        return
    cursor = conn.cursor()
    cursor.execute("""
        CREATE VIRTUAL TABLE assets_fts USING fts5(
            asset_id UNINDEXED,
            title,
            transcript_text,
            tokenize='unicode61 remove_diacritics 2'
        )
    """)


def ensure_fts_populated() -> bool:
    """Ensure FTS5 index has data; rebuilds from media_assets if empty."""
    from .core import get_db_connection
    with get_db_connection() as conn:
        # 表不存在时 SELECT 会抛 OperationalError，先确保表已就位
        _ensure_fts_table(conn)
        cur = conn.execute("SELECT COUNT(*) FROM assets_fts")
        count = cur.fetchone()[0]
        if count > 0:
            return True
        _rebuild_fts_from_assets(conn)
        return True


def update_fts_for_asset(asset_id: str, title: str, transcript_text: str) -> None:
    """Upsert a single asset into the FTS5 index."""
    from .core import get_db_connection
    with get_db_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO assets_fts(asset_id, title, transcript_text) VALUES (?, ?, ?)",
            (asset_id, title, transcript_text or ""),
        )


def _rebuild_fts_from_assets(conn: sqlite3.Connection) -> int:
    """Rebuild full FTS5 index from media_assets. Caller must hold conn."""
    cursor = conn.execute(
        "SELECT asset_id, title, COALESCE(transcript_text, '') FROM media_assets"
    )
    rows = list(cursor.fetchall())
    if not rows:
        return 0
    conn.executemany(
        "INSERT OR REPLACE INTO assets_fts(asset_id, title, transcript_text) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def rebuild_fts_index() -> int:
    """Full rebuild of FTS5 index. Returns row count."""
    from .core import get_db_connection
    with get_db_connection() as conn:
        _ensure_fts_table(conn)
        count = _rebuild_fts_from_assets(conn)
        logger.info(f"FTS5 index rebuilt: {count} rows")
        return count

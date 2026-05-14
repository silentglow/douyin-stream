import sqlite3


def create_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS creators (
        uid TEXT PRIMARY KEY,
        sec_user_id TEXT,
        nickname TEXT,
        avatar TEXT,
        bio TEXT,
        homepage_url TEXT,
        platform TEXT DEFAULT 'douyin',
        sync_status TEXT DEFAULT 'active',
        last_fetch_time DATETIME,
        auto_sync BOOLEAN DEFAULT 0
    )
    """)


def create_indexes(conn: sqlite3.Connection) -> None:
    pass

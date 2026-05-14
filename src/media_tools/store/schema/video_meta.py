import sqlite3


def create_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS video_metadata (
        aweme_id TEXT PRIMARY KEY,
        uid TEXT NOT NULL,
        nickname TEXT,
        desc TEXT,
        create_time INTEGER,
        duration INTEGER,
        digg_count INTEGER DEFAULT 0,
        comment_count INTEGER DEFAULT 0,
        collect_count INTEGER DEFAULT 0,
        share_count INTEGER DEFAULT 0,
        play_count INTEGER DEFAULT 0,
        local_filename TEXT,
        file_size INTEGER,
        fetch_time INTEGER
    )
    """)


def create_indexes(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_uid ON video_metadata(uid)")

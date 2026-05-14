import sqlite3


def create_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS media_assets (
        asset_id TEXT PRIMARY KEY,
        creator_uid TEXT,
        source_url TEXT,
        title TEXT,
        duration INTEGER,
        video_path TEXT,
        video_status TEXT DEFAULT 'pending',
        transcript_path TEXT,
        transcript_status TEXT DEFAULT 'none',
        create_time DATETIME,
        update_time DATETIME,
        is_read BOOLEAN DEFAULT 0,
        is_starred BOOLEAN DEFAULT 0,
        folder_path TEXT DEFAULT '',
        transcript_preview TEXT,
        transcript_text TEXT,
        transcript_last_error TEXT,
        transcript_error_type TEXT,
        transcript_retry_count INTEGER DEFAULT 0,
        transcript_failed_at DATETIME,
        last_task_id TEXT,
        source_platform TEXT
    )
    """)


def create_indexes(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE INDEX IF NOT EXISTS idx_media_assets_creator ON media_assets(creator_uid)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_media_assets_video_status ON media_assets(video_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_media_assets_transcript_status ON media_assets(transcript_status)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_assets_creator_status "
        "ON media_assets(creator_uid, video_status, transcript_status)"
    )

import sqlite3

version = 1


def apply(conn: sqlite3.Connection) -> None:
    """Apply all schema changes that were previously handled by _ensure_column."""
    # task_queue columns
    _add_column_if_not_exists(conn, "task_queue", "update_time", "DATETIME")
    _add_column_if_not_exists(conn, "task_queue", "cancel_requested", "INTEGER DEFAULT 0")
    _add_column_if_not_exists(conn, "task_queue", "auto_retry", "INTEGER DEFAULT 0")

    # creators columns
    _add_column_if_not_exists(conn, "creators", "platform", "TEXT DEFAULT 'douyin'")
    _add_column_if_not_exists(conn, "creators", "sync_status", "TEXT DEFAULT 'active'")
    _add_column_if_not_exists(conn, "creators", "last_fetch_time", "DATETIME")
    _add_column_if_not_exists(conn, "creators", "auto_sync", "BOOLEAN DEFAULT 0")
    _add_column_if_not_exists(conn, "creators", "avatar", "TEXT")
    _add_column_if_not_exists(conn, "creators", "bio", "TEXT")

    # Accounts_Pool columns
    _add_column_if_not_exists(conn, "Accounts_Pool", "remark", "TEXT DEFAULT ''")
    _add_column_if_not_exists(conn, "Accounts_Pool", "auth_state_path", "TEXT DEFAULT ''")

    # media_assets columns
    _add_column_if_not_exists(conn, "media_assets", "source_url", "TEXT")
    _add_column_if_not_exists(conn, "media_assets", "is_read", "BOOLEAN DEFAULT 0")
    _add_column_if_not_exists(conn, "media_assets", "is_starred", "BOOLEAN DEFAULT 0")
    _add_column_if_not_exists(conn, "media_assets", "folder_path", "TEXT DEFAULT ''")
    _add_column_if_not_exists(conn, "media_assets", "create_time", "DATETIME")
    _add_column_if_not_exists(conn, "media_assets", "update_time", "DATETIME")
    _add_column_if_not_exists(conn, "media_assets", "transcript_preview", "TEXT")
    _add_column_if_not_exists(conn, "media_assets", "transcript_text", "TEXT")
    _add_column_if_not_exists(conn, "media_assets", "transcript_last_error", "TEXT")
    _add_column_if_not_exists(conn, "media_assets", "transcript_error_type", "TEXT")
    _add_column_if_not_exists(conn, "media_assets", "transcript_retry_count", "INTEGER DEFAULT 0")
    _add_column_if_not_exists(conn, "media_assets", "transcript_failed_at", "DATETIME")
    _add_column_if_not_exists(conn, "media_assets", "last_task_id", "TEXT")
    _add_column_if_not_exists(conn, "media_assets", "source_platform", "TEXT")


def _add_column_if_not_exists(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    """Add column only if it doesn't already exist."""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except sqlite3.OperationalError:
        pass  # Column already exists

import sqlite3


def create_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS task_queue (
        task_id TEXT PRIMARY KEY,
        task_type TEXT,
        payload JSON,
        status TEXT DEFAULT 'PENDING',
        progress REAL DEFAULT 0.0,
        error_msg TEXT,
        create_time DATETIME,
        update_time DATETIME,
        start_time DATETIME,
        end_time DATETIME,
        cancel_requested INTEGER DEFAULT 0,
        auto_retry INTEGER DEFAULT 0
    )
    """)


def create_indexes(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_queue_status ON task_queue(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_queue_update_time ON task_queue(update_time)")

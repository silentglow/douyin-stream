import sqlite3


def create_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS scheduled_tasks (
        task_id TEXT PRIMARY KEY,
        task_type TEXT,
        cron_expr TEXT,
        enabled BOOLEAN DEFAULT 1,
        create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)


def create_indexes(conn: sqlite3.Connection) -> None:
    pass

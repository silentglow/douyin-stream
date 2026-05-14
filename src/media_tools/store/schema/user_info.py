import sqlite3


def create_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS user_info_web (
        uid TEXT PRIMARY KEY,
        sec_user_id TEXT,
        nickname TEXT,
        avatar TEXT
    )
    """)


def create_indexes(conn: sqlite3.Connection) -> None:
    pass

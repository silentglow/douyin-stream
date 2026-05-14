import sqlite3


def create_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS auth_credentials (
        platform TEXT PRIMARY KEY,
        auth_data JSON,
        is_valid BOOLEAN DEFAULT 1,
        last_check_time DATETIME
    )
    """)


def create_indexes(conn: sqlite3.Connection) -> None:
    pass

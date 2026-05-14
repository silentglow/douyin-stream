import sqlite3


def create_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS SystemSettings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)


def create_indexes(conn: sqlite3.Connection) -> None:
    pass

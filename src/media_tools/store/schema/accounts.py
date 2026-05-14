import sqlite3


def create_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS Accounts_Pool (
        account_id TEXT PRIMARY KEY,
        platform TEXT,
        cookie_data TEXT,
        status TEXT DEFAULT 'active',
        last_used TIMESTAMP,
        create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        remark TEXT DEFAULT '',
        auth_state_path TEXT DEFAULT ''
    )
    """)


def create_indexes(conn: sqlite3.Connection) -> None:
    pass

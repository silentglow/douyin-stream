import sqlite3
import logging

logger = logging.getLogger(__name__)


def ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)


def get_current_version(conn: sqlite3.Connection) -> int:
    ensure_version_table(conn)
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return row[0] or 0


def run_migrations(conn: sqlite3.Connection) -> None:
    from . import _001_init

    current = get_current_version(conn)
    migrations = [
        (1, _001_init),
    ]

    for version, module in migrations:
        if version > current:
            logger.info(f"Applying migration {version}")
            module.apply(conn)
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
            conn.commit()

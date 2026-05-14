import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from media_tools.logger import get_logger

logger = get_logger('db')

_db_path: Optional[str] = None


def get_db_path() -> str:
    global _db_path
    if _db_path is None:
        project_root = Path(__file__).resolve().parents[2]
        default = project_root / "data" / "media_tools.db"
        default.parent.mkdir(parents=True, exist_ok=True)
        _db_path = str(default)
    return _db_path


def set_db_path(path: str) -> None:
    global _db_path
    _db_path = path


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency – yields a connection with explicit transaction."""
    conn = sqlite3.connect(get_db_path(), timeout=15.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    conn.execute("BEGIN")
    try:
        yield conn
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


_thread_local = threading.local()


def get_db_connection() -> sqlite3.Connection:
    """Get a database connection (thread-local cached)."""
    cached = getattr(_thread_local, "conn", None)
    if cached is not None:
        try:
            cached.execute("SELECT 1")
            return cached
        except sqlite3.Error:
            try:
                cached.close()
            except Exception:
                pass
            _thread_local.conn = None

    conn = sqlite3.connect(get_db_path(), timeout=15.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    _thread_local.conn = conn
    return conn


def close_db_connection() -> None:
    cached = getattr(_thread_local, "conn", None)
    if cached is not None:
        try:
            cached.close()
        except sqlite3.Error:
            pass
        _thread_local.conn = None

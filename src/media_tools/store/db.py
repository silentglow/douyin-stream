import re
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path

from media_tools.logger import get_logger

from .path_utils import local_asset_id, resolve_query_value, resolve_safe_path  # noqa: F401

logger = get_logger("db")

# --- Identifier validation ---
_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_VALID_TABLES = frozenset(
    {
        "creators",
        "media_assets",
        "task_queue",
        "auth_credentials",
        "Accounts_Pool",
        "SystemSettings",
        "scheduled_tasks",
        "assets_fts",
        "video_metadata",
        "user_info_web",
        "transcribe_runs",
    }
)


def validate_identifier(name: str, field_name: str = "identifier") -> str:
    if not name or not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid {field_name}: {name!r}")
    return name


def _check_table_name(table: str) -> str:
    if table in _VALID_TABLES:
        return table
    return validate_identifier(table, "table_name")


def get_table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    safe_table = _check_table_name(table)
    columns = {
        row["name"] if isinstance(row, sqlite3.Row) else row[1]
        for row in conn.execute("PRAGMA table_info(" + safe_table + ")").fetchall()
    }
    return columns


# --- Resolved DB path ---
_db_path: str | None = None


def get_db_path() -> str:
    global _db_path
    if _db_path is None:
        project_root = Path(__file__).resolve().parents[3]
        default = project_root / "data" / "media_tools.db"
        default.parent.mkdir(parents=True, exist_ok=True)
        _db_path = str(default)
    return _db_path


def set_db_path(path: str) -> None:
    global _db_path
    _db_path = path


# --- Connection management ---
@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
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
    cached = getattr(_thread_local, "conn", None)
    cached_path = getattr(_thread_local, "db_path", None)
    current_path = get_db_path()
    if cached is not None and cached_path == current_path:
        try:
            cached.execute("SELECT 1")
            cached.row_factory = sqlite3.Row
            return cached
        except sqlite3.Error:
            with suppress(sqlite3.Error, OSError):
                cached.close()
            _thread_local.conn = None
    elif cached is not None:
        with suppress(sqlite3.Error, OSError):
            cached.close()
        _thread_local.conn = None

    conn = sqlite3.connect(current_path, timeout=15.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    _thread_local.conn = conn
    _thread_local.db_path = current_path
    return conn


@contextmanager
def get_db_connection_safe() -> Generator[sqlite3.Connection, None, None]:
    """线程安全的 DB 连接上下文管理器，自动处理 row_factory 隔离与事务回滚。

    与裸用 `with get_db_connection() as conn:` 的区别：
    - 返回前确保 row_factory = sqlite3.Row（避免被上游调用者污染）
    - 若连接处于显式事务中且发生异常，自动执行 ROLLBACK
    """
    conn = get_db_connection()
    old_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    except sqlite3.Error:
        # 若连接处于显式事务中，先回滚避免污染后续使用
        with suppress(sqlite3.Error):
            conn.rollback()
        raise
    finally:
        conn.row_factory = old_factory


def close_db_connection() -> None:
    cached = getattr(_thread_local, "conn", None)
    if cached is not None:
        with suppress(sqlite3.Error):
            cached.close()
        _thread_local.conn = None


def close_all_cached_connections() -> int:
    """Backward-compatible alias for close_db_connection."""
    close_db_connection()
    return 1


def reset_db_cache() -> None:
    """Clear current thread's DB connection cache.

    Mainly for testing (e.g. when init_db switches to a test database).
    """
    close_db_connection()


# --- Connection pool stats ---
_physical_connections: int = 0
_physical_connections_lock = threading.Lock()


# --- Legacy DBConnection class (for backward compatibility) ---
class DBConnection:
    """Legacy wrapper for backward compatibility."""

    _open_count = 0
    _open_count_lock = threading.Lock()
    _max_connections_warning = 20

    def __init__(self, keep_open: bool = False, _owns_physical: bool = True):
        global _physical_connections
        self._conn = sqlite3.connect(get_db_path(), timeout=15.0)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.row_factory = sqlite3.Row
        self._keep_open = keep_open
        self._committed = False
        self._owns_physical = _owns_physical

        if _owns_physical:
            with DBConnection._open_count_lock:
                DBConnection._open_count += 1
            with _physical_connections_lock:
                _physical_connections += 1
            if DBConnection._open_count > DBConnection._max_connections_warning:
                logger.warning(f"DB connection count high: {DBConnection._open_count}")

    def __enter__(self) -> sqlite3.Connection:
        return self._conn

    def __exit__(self, exc_type, _exc_val, _exc_tb) -> None:
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        except sqlite3.Error:
            self._conn.rollback()
        finally:
            if self._owns_physical:
                self._conn.close()
                with DBConnection._open_count_lock:
                    DBConnection._open_count -= 1
                global _physical_connections
                with _physical_connections_lock:
                    _physical_connections -= 1

    def commit(self) -> None:
        self._conn.commit()
        self._committed = True

    @classmethod
    def get_stats(cls) -> dict:
        """Return connection statistics."""
        return {
            "open_connections": cls._open_count,
            "physical_connections": _physical_connections,
            "max_warning": cls._max_connections_warning,
        }


# --- init_db (legacy entry point) ---
def init_db(db_path: str | None = None) -> None:
    """Initialize database using new schema and migration framework."""
    global _db_path
    if db_path:
        _db_path = str(db_path)

    from .migrations import run_migrations
    from .schema import init_schema

    conn = sqlite3.connect(get_db_path(), timeout=15.0)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        init_schema(conn)
        run_migrations(conn)
        from .fts import _ensure_fts_table

        _ensure_fts_table(conn)
        conn.commit()
        logger.info("Database initialized")
    except (sqlite3.Error, OSError) as e:
        logger.error(f"Database initialization failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


# --- Re-export FTS functions for backward compatibility ---
from .fts import ensure_fts_populated, rebuild_fts_index, update_fts_for_asset  # noqa: F401, E402

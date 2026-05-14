import re
import sqlite3
import os
import threading
from pathlib import Path
from typing import Generator, Optional, Union
from media_tools.logger import get_logger

logger = get_logger('db')

# --- Identifier validation ---
# 白名单：只允许字母、数字、下划线，首字符不能是数字
_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

# 硬编码的表名白名单（内部可信来源）
_VALID_TABLES = frozenset({
    'creators', 'media_assets', 'task_queue', 'auth_credentials',
    'Accounts_Pool', 'SystemSettings', 'scheduled_tasks', 'assets_fts',
    'video_metadata', 'user_info_web', 'transcribe_runs'
})


def validate_identifier(name: str, field_name: str = "identifier") -> str:
    """
    校验标识符（表名、列名、索引名）安全性

    白名单正则：^[a-zA-Z_][a-zA-Z0-9_]*$

    Args:
        name: 要校验的标识符
        field_name: 字段名（用于错误信息）

    Returns:
        校验通过的标识符

    Raises:
        ValueError: 标识符包含非法字符
    """
    if not name or not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid {field_name}: {name!r} (must match ^[a-zA-Z_][a-zA-Z0-9_]*$)")
    return name


def _check_table_name(table: str) -> str:
    """校验表名，先检查硬编码白名单，再做通用校验"""
    if table in _VALID_TABLES:
        return table
    # 不在白名单中，做通用校验
    return validate_identifier(table, "table_name")


def get_table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """获取表的列名集合。表名经过白名单/正则校验，无 SQL 注入风险。"""
    safe_table = _check_table_name(table)
    # PRAGMA 不支持参数化查询，但表名已通过 _check_table_name 严格校验
    return {
        row["name"] if isinstance(row, sqlite3.Row) else row[1]
        for row in conn.execute("PRAGMA table_info(" + safe_table + ")").fetchall()
    }


# --- Resolved DB path (set once at init, reused everywhere) ---
_db_path: Optional[str] = None


def get_db_path() -> str:
    """Return the resolved DB path. Falls back to project-root/data if init_db hasn't been called."""
    global _db_path
    if _db_path is None:
        # 不依赖 core.config / common.paths，从文件位置推导项目根目录
        # src/media_tools/db/core.py -> project_root
        project_root = Path(__file__).resolve().parents[3]
        default = project_root / "data" / "media_tools.db"
        default.parent.mkdir(parents=True, exist_ok=True)
        _db_path = str(default)
    return _db_path


def _set_wal_mode(conn: sqlite3.Connection) -> None:
    """Set WAL mode if not already enabled (optimization to avoid repeated PRAGMA)."""
    try:
        cursor = conn.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        if mode.upper() != "WAL":
            conn.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.Error:
        conn.execute("PRAGMA journal_mode=WAL;")


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency – yields a connection with explicit transaction, always closes on exit."""
    conn = sqlite3.connect(get_db_path(), timeout=15.0)
    _set_wal_mode(conn)
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


# --- Per-thread connection cache ---
_thread_local = threading.local()

# --- Connection pool stats ---
_physical_connections: int = 0
_physical_connections_lock = threading.Lock()


class DBConnection:
    """SQLite 连接封装，自动管理 WAL 模式和关闭。

    默认启用线程级连接复用：通过 `_thread_local` 缓存 SQLite 连接，
    同一线程的多次 `with get_db_connection()` 复用同一个物理连接。
    设置 `keep_open=True` 时行为不变（用于长事务场景）。
    """

    _open_count = 0  # 线程级物理连接总数（用于监控）
    _open_count_lock = threading.Lock()
    _max_connections_warning = 20  # 超过此阈值警告

    def __init__(self, keep_open: bool = False, _owns_physical: bool = True):
        global _physical_connections
        self._conn = sqlite3.connect(get_db_path(), timeout=15.0)
        self._keep_open = keep_open
        self._committed = False
        self._owns_physical = _owns_physical

        # 设置 WAL 模式
        _set_wal_mode(self._conn)
        self._conn.row_factory = sqlite3.Row

        # 监控连接数（仅真实物理连接计入统计）
        if _owns_physical:
            with DBConnection._open_count_lock:
                DBConnection._open_count += 1
            with _physical_connections_lock:
                _physical_connections += 1
            if DBConnection._open_count > DBConnection._max_connections_warning:
                logger.warning(f"DB connection count high: {DBConnection._open_count}")

    @classmethod
    def _reuse_thread_local(cls) -> "DBConnection":
        """创建复用线程缓存连接的轻量包装（不拥有物理连接生命周期）。"""
        wrapper = object.__new__(cls)
        wrapper._conn = _thread_local.conn
        wrapper._keep_open = False
        wrapper._committed = False
        wrapper._owns_physical = False
        return wrapper

    def __enter__(self) -> sqlite3.Connection:
        return self._conn

    def __exit__(self, exc_type, _exc_val, _exc_tb) -> None:
        """自动 commit/rollback；仅对自有物理连接执行 close。"""
        try:
            if self._committed:
                pass
            elif exc_type is None:
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
        """显式提交（可选）"""
        self._conn.commit()
        self._committed = True

    @classmethod
    def get_stats(cls) -> dict:
        """返回连接统计"""
        return {
            "open_connections": cls._open_count,
            "physical_connections": _physical_connections,
            "max_warning": cls._max_connections_warning,
        }


def get_db_connection(keep_open: bool = False) -> DBConnection:
    """获取数据库连接的上下文管理器

    当 keep_open=False 时优先复用线程缓存连接；keep_open=True 时
    总是创建新的物理连接（长事务场景，避免干扰缓存）。
    """
    if keep_open:
        return DBConnection(keep_open=True, _owns_physical=True)

    # 尝试复用线程缓存连接
    cached = getattr(_thread_local, "conn", None)
    if cached is not None:
        try:
            cached.execute("SELECT 1")
            return DBConnection._reuse_thread_local()
        except (sqlite3.Error, Exception):
            try:
                cached.close()
            except Exception:  # noqa: defensive – 关闭缓存连接时忽略任何错误
                pass
            _thread_local.conn = None

    # 创建新连接并缓存（不拥有物理生命周期，__exit__ 时不关闭，由 shutdown/线程退出回收）
    db_conn = DBConnection(keep_open=False, _owns_physical=False)
    _thread_local.conn = db_conn._conn
    return db_conn


def reset_db_cache() -> None:
    """清除当前线程的 DB 连接缓存。

    主要用于测试场景（如 init_db 切换测试数据库时）。
    生产环境一般不需要手动调用，shutdown 时会由 `close_all_cached_connections` 处理。
    """
    close_all_cached_connections()


def close_all_cached_connections() -> int:
    """关闭当前线程缓存的连接。应在 shutdown 或线程退出时调用。
    返回关闭的连接数（0 或 1，因为 thread-local 只缓存一个连接）。"""
    global _physical_connections
    cached = getattr(_thread_local, "conn", None)
    if cached is not None:
        try:
            cached.close()
            with _physical_connections_lock:
                _physical_connections -= 1
            with DBConnection._open_count_lock:
                DBConnection._open_count -= 1
        except sqlite3.Error:
            pass
        _thread_local.conn = None
        return 1
    return 0


_COLUMN_DEF_RE = re.compile(
    r"^(TEXT|INTEGER|REAL|BOOLEAN|DATETIME|JSON|TIMESTAMP)"
    r"(\s+DEFAULT\s+('(?:[^']*|'')*'|[\w.]+|\([\w.,\s]+\)))?$",
    re.IGNORECASE,
)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_def: str) -> None:
    """确保列存在，不存在则添加（带标识符校验）"""
    safe_table = _check_table_name(table)
    safe_column = validate_identifier(column, "column_name")
    if not _COLUMN_DEF_RE.match(column_def.strip()):
        raise ValueError(f"Invalid column_def: {column_def!r}")

    existing = get_table_columns(conn, safe_table)
    if safe_column not in existing:
        cursor = conn.cursor()
        cursor.execute(f"ALTER TABLE {safe_table} ADD COLUMN {safe_column} {column_def}")


# Re-export FTS5 functions for backward compatibility
from .fts import ensure_fts_populated, update_fts_for_asset, rebuild_fts_index  # noqa: F401


def _ensure_fts_table(conn: sqlite3.Connection) -> None:
    """Create assets_fts FTS5 virtual table if it doesn't exist."""
    from .fts import _ensure_fts_table as _ensure
    _ensure(conn)

def init_db(db_path: Union[str, Path]):
    """
    初始化所有数据表（启动时调用一次）

    Args:
        db_path: 数据库文件路径 (通常为 media_tools.db)
    """
    global _db_path
    db_path = Path(db_path)
    new_path = str(db_path)

    # DB 路径变更时清除线程缓存，避免旧连接指向已废弃的数据库
    if _db_path is not None and _db_path != new_path:
        reset_db_cache()

    _db_path = new_path

    # 兼容性处理：如果旧版 douyin_users.db 存在且新版不存在，自动重命名
    old_db_path = db_path.parent / "douyin_users.db"
    if old_db_path.exists() and not db_path.exists():
        try:
            logger.info(f"发现旧版数据库 {old_db_path.name}，正在迁移至 {db_path.name}...")
            os.rename(old_db_path, db_path)
        except (OSError, PermissionError) as e:
            logger.error(f"重命名旧版数据库失败: {e}")

    # 确保父目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = None
    try:
        conn = sqlite3.connect(str(db_path), timeout=15.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        cursor = conn.cursor()

        # 1. 创作者域 (Creator Domain)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS creators (
            uid TEXT PRIMARY KEY,
            sec_user_id TEXT,
            nickname TEXT,
            avatar TEXT,
            bio TEXT,
            homepage_url TEXT,
            platform TEXT DEFAULT 'douyin',
            sync_status TEXT DEFAULT 'active',
            last_fetch_time DATETIME
        )
        """)

        # 迁移：为已存在的表添加 homepage_url 字段
        try:
            cursor.execute("ALTER TABLE creators ADD COLUMN homepage_url TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # 字段已存在

        # 2. 资产域 (Asset Domain)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS media_assets (
            asset_id TEXT PRIMARY KEY,
            creator_uid TEXT,
            source_url TEXT,
            title TEXT,
            duration INTEGER,

            video_path TEXT,
            video_status TEXT DEFAULT 'pending',

            transcript_path TEXT,
            transcript_status TEXT DEFAULT 'none',

            create_time DATETIME,
            update_time DATETIME
        )
        """)

        # 3. 任务域 (Task Domain)
        cursor.execute("""
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
            end_time DATETIME
        )
        """)

        # 4. 认证域 (Auth Domain)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS auth_credentials (
            platform TEXT PRIMARY KEY,
            auth_data JSON,
            is_valid BOOLEAN DEFAULT 1,
            last_check_time DATETIME
        )
        """)

        # 5. 账号池 (Account Pool) — 原散落在 settings.py / f2_helper.py
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Accounts_Pool (
            account_id TEXT PRIMARY KEY,
            platform TEXT,
            cookie_data TEXT,
            status TEXT DEFAULT 'active',
            last_used TIMESTAMP,
            create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 6. 系统设置 (System Settings) — 原散落在 settings.py
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS SystemSettings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        # 7. 定时任务 (Scheduled Tasks) — 原散落在 scheduler.py
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            task_id TEXT PRIMARY KEY,
            task_type TEXT,
            cron_expr TEXT,
            enabled BOOLEAN DEFAULT 1,
            create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 8. 视频元数据 (Video Metadata) — 由 douyin downloader 管理
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS video_metadata (
            aweme_id TEXT PRIMARY KEY,
            uid TEXT NOT NULL,
            nickname TEXT,
            desc TEXT,
            create_time INTEGER,
            duration INTEGER,
            digg_count INTEGER DEFAULT 0,
            comment_count INTEGER DEFAULT 0,
            collect_count INTEGER DEFAULT 0,
            share_count INTEGER DEFAULT 0,
            play_count INTEGER DEFAULT 0,
            local_filename TEXT,
            file_size INTEGER,
            fetch_time INTEGER
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_video_uid ON video_metadata(uid)")

        # 9. 用户信息缓存 (User Info Cache) — 由 F2 库管理
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_info_web (
            uid TEXT PRIMARY KEY,
            sec_user_id TEXT,
            nickname TEXT,
            avatar TEXT
        )
        """)

        # 10. 转写运行记录 (Transcribe Runs) — 第三阶段：可恢复转写流水线
        # 每行 = 某个视频在某个通义账号上的一次完整转写尝试。
        # stage 推进顺序：queued -> uploaded -> transcribing -> exporting -> downloading -> saved
        # 上传后失败的 run（stage in RESUMABLE_STAGES）允许下次同 asset+account 的尝试续做，
        # 跳过 token/get + upload，直接从 poll/export/download 继续，避免烧额度。
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transcribe_runs (
            run_id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            video_path TEXT NOT NULL,
            account_id TEXT NOT NULL,
            task_id TEXT,
            stage TEXT NOT NULL DEFAULT 'queued',
            record_id TEXT,
            gen_record_id TEXT,
            batch_id TEXT,
            export_task_id TEXT,
            export_url TEXT,
            transcript_path TEXT,
            last_error TEXT,
            error_stage TEXT,
            error_type TEXT,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)

        # 创建索引优化查询
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_assets_creator ON media_assets(creator_uid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_assets_video_status ON media_assets(video_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_assets_transcript_status ON media_assets(transcript_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_queue_status ON task_queue(status)")
        # 复合索引：覆盖 creator_transcribe_worker 的高频查询
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_media_assets_creator_status "
            "ON media_assets(creator_uid, video_status, transcript_status)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_queue_update_time ON task_queue(update_time)")
        # transcribe_runs：find_resumable 主查询走 (asset_id, account_id, stage)；
        # find_saved_for_asset 走 (asset_id, stage)；运维排查失败走 (stage, updated_at)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_transcribe_runs_asset_account "
            "ON transcribe_runs(asset_id, account_id, stage)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_transcribe_runs_asset_stage "
            "ON transcribe_runs(asset_id, stage)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_transcribe_runs_stage_updated "
            "ON transcribe_runs(stage, updated_at)"
        )

        _ensure_column(conn, "task_queue", "update_time", "DATETIME")
        _ensure_column(conn, "task_queue", "cancel_requested", "INTEGER DEFAULT 0")
        _ensure_column(conn, "task_queue", "auto_retry", "INTEGER DEFAULT 0")
        _ensure_column(conn, "creators", "platform", "TEXT DEFAULT 'douyin'")
        _ensure_column(conn, "creators", "sync_status", "TEXT DEFAULT 'active'")
        _ensure_column(conn, "creators", "last_fetch_time", "DATETIME")
        _ensure_column(conn, "creators", "auto_sync", "BOOLEAN DEFAULT 0")
        _ensure_column(conn, "creators", "avatar", "TEXT")
        _ensure_column(conn, "creators", "bio", "TEXT")
        _ensure_column(conn, "Accounts_Pool", "remark", "TEXT DEFAULT ''")
        _ensure_column(conn, "Accounts_Pool", "auth_state_path", "TEXT DEFAULT ''")
        _ensure_column(conn, "media_assets", "source_url", "TEXT")
        _ensure_column(conn, "media_assets", "is_read", "BOOLEAN DEFAULT 0")
        _ensure_column(conn, "media_assets", "is_starred", "BOOLEAN DEFAULT 0")
        _ensure_column(conn, "media_assets", "folder_path", "TEXT DEFAULT ''")
        _ensure_column(conn, "media_assets", "create_time", "DATETIME")
        _ensure_column(conn, "media_assets", "update_time", "DATETIME")
        _ensure_column(conn, "media_assets", "transcript_preview", "TEXT")
        _ensure_column(conn, "media_assets", "transcript_text", "TEXT")
        # 第二阶段：视频级状态治理 —— 失败可见、可重试、可定位
        _ensure_column(conn, "media_assets", "transcript_last_error", "TEXT")
        _ensure_column(conn, "media_assets", "transcript_error_type", "TEXT")
        _ensure_column(conn, "media_assets", "transcript_retry_count", "INTEGER DEFAULT 0")
        _ensure_column(conn, "media_assets", "transcript_failed_at", "DATETIME")
        _ensure_column(conn, "media_assets", "last_task_id", "TEXT")
        _ensure_column(conn, "media_assets", "source_platform", "TEXT")

        # FTS5 全文索引（用于素材搜索加速）
        _ensure_fts_table(conn)

        conn.commit()
        logger.info("数据库初始化完成（含全部 9 张表）")
    except (sqlite3.Error, OSError) as e:
        logger.error(f"初始化数据库失败: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

    _migrate_legacy_auth_files(db_path.parent.parent)


def _migrate_legacy_auth_files(project_root: Path) -> None:
    old_auth_dir = project_root / ".auth"
    new_auth_dir = project_root / "data" / "auth"
    if old_auth_dir.exists() and old_auth_dir.is_dir() and any(old_auth_dir.iterdir()):
        new_auth_dir.mkdir(parents=True, exist_ok=True)
        for old_file in old_auth_dir.iterdir():
            if not old_file.is_file():
                continue
            new_file = new_auth_dir / old_file.name
            if new_file.exists():
                continue
            try:
                import shutil
                shutil.move(str(old_file), str(new_file))
                logger.info(f"迁移认证文件: {old_file} → {new_file}")
            except (OSError, PermissionError) as e:
                logger.warning(f"迁移认证文件失败: {old_file} → {new_file}: {e}")
        remaining = list(old_auth_dir.iterdir())
        if not remaining:
            try:
                old_auth_dir.rmdir()
                logger.info(f"已删除空目录: {old_auth_dir}")
            except OSError:
                pass

    _migrate_single_file(project_root / "accounts.json", new_auth_dir / "accounts.json")
    _migrate_legacy_artifacts(project_root)


def _migrate_single_file(old_path: Path, new_path: Path) -> None:
    if not old_path.exists() or not old_path.is_file():
        return
    if new_path.exists():
        return
    try:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.move(str(old_path), str(new_path))
        logger.info(f"迁移文件: {old_path} → {new_path}")
    except (OSError, PermissionError) as e:
        logger.warning(f"迁移文件失败: {old_path} → {new_path}: {e}")


def _migrate_legacy_artifacts(project_root: Path) -> None:
    old_dir = project_root / "artifacts"
    new_dir = project_root / "data" / "logs"
    if not old_dir.exists() or not old_dir.is_dir():
        return
    if not any(old_dir.iterdir()):
        return
    new_dir.mkdir(parents=True, exist_ok=True)
    for item in old_dir.iterdir():
        if not item.is_dir():
            continue
        target = new_dir / item.name
        if target.exists():
            continue
        try:
            import shutil
            shutil.move(str(item), str(target))
            logger.info(f"迁移日志目录: {item} → {target}")
        except (OSError, PermissionError) as e:
            logger.warning(f"迁移日志目录失败: {item} → {target}: {e}")
    remaining = list(old_dir.iterdir())
    if not remaining:
        try:
            old_dir.rmdir()
            logger.info(f"已删除空目录: {old_dir}")
        except OSError:
            pass


# --- Path helpers (shared across routers & downloader) ---

# Re-export path utilities for backward compatibility
from .path_utils import resolve_safe_path, resolve_query_value, local_asset_id  # noqa: F401


# --- 数据库优化工具 ---

def vacuum_db() -> None:
    """执行数据库 VACUUM 操作，回收空间并优化索引。
    
    建议在以下时机调用：
    1. 系统启动时（可选，会增加启动时间）
    2. 定期任务清理后
    3. 大规模数据删除后
    
    SQLite 的 VACUUM 命令会重建数据库文件，消除碎片，
    并优化数据库结构，提升后续读写性能。
    """
    import time
    start_time = time.time()
    with get_db_connection() as conn:
        conn.execute("VACUUM")
    elapsed = time.time() - start_time
    logger.info(f"Database VACUUM completed in {elapsed:.2f} seconds")


# --- 状态枚举化支持 ---

VIDEO_STATUS_MAP = {
    'pending': 0,
    'downloading': 1,
    'downloaded': 2,
    'failed': 3,
}

TRANSCRIPT_STATUS_MAP = {
    'none': 0,
    'transcribing': 1,
    'completed': 2,
    'failed': 3,
}

TASK_STATUS_MAP = {
    'PENDING': 0,
    'RUNNING': 1,
    'COMPLETED': 2,
    'FAILED': 3,
    'CANCELLED': 4,
}


def video_status_to_code(status: str) -> int:
    """将视频状态字符串转换为枚举码"""
    return VIDEO_STATUS_MAP.get(status, 0)


def video_status_from_code(code: int) -> str:
    """将视频状态枚举码转换为字符串"""
    return next((k for k, v in VIDEO_STATUS_MAP.items() if v == code), 'pending')


def transcript_status_to_code(status: str) -> int:
    """将转写状态字符串转换为枚举码"""
    return TRANSCRIPT_STATUS_MAP.get(status, 0)


def transcript_status_from_code(code: int) -> str:
    """将转写状态枚举码转换为字符串"""
    return next((k for k, v in TRANSCRIPT_STATUS_MAP.items() if v == code), 'none')


def task_status_to_code(status: str) -> int:
    """将任务状态字符串转换为枚举码"""
    return TASK_STATUS_MAP.get(status, 0)


def task_status_from_code(code: int) -> str:
    """将任务状态枚举码转换为字符串"""
    return next((k for k, v in TASK_STATUS_MAP.items() if v == code), 'PENDING')


if __name__ == "__main__":
    db_path = "data/media_tools.db"
    init_db(db_path)
    logger.info("DB Init success")

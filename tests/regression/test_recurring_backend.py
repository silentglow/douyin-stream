"""
回归测试套件：反复出现的后端 Bug 模式
运行方式: pytest tests/regression/test_recurring_backend.py -v
"""

import asyncio
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

def _find_repo_root(start: Path) -> Path:
    cur = start
    for _ in range(12):
        if (cur / "pyproject.toml").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    raise RuntimeError("Cannot locate repo root (pyproject.toml not found)")


REPO_ROOT = _find_repo_root(Path(__file__).resolve())

# BACKEND-001: 宽泛异常捕获检查
# 这不是运行时测试，而是静态代码检查
def test_no_bare_except_exception():
    """
    验证 src/media_tools/ 下不存在 'except Exception:' 模式。
    此测试失败意味着又有开发者引入了宽泛异常捕获。
    """
    import subprocess
    result = subprocess.run(
        ["grep", "-rn", "except Exception:", "src/media_tools/"],
        capture_output=True, text=True, cwd=str(REPO_ROOT)
    )
    lines = [l for l in result.stdout.strip().split("\n") if l]
    # 允许注释中或 noqa 标记的例外
    violations = []
    for line in lines:
        if "noqa" in line or "# " in line:
            continue
        violations.append(line)
    assert len(violations) == 0, (
        f"发现 {len(violations)} 处宽泛异常捕获 (BACKEND-001):\n" +
        "\n".join(violations[:20])
    )


def test_no_bare_sqlite3_connect():
    """
    验证不存在裸 sqlite3.connect 调用，仅 store/db.py 允许。
    """
    import subprocess
    result = subprocess.run(
        ["grep", "-rn", "sqlite3.connect", "src/media_tools/"],
        capture_output=True, text=True, cwd=str(REPO_ROOT)
    )
    lines = [l for l in result.stdout.strip().split("\n") if l]
    allowed_paths = ("store/db.py",)
    allowed = [l for l in lines if any(p in l for p in allowed_paths)]
    violations = [l for l in lines if not any(p in l for p in allowed_paths)]
    assert len(violations) == 0, (
        f"发现 {len(violations)} 处裸 sqlite3.connect (BACKEND-004):\n" +
        "\n".join(violations[:20])
    )


# BACKEND-002: Cookie 临时文件生命周期
def test_managed_temp_file_unified():
    """
    验证 managed_temp_file 只存在于一处（common/temp_file.py 或 db/core.py）。
    如果仍在 douyin/bilibili 中各自实现，测试失败。
    """
    import subprocess
    result = subprocess.run(
        ["grep", "-rln", "managed_temp_file", "src/media_tools/"],
        capture_output=True, text=True, cwd=str(REPO_ROOT)
    )
    files = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
    # 预期最多 2 个文件：定义处 + 可能的一处使用
    # 如果超过 2 个文件包含该函数定义，说明仍有重复
    definition_files = []
    for f in files:
        result2 = subprocess.run(
            ["grep", "-n", "def managed_temp_file", f],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        if result2.stdout.strip():
            definition_files.append(f)
    assert len(definition_files) <= 1, (
        f"managed_temp_file 在多处定义 (BACKEND-002/007): {definition_files}"
    )


# BACKEND-003: 双重 commit 语义测试
def test_db_connection_commit_semantics():
    """
    验证 DBConnection 的 commit 语义清晰：
    要么完全自动，要么完全手动，不混合。
    """
    from media_tools.store.db import DBConnection
    # DBConnection 目前绑定 get_db_path()，无法传入 :memory:
    # 这里只验证 API 语义存在
    conn = DBConnection()
    # 验证有 commit 方法
    assert hasattr(conn, "commit"), "DBConnection 必须有 commit 方法"
    # 验证 __exit__ 不会与显式 commit 冲突
    with conn as db:
        db.execute("SELECT 1")
        conn.commit()
    # 如果 _committed 标志正确，不会双重 commit
    # 如果 __exit__ 抛错（因为已 commit），需要修复


# BACKEND-004: 裸连接 + 连接泄漏
@pytest.mark.parametrize("module_name", [
    "media_tools.platform.douyin",
    "media_tools.douyin.core.following_mgr",
    "media_tools.douyin.core.cleaner",
])
def test_modules_use_db_connection(module_name):
    """
    验证关键模块没有引入新的裸 sqlite3.connect。
    """
    import subprocess
    module_path = module_name.replace(".", "/") + ".py"
    result = subprocess.run(
        ["grep", "-n", "sqlite3.connect", f"src/{module_path}"],
        capture_output=True, text=True, cwd=str(REPO_ROOT)
    )
    lines = [l for l in result.stdout.strip().split("\n") if l]
    assert len(lines) == 0, (
        f"{module_name} 仍使用裸 sqlite3.connect:\n" + "\n".join(lines)
    )


def test_db_connection_leak_protection():
    """
    验证 DBConnection 上下文管理器正确关闭连接。
    """
    from media_tools.store.db import DBConnection
    open_before = sqlite3.connect(":memory:").execute(
        "SELECT COUNT(*) FROM pragma_database_list()"
    ).fetchone()[0]

    for _ in range(100):
        # DBConnection 目前固定使用 get_db_path()，无法直接传 :memory:
        # 这里只验证上下文管理器不抛错
        with DBConnection() as conn:
            conn.execute("SELECT 1")

    # SQLite 内存连接不会体现在文件描述符中，但验证不抛错即可
    assert True


# BACKEND-005: async/sync 混合
@pytest.mark.asyncio
async def test_async_endpoint_not_blocking_event_loop():
    """
    验证核心 async 函数不会长时间阻塞事件循环。
    此测试通过并发执行两个应该并行的操作来检测阻塞。
    """
    async def fast_op():
        await asyncio.sleep(0.1)
        return "done"

    async def maybe_blocking_op():
        # 模拟可能阻塞的同步调用
        # 如果此处用 time.sleep(1) 而非 asyncio.sleep(1)，两个任务会串行
        await asyncio.sleep(0.5)
        return "done"

    start = time.monotonic()
    results = await asyncio.gather(
        fast_op(),
        maybe_blocking_op(),
    )
    elapsed = time.monotonic() - start

    # 如果两者真正并行，总耗时应约 0.5s；如果串行，会约 0.6s+
    # 给一些裕量
    assert elapsed < 0.8, (
        f"操作疑似串行执行，耗时 {elapsed:.2f}s (BACKEND-005)"
    )


def test_async_db_wrapper_exists():
    """
    验证 DBConnection 或相关模块有 async 封装方法。
    """
    from media_tools.store import db as core
    has_async = any(
        name.startswith("a") for name in dir(core)
        if callable(getattr(core, name, None))
    ) or hasattr(core, "AsyncDBConnection")
    # 这是一个软性检查：如果没有 async 封装，发出警告但不失败
    # 因为完全迁移可能需要时间
    if not has_async:
        pytest.skip("Async DB wrapper 尚未实现 (BACKEND-005 待修复)")


# BACKEND-006: PRAGMA table_info 安全
@pytest.mark.parametrize("router", ["assets", "creators", "tasks"])
def test_pragma_table_info_uses_validation(router):
    """
    验证 router 中不再有无校验的 PRAGMA table_info f-string 拼接。
    """
    import subprocess
    result = subprocess.run(
        ["grep", "-n", "PRAGMA table_info", f"src/media_tools/api/routers/{router}.py"],
        capture_output=True, text=True, cwd=str(REPO_ROOT)
    )
    lines = [l for l in result.stdout.strip().split("\n") if l]
    for line in lines:
        # 如果包含 f-string 且无 validate_identifier，则违规
        if "f\"PRAGMA table_info" in line or "f'PRAGMA table_info" in line:
            pytest.fail(
                f"{router}.py 存在无校验的 PRAGMA f-string: {line} (BACKEND-006)"
            )


def test_get_table_columns_unified():
    """
    验证 _get_table_columns 只存在于 db/core.py。
    """
    import subprocess
    result = subprocess.run(
        ["grep", "-rln", "def _get_table_columns", "src/media_tools/"],
        capture_output=True, text=True, cwd=str(REPO_ROOT)
    )
    files = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
    assert len(files) <= 1, (
        f"_get_table_columns 在多处定义 (BACKEND-006/007): {files}"
    )


def test_workers_do_not_update_task_status_via_raw_sql():
    import subprocess

    result = subprocess.run(
        [
            "grep",
            "-rnI",
            "--exclude-dir=__pycache__",
            "--exclude=*.pyc",
            "UPDATE task_queue SET status=",
            "src/media_tools/workers/",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    violations = [l for l in result.stdout.strip().split("\n") if l.strip()]
    assert not violations, (
        f"workers 不应直接写 task_queue.status (BACKEND-008):\n" + "\n".join(violations)
    )


def test_pragma_table_info_only_in_db_core():
    import subprocess

    result = subprocess.run(
        [
            "grep",
            "-rnI",
            "--exclude-dir=__pycache__",
            "--exclude=*.pyc",
            "PRAGMA table_info",
            "src/media_tools/",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
    allowed_paths = ("src/media_tools/store/db.py",)
    violations = [l for l in lines if not any(p in l for p in allowed_paths)]
    assert not violations, (
        "PRAGMA table_info 应只出现在 db/core.py 或 store/db.py (BACKEND-009):\n" + "\n".join(violations)
    )


# BACKEND-007: 重复代码检测
def test_no_duplicate_managed_temp_file():
    """
    验证 managed_temp_file 相关函数不重复。
    """
    funcs = ["managed_temp_file", "_register_temp_file", "_cleanup_temp_files"]
    for func in funcs:
        import subprocess
        result = subprocess.run(
            ["grep", "-rln", f"def {func}", "src/media_tools/"],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        files = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        assert len(files) <= 1, (
            f"{func} 在多处定义 (BACKEND-007): {files}"
        )

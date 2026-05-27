"""REFACTOR 2026-05 任务 4 回归测试：配置层级 + cache TTL。

约束的核心：
1. `_settings_cache_ttl` 必须 ≤ 30 秒（防止回滚到旧的 300 秒）
2. DB 直接改 setting 后，TTL+1 秒内 AppConfig.get 必须能读到新值
3. `os.environ.get` 在 src/media_tools/ 内只能出现在 bootstrap 允许列表里
"""

from __future__ import annotations

import time
from pathlib import Path

from media_tools.core.config import (
    _get_system_setting,
    _invalidate_settings_cache,
    _set_system_setting,
    _settings_cache,
    _settings_cache_ttl,
)
from media_tools.store.db import get_db_connection

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_settings_cache_ttl_is_bounded():
    """TTL 必须 ≤ 30 秒（卡 300 秒回滚）。"""
    assert _settings_cache_ttl <= 30, (
        f"_settings_cache_ttl={_settings_cache_ttl} 太长；历史教训：300 秒导致 "
        f"setting 修改后用户长时间感知不到（如 export_format=pdf 的事故）。"
    )


def test_settings_change_via_api_invalidates_cache_immediately():
    """通过 _set_system_setting 改值（API 路径）必须立刻清缓存。"""
    key = "_test_layer_key_api"

    _invalidate_settings_cache()
    _set_system_setting(key, "v1")

    # 首次读 → 缓存填充
    assert _get_system_setting(key) == "v1"
    assert key in _settings_cache

    # 通过 API 改值，缓存必须被清掉，下次读立刻看到新值
    _set_system_setting(key, "v2")
    assert _get_system_setting(key) == "v2"

    # 清理
    with get_db_connection() as conn:
        conn.execute("DELETE FROM SystemSettings WHERE key=?", (key,))
        conn.commit()
    _invalidate_settings_cache()


def test_settings_change_in_db_visible_within_ttl_plus_buffer():
    """绕过 API 直接写 DB 后，等待 TTL+1 秒，AppConfig 必须能读到新值。

    这是 v2026-05 之前坑用户的具体场景：从 UI 设了 setting 后，
    后台 worker 长时间用旧值。"""
    key = "_test_layer_key_db_direct"

    _invalidate_settings_cache()
    _set_system_setting(key, "old_value")
    assert _get_system_setting(key) == "old_value"

    # 绕过 _set_system_setting 直接改 DB（模拟非 API 路径）
    with get_db_connection() as conn:
        conn.execute("UPDATE SystemSettings SET value=? WHERE key=?", ("new_value", key))
        conn.commit()

    # 缓存内仍是 old_value（TTL 未过）
    assert _get_system_setting(key) == "old_value"

    # 等待 TTL 过期
    time.sleep(_settings_cache_ttl + 1)

    # 缓存过期，应读到新值
    assert _get_system_setting(key) == "new_value", (
        "TTL 过期后 AppConfig 仍读到旧值；说明 _get_system_setting 的缓存过期逻辑坏了"
    )

    # 清理
    with get_db_connection() as conn:
        conn.execute("DELETE FROM SystemSettings WHERE key=?", (key,))
        conn.commit()
    _invalidate_settings_cache()


# ═════════════════════════════════════════════════════════════════
# 散落 os.environ.get 防回滚白名单
# ═════════════════════════════════════════════════════════════════

# 允许直接读 os.environ 的文件——bootstrap / config loader / OS 系统级
ENV_ALLOWED_FILES = {
    "src/media_tools/core/config.py",  # 主 config loader
    "src/media_tools/transcribe/config.py",  # transcribe config loader
    "src/media_tools/common/runtime.py",  # env_flag helper（被 transcribe/config 调用）
    "src/media_tools/logger.py",  # 日志 bootstrap（早于 AppConfig）
    "src/media_tools/douyin/core/f2_helper.py",  # OS-level TMPDIR/TEMP（非项目配置）
    "src/media_tools/douyin/core/config_mgr.py",  # MEDIA_TOOLS_PROJECT_ROOT 启动 override
}


def test_no_scattered_os_environ_get():
    """`os.environ.get` 仅允许出现在白名单文件，其它路径必须走 AppConfig。"""
    import subprocess

    result = subprocess.run(
        ["grep", "-rln", r"os\.environ\.get\|os\.getenv", "src/media_tools/", "--include=*.py"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    found_files = {line.strip() for line in result.stdout.strip().split("\n") if line.strip()}

    violations = found_files - ENV_ALLOWED_FILES
    assert not violations, (
        "以下文件不允许直接读环境变量（应走 AppConfig）：\n"
        + "\n".join(f"  - {v}" for v in sorted(violations))
        + f"\n\n如确认是合法的 bootstrap 文件，请加到 {__file__} 的 ENV_ALLOWED_FILES 白名单。"
    )

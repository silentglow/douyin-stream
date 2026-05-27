"""REFACTOR 2026-05 任务 4 e2e 回归测试：specific export_format 事故防回归。

历史背景：用户在 UI 把 `export_format` 从 `md` 改成 `pdf` 后，由于 _settings_cache_ttl=300 秒，
后台启动的转写任务 5 分钟内仍按旧值 `md` 走（再加上 pypdf 没装导致 PDF 提取失败显示空白）。

本测试锁定：通过 `_set_system_setting` 改 export_format 后，下一次 `get_app_config()` 的
`pipeline_export_format` 必须立刻反映新值，不依赖 TTL 过期。
"""

from __future__ import annotations

import pytest

from media_tools.core.config import (
    _invalidate_settings_cache,
    _set_system_setting,
    get_app_config,
)
from media_tools.store.db import get_db_connection


@pytest.fixture
def isolate_settings():
    """每个测试前后清理 SystemSettings.export_format 并清缓存。"""
    _invalidate_settings_cache()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM SystemSettings WHERE key=?", ("export_format",))
        conn.commit()
    _invalidate_settings_cache()

    yield

    with get_db_connection() as conn:
        conn.execute("DELETE FROM SystemSettings WHERE key=?", ("export_format",))
        conn.commit()
    _invalidate_settings_cache()


def test_export_format_change_visible_immediately(isolate_settings):
    """改 export_format 后立刻 get_app_config 必须看到新值。"""
    # 默认值（来自 _RUNTIME_DEFAULTS）
    cfg = get_app_config()
    default_format = cfg.pipeline_export_format
    assert default_format == "md", f"默认 export_format 应为 md，实际 {default_format}"

    # 改到 pdf
    _set_system_setting("export_format", "pdf")
    cfg2 = get_app_config()
    assert cfg2.pipeline_export_format == "pdf", (
        "改 export_format=pdf 后 AppConfig 仍报旧值；这正是 v2026-05 之前坑用户的场景"
    )

    # 改回 md
    _set_system_setting("export_format", "md")
    cfg3 = get_app_config()
    assert cfg3.pipeline_export_format == "md"


def test_export_format_invalid_value_rejected_at_api_layer():
    """API 层 settings.py:206 已有白名单校验，仅 md/docx/pdf/srt/txt 五种。
    这条测试确认那个校验仍在，避免回归。"""
    import inspect

    from media_tools.api.routers import settings as settings_router

    src = inspect.getsource(settings_router)
    # 必须含 export_format 的合法值校验
    assert "md" in src and "docx" in src and "pdf" in src and "srt" in src and "txt" in src, (
        "settings 路由应保留 export_format 合法值白名单（md/docx/pdf/srt/txt）"
    )
    assert "export_format must be one of" in src, "settings 路由应保留 export_format 不合法时的 400 错误"

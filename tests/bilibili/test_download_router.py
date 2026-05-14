from __future__ import annotations

from media_tools.transcribe.download_router import resolve_platform


def test_resolve_platform_bilibili() -> None:
    assert resolve_platform("https://space.bilibili.com/123") == "bilibili"


def test_resolve_platform_douyin() -> None:
    assert resolve_platform("https://www.douyin.com/user/xxx") == "douyin"


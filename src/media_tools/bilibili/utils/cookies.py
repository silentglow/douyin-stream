from __future__ import annotations

from media_tools.core.cookie_manager import get_cookie_manager


def get_bilibili_cookie_string() -> str:
    return get_cookie_manager().get_cookie("bilibili")

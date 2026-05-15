from __future__ import annotations
"""抖音核心工具函数"""
from typing import Optional, Union

import asyncio
import concurrent.futures
import logging
import re
from pathlib import Path

from .config_mgr import get_config

logger = logging.getLogger(__name__)


def _clean_nickname(name: str) -> str:
    """清洗昵称，移除非法字符和常见后缀"""
    if not name:
        return ""
    suffixes = ["的抖音", "的Douyin", " - 抖音", " - Douyin", " | 抖音", " | Douyin"]
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    name = re.sub(r'[<>"/\\|?*]', '', name).strip()
    return name


def _run_async_coro(coro):
    """在同步代码中安全运行异步协程，兼容已有事件循环的场景（如 FastAPI）。"""
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        pass
    return asyncio.run(coro)


def _resolve_sec_user_id(url: str) -> Optional[str]:
    """将用户主页链接规范化为 canonical sec_user_id。"""
    raw_match = re.search(r'/user/([^/"\s?]+)', url)
    raw_value = raw_match.group(1) if raw_match else ''
    if raw_value.startswith('MS4w'):
        return raw_value

    async def _fetch() -> str:
        from f2.apps.douyin.utils import SecUserIdFetcher
        return await SecUserIdFetcher.get_sec_user_id(url)

    try:
        resolved = _run_async_coro(_fetch())
        if resolved and resolved.startswith('MS4w'):
            return resolved
    except (RuntimeError, OSError, ValueError) as exc:
        logger.warning(f"sec_user_id 规范化失败: {exc}")

    if raw_value:
        logger.error('当前链接未包含 sec_user_id；请优先使用 sec_user_id 形式的用户主页链接。')
    else:
        logger.error('无法从链接中提取用户标识。')
    return None


def _get_skill_dir() -> Path:
    """获取项目根目录"""
    return get_config().project_root

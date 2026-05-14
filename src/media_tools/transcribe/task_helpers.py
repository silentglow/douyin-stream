from __future__ import annotations
"""Pipeline 任务辅助函数"""

import asyncio
import inspect
import logging
from pathlib import Path
from typing import Any, Optional, Union

from media_tools.core import background
from media_tools.transcribe.media_extensions import MEDIA_EXTENSIONS

logger = logging.getLogger(__name__)

MIN_VIDEO_BYTES = 10240  # 10KB


async def call_progress(update_progress_fn, progress: float, msg: str, stage: str = "", pipeline_progress: Optional[dict] = None) -> None:
    if not update_progress_fn:
        return
    try:
        if stage or pipeline_progress:
            try:
                result = update_progress_fn(progress, msg, stage, pipeline_progress)
            except TypeError:
                try:
                    result = update_progress_fn(progress, msg, stage)
                except TypeError:
                    result = update_progress_fn(progress, msg)
        else:
            result = update_progress_fn(progress, msg)
        if inspect.isawaitable(result):
            await result
    except (TypeError, ValueError, RuntimeError) as e:
        logger.error(f"update_progress_fn 内部抛错: {e}")


def create_managed_task(coro) -> asyncio.Task[Any]:
    """创建受管理的后台任务，自动注册到全局 registry 并在 done 时检查异常。"""
    task = background.create(coro)

    def _on_done(t: asyncio.Task[Any]) -> None:
        if t.cancelled() or not t.done():
            return
        exc = t.exception()
        if exc is not None:
            logger.error(f"Background task failed: {exc!r}")

    task.add_done_callback(_on_done)
    return task


def filter_supported_media_paths(file_paths: list[str]) -> list[Path]:
    valid_paths: list[Path] = []
    for file_path in file_paths:
        path = Path(file_path)
        if path.suffix.lower() not in MEDIA_EXTENSIONS:
            continue
        try:
            # 单次 stat 既验证存在又取大小，避开 exists() / stat() 之间的 TOCTOU
            st = path.stat()
        except OSError:
            continue
        if st.st_size >= MIN_VIDEO_BYTES:
            valid_paths.append(path)
    return valid_paths

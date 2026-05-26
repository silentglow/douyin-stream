from __future__ import annotations
"""后台 asyncio.Task 统一 registry。

历史上 `_background_tasks: set[asyncio.Task]` 在 task_state、auto_retry、
websocket_manager、task_helpers 各有一份，shutdown 时无统一入口取消，
导致重启服务时可能丢失 in-flight 任务或留下 zombie 协程。

本模块提供：
- `register(task)` / `create(coro)`：把任务挂入全局集合，done 时自动移除
- `active_count()` / `snapshot()`：用于 /metrics 和健康检查
- `cancel_all()`：lifespan shutdown 时一次性取消并等待
"""

import asyncio
import logging
from typing import Any, Coroutine, Optional

logger = logging.getLogger(__name__)

_tasks: set[asyncio.Task[Any]] = set()

# 主 FastAPI 事件循环引用，供 APScheduler 线程等"非主 loop 上下文"通过
# `asyncio.run_coroutine_threadsafe(coro, get_main_loop())` 把协程派发回主 loop，
# 这样产生的 Task 才能被 `_active_tasks` 注册的 cancel 路径正确取消。
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """在 FastAPI lifespan 启动期内调用一次，记录主事件循环。"""
    global _main_loop
    _main_loop = loop


def get_main_loop() -> Optional[asyncio.AbstractEventLoop]:
    """获取主事件循环；尚未初始化时返回 None，由调用方决定如何降级。"""
    return _main_loop


def register(task: asyncio.Task[Any]) -> asyncio.Task[Any]:
    """注册已存在的 Task；done 时自动从 registry 移除。"""
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


def create(coro: Coroutine[Any, Any, Any], *, name: Optional[str] = None) -> asyncio.Task[Any]:
    """`asyncio.create_task` 的快捷封装，自动 register。"""
    task = asyncio.create_task(coro, name=name) if name else asyncio.create_task(coro)
    return register(task)


def active_count() -> int:
    """当前未完成任务数。"""
    return sum(1 for t in _tasks if not t.done())


def total_count() -> int:
    """registry 中的任务数（含已完成但回调尚未执行的）。"""
    return len(_tasks)


def snapshot() -> list[asyncio.Task[Any]]:
    """返回当前任务列表的浅拷贝。"""
    return list(_tasks)


async def cancel_all(timeout: float = 5.0) -> int:
    """取消所有未完成任务并等待，返回被取消的数量。

    超时后剩余仍在运行的任务由调用方决定如何处理（通常是放弃等待）。
    """
    # 先快照，避免迭代期间 done callback 修改 _tasks 导致 RuntimeError
    snapshot = list(_tasks)
    pending = [t for t in snapshot if not t.done()]
    if not pending:
        return 0
    for t in pending:
        t.cancel()
    try:
        await asyncio.wait_for(
            asyncio.gather(*pending, return_exceptions=True),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        still_running = sum(1 for t in pending if not t.done())
        logger.warning(f"cancel_all timed out after {timeout}s; {still_running} task(s) still running")
    return len(pending)

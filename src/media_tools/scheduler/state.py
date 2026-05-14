import asyncio
import logging
import sqlite3
from datetime import datetime
from media_tools.core import background
from media_tools.douyin.core.cancel_registry import clear_cancel_event
from media_tools.store.db import get_db_connection
from media_tools.scheduler.retry import schedule_auto_retry

logger = logging.getLogger(__name__)

_active_tasks: dict[str, asyncio.Task] = {}


async def _task_heartbeat(task_id: str, interval: int = 30):
    while True:
        await asyncio.sleep(interval)
        try:
            with get_db_connection() as conn:
                conn.execute(
                    "UPDATE task_queue SET update_time = ? WHERE task_id = ? AND status IN ('PENDING', 'RUNNING')",
                    (datetime.now().isoformat(), task_id),
                )
        except (sqlite3.Error, OSError) as e:
            logger.warning(f"heartbeat DB更新失败 task_id={task_id}: {e}")


def _register_background_task(task_id: str, coro) -> asyncio.Task:
    task = background.create(coro, name=f"worker:{task_id}")
    _active_tasks[task_id] = task

    def _on_done(t: asyncio.Task) -> None:
        # 仅当当前注册的就是 t 时才移除：rerun/retry 用同一 task_id 注册新协程时，
        # 旧 task 的 _on_done 在 _active_tasks 已被新任务覆盖后才触发，盲 pop 会
        # 把新任务从注册表里抹掉，导致 cancel/delete 端点再也找不到它。
        if _active_tasks.get(task_id) is t:
            _active_tasks.pop(task_id, None)
        clear_cancel_event(task_id)

        if t.cancelled() or not t.done():
            return
        try:
            exc = t.exception()
        except (RuntimeError, TypeError) as e:
            logger.exception(f"检查 task exception 失败 task_id={task_id}: {e}")
            return
        if exc is None:
            return

        logger.error(f"Background task {task_id} crashed: {exc!r}")
        # worker 抛出未捕获异常时其内部不会调用 _fail_task，DB 仍是 RUNNING；
        # 这里补一刀把状态改成 FAILED，并由 _fail_task 内部触发 schedule_auto_retry 与 WS 广播。
        error_text = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        from media_tools.scheduler.ops import _fail_task

        try:
            loop = asyncio.get_event_loop()
            loop.create_task(_fail_task(task_id, "unknown", error_text))
        except RuntimeError:
            # 没有运行的 loop —— done_callback 通常由 loop 触发，理论上不会到这里
            schedule_auto_retry(task_id)

    task.add_done_callback(_on_done)
    return task

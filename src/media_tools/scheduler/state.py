import asyncio
import logging
import sqlite3
from datetime import datetime

from media_tools.core import background

# 架构耦合说明：scheduler 层依赖 douyin.cancel_registry 清理任务取消事件。
# 未来可将 cancel_registry 提升到 core 层以消除跨域依赖。
from media_tools.douyin.core.cancel_registry import clear_cancel_event
from media_tools.scheduler.retry import schedule_auto_retry
from media_tools.store.db import get_db_connection

logger = logging.getLogger(__name__)

_active_tasks: dict[str, asyncio.Task] = {}
# 暂停会主动取消当前协程；该标记让 Worker 将取消解释为 PAUSED 而不是 CANCELLED。
_pause_requested_tasks: set[str] = set()
# 删除中的任务可能仍有不可立即中断的 worker；阻止迟到进度重新创建已删除记录。
_deleted_task_ids: set[str] = set()


def request_task_pause(task_id: str) -> None:
    _pause_requested_tasks.add(task_id)


def is_task_pause_requested(task_id: str) -> bool:
    return task_id in _pause_requested_tasks


def clear_task_pause_request(task_id: str) -> None:
    _pause_requested_tasks.discard(task_id)


def request_task_deletion(task_id: str) -> None:
    _deleted_task_ids.add(task_id)


def is_task_deleted(task_id: str) -> bool:
    return task_id in _deleted_task_ids


def clear_task_deletion(task_id: str) -> None:
    _deleted_task_ids.discard(task_id)


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
    # 若同一 task_id 仍有旧任务在跑，先取消它，避免 rerun/retry 时新旧任务竞争
    old = _active_tasks.get(task_id)
    if old is not None and not old.done():
        old.cancel()

    task = background.create(coro, name=f"worker:{task_id}")
    _active_tasks[task_id] = task

    # 捕获注册时的事件循环（一定在协程中），避免 _on_done 里使用废弃的 get_event_loop()
    loop = asyncio.get_running_loop()

    def _on_done(t: asyncio.Task) -> None:
        # 仅当当前注册的就是 t 时才移除：rerun/retry 用同一 task_id 注册新协程时，
        # 旧 task 的 _on_done 在 _active_tasks 已被新任务覆盖后才触发，盲 pop 会
        # 把新任务从注册表里抹掉，导致 cancel/delete 端点再也找不到它。
        if _active_tasks.get(task_id) is t:
            _active_tasks.pop(task_id, None)
        clear_cancel_event(task_id)
        clear_task_deletion(task_id)

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
            loop.create_task(_fail_task(task_id, "unknown", error_text))
        except RuntimeError:
            # loop 已关闭 —— 降级为只写 retry 标记
            schedule_auto_retry(task_id)

    task.add_done_callback(_on_done)
    return task

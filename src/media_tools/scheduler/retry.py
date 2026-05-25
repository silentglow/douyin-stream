from __future__ import annotations
from typing import Optional, Union

import asyncio
import json
import logging
import sqlite3

from media_tools.core import background
from media_tools.store.db import get_db_connection

logger = logging.getLogger(__name__)

MAX_AUTO_RETRY = 2

# 抽到模块级别便于测试 patch；生产值 5s/10s/20s 上限 60s。
_BACKOFF_BASE_SECONDS = 5
_BACKOFF_MAX_SECONDS = 60


async def _backoff_sleep(task_id: str, retry_count: int) -> None:
    delay_seconds = min((2 ** retry_count) * _BACKOFF_BASE_SECONDS, _BACKOFF_MAX_SECONDS)
    logger.info(
        f"任务 {task_id} 将在 {delay_seconds}s 后进行第 {retry_count + 1}/{MAX_AUTO_RETRY} 次自动重试"
    )
    await asyncio.sleep(delay_seconds)

# 仅以下 task_type 受 auto_retry 支持；其它（如 recover_aweme_transcribe、
# 以 creator_uid 启动的 local_transcribe）原始参数不足以复现，重试只会再次失败。
_AUTO_RETRY_SUPPORTED_TYPES: frozenset[str] = frozenset({
    "pipeline",
    "download",
})
_AUTO_RETRY_SUPPORTED_PREFIXES: tuple[str, ...] = (
    "creator_sync",
    "full_sync",
)


def _is_auto_retry_supported(task_type: Optional[str], payload: Optional[dict]) -> bool:
    if not task_type:
        return False
    if task_type in _AUTO_RETRY_SUPPORTED_TYPES:
        return True
    if any(task_type.startswith(p) for p in _AUTO_RETRY_SUPPORTED_PREFIXES):
        return True
    # local_transcribe 仅在能拿到 file_paths 列表时才能复现
    if task_type == "local_transcribe":
        return bool(payload and isinstance(payload.get("file_paths"), list) and payload["file_paths"])
    # creator_transcribe 只有 creator_uid，重试无法继续转写
    return False


def schedule_auto_retry(task_id: str) -> None:
    """Schedule auto-retry as a fire-and-forget task on the running event loop.

    Sync-callable so it works from both async code and sync `Task.add_done_callback` callbacks.
    No-op if there is no running event loop (e.g. called outside the server runtime).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        logger.debug(f"schedule_auto_retry skipped (no running loop) task_id={task_id}")
        return
    background.create(handle_auto_retry(task_id), name=f"auto_retry:{task_id}")


async def handle_auto_retry(task_id: str) -> None:
    db_marked_running = False
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT task_type, payload, auto_retry FROM task_queue WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if not row:
                return
            if not (row["auto_retry"] or 0):
                return

            task_type = row["task_type"]
            payload_str = row["payload"] or ""

        try:
            original_params = json.loads(payload_str) if payload_str else {}
        except (json.JSONDecodeError, TypeError):
            original_params = {}
        # 历史 payload 偶有非 dict 内容（直接的列表/字符串），后续逻辑全部按 dict 操作，先收敛到空 dict
        if not isinstance(original_params, dict):
            original_params = {}

        if not _is_auto_retry_supported(task_type, original_params):
            logger.info(f"任务 {task_id} 类型 {task_type!r} 不支持自动重试，跳过")
            return

        retry_count = int(original_params.get("_retry_count", 0) or 0)
        if retry_count >= MAX_AUTO_RETRY:
            logger.info(f"任务 {task_id} 已达最大自动重试次数 ({MAX_AUTO_RETRY})")
            return

        original_params["_retry_count"] = retry_count + 1
        payload_str = json.dumps(
            {**original_params, "msg": f"自动重试 ({retry_count + 1}/{MAX_AUTO_RETRY})..."},
            ensure_ascii=False,
        )

        # 退避：避免失败任务瞬间连重 N 次打爆下游限流；同时给 cancel 信号留出命中窗口，
        # 在写 DB 之前被取消就完全无副作用，不会留 RUNNING orphan。
        await _backoff_sleep(task_id, retry_count)

        with get_db_connection() as conn:
            cursor = conn.execute(
                "UPDATE task_queue SET status='RUNNING', progress=0.0, auto_retry=1, payload=? WHERE task_id=? AND status='FAILED'",
                (payload_str, task_id),
            )
            if cursor.rowcount == 0:
                logger.info(f"任务 {task_id} 状态已变更，跳过自动重试")
                return
        db_marked_running = True

        from media_tools.scheduler.dispatcher import _start_task_worker

        await _start_task_worker(task_id, task_type, original_params)
    except asyncio.CancelledError:
        # shutdown 期间被取消：不要把任务留成 RUNNING orphan（否则要等 cleanup_stale_tasks 20 分钟）
        if db_marked_running:
            _rollback_running_to_failed(task_id)
        logger.info(f"自动重试被取消 task_id={task_id}")
        raise
    except (sqlite3.Error, OSError, RuntimeError, asyncio.TimeoutError):
        logger.exception(f"自动重试失败 task_id={task_id}")
        if db_marked_running:
            _rollback_running_to_failed(task_id)


def _rollback_running_to_failed(task_id: str) -> None:
    """auto retry 已写 RUNNING 但后续失败/被取消时，立即把状态回滚为 FAILED。

    WHERE status='RUNNING' 保护：若 worker 已自己更新到 CANCELLED/FAILED 等终态，本次 UPDATE 是 no-op。
    """
    try:
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE task_queue SET status='FAILED' WHERE task_id=? AND status='RUNNING'",
                (task_id,),
            )
    except sqlite3.Error:
        logger.exception(f"回滚 RUNNING orphan 失败 task_id={task_id}")


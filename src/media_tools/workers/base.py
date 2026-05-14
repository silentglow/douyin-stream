from __future__ import annotations
"""后台任务工作者基类与注册表。

提供统一的 heartbeat、进度上报、三态终态决策和异常处理模板，
消除各 worker 文件中重复的 try/finally/except  boilerplate。
"""

import asyncio
import logging
from typing import Any, Optional

from media_tools.core.logging_context import task_context
from media_tools.scheduler.ops import (
    update_task_progress,
    _complete_task,
    _fail_task,
    _mark_task_cancelled,
)
from media_tools.scheduler.state import _task_heartbeat

logger = logging.getLogger(__name__)


class BaseWorker:
    """后台任务工作者基类。

    子类需覆盖：
      - task_type: str   （类属性，用于进度/终态上报）
      - run(task_id, **kwargs) -> None   （业务逻辑）

    execute() 为模板方法，子类不应覆盖。
    """

    task_type: str = ""

    def __init__(self) -> None:
        self._task_id: Optional[str] = None
        self._heartbeat: Optional[asyncio.Task[Any]] = None

    # ------------------------------------------------------------------
    # 模板方法
    # ------------------------------------------------------------------
    def _get_task_context_kwargs(self, **run_kwargs: Any) -> dict[str, Any]:
        """子类可覆盖，为 task_context 提供额外字段（如 creator_uid）。"""
        return {}

    async def execute(self, task_id: str, **kwargs: Any) -> None:
        """启动 heartbeat，设置日志上下文，执行业务逻辑，处理异常。"""
        self._task_id = task_id
        self._heartbeat = asyncio.create_task(_task_heartbeat(task_id))
        try:
            ctx = {"task_id": task_id, **self._get_task_context_kwargs(**kwargs)}
            with task_context(**ctx):
                await self.run(task_id, **kwargs)
        except asyncio.CancelledError:
            await self._handle_cancelled()
            raise
        except (RuntimeError, OSError, ValueError, TypeError) as exc:
            await self._handle_exception(exc)
        finally:
            await self._cleanup_heartbeat()

    async def run(self, task_id: str, **kwargs: Any) -> None:
        """子类必须覆盖此方法。"""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # 进度上报（统一签名）
    # ------------------------------------------------------------------
    async def report_progress(
        self,
        progress: float,
        message: str,
        *,
        stage: str = "",
        pipeline_progress: Optional[dict] = None,
    ) -> None:
        await update_task_progress(
            self._task_id,
            progress,
            message,
            self.task_type,
            stage=stage,
            pipeline_progress=pipeline_progress,
        )

    # ------------------------------------------------------------------
    # 三态终态决策
    # ------------------------------------------------------------------
    async def finalize_success(
        self,
        message: str,
        *,
        result_summary: Optional[dict] = None,
        subtasks: Optional[list] = None,
    ) -> None:
        await _complete_task(
            self._task_id,
            self.task_type,
            message,
            status="COMPLETED",
            result_summary=result_summary,
            subtasks=subtasks,
        )

    async def finalize_partial(
        self,
        message: str,
        *,
        error_msg: Optional[str] = None,
        result_summary: Optional[dict] = None,
        subtasks: Optional[list] = None,
    ) -> None:
        await _complete_task(
            self._task_id,
            self.task_type,
            message,
            status="PARTIAL_FAILED",
            error_msg=error_msg,
            result_summary=result_summary,
            subtasks=subtasks,
        )

    async def finalize_failure(
        self,
        message: str,
        *,
        error_msg: Optional[str] = None,
        result_summary: Optional[dict] = None,
        subtasks: Optional[list] = None,
    ) -> None:
        await _complete_task(
            self._task_id,
            self.task_type,
            message,
            status="FAILED",
            error_msg=error_msg,
            result_summary=result_summary,
            subtasks=subtasks,
        )

    # ------------------------------------------------------------------
    # 内部钩子（子类可按需覆盖）
    # ------------------------------------------------------------------
    async def _handle_cancelled(self) -> None:
        await _mark_task_cancelled(self._task_id, self.task_type)

    async def _handle_exception(self, exc: Exception) -> None:
        logger.exception(f"Worker {self.task_type} failed: {exc}")
        await _fail_task(self._task_id, self.task_type, str(exc))

    async def _cleanup_heartbeat(self) -> None:
        if self._heartbeat is not None:
            self._heartbeat.cancel()
            try:
                await self._heartbeat
            except asyncio.CancelledError:
                pass


# ====================================================================
# 注册表
# ====================================================================
_WORKER_REGISTRY: dict[str, type[BaseWorker]] = {}


def register_worker(task_type: str):
    """装饰器：将 Worker 类注册到全局注册表。

    示例::
        @register_worker("local_transcribe")
        class LocalTranscribeWorker(BaseWorker):
            task_type = "local_transcribe"
            async def run(self, task_id, **kwargs): ...
    """

    def decorator(cls: type[BaseWorker]) -> type[BaseWorker]:
        _WORKER_REGISTRY[task_type] = cls
        return cls

    return decorator


def get_worker_class(task_type: str) -> Optional[type[BaseWorker]]:
    """按 task_type 查找 Worker 类，支持前缀匹配（creator_sync_*, full_sync_*）。"""
    if task_type in _WORKER_REGISTRY:
        return _WORKER_REGISTRY[task_type]
    for registered_type in _WORKER_REGISTRY:
        if task_type.startswith(registered_type + "_"):
            return _WORKER_REGISTRY[registered_type]
    return None


def list_worker_types() -> list[str]:
    return list(_WORKER_REGISTRY.keys())

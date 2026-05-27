from __future__ import annotations

"""后台任务工作者基类。

提供统一的 heartbeat、进度上报、三态终态决策和异常处理模板，
消除各 worker 文件中重复的 try/finally/except  boilerplate。
"""

import asyncio
import contextlib
import logging
from typing import Any, TypeVar

from media_tools.core.logging_context import task_context
from media_tools.scheduler.ops import (
    _complete_task,
    _fail_task,
    _mark_task_cancelled,
    update_task_progress,
)
from media_tools.scheduler.state import _task_heartbeat

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════
# Worker 注册表(原 scheduler/registry.py,18 行,合并进来)
# ═════════════════════════════════════════════════════════════════
# 历史:为避免循环导入独立成文件。现在 base.py 不再需要从 registry 反向导入,
# 二者依赖方向一致,合并简化文件数。
T = TypeVar("T", bound="BaseWorker")

_WORKER_REGISTRY: dict[str, type] = {}


def register_worker(task_type: str):
    """装饰器:将 Worker 类注册到全局注册表。"""

    def decorator(cls: type[T]) -> type[T]:
        _WORKER_REGISTRY[task_type] = cls
        return cls

    return decorator


class BaseWorker:
    """后台任务工作者基类。

    子类需覆盖：
      - task_type: str   （类属性，用于进度/终态上报）
      - run(task_id, **kwargs) -> None   （业务逻辑）

    execute() 为模板方法，子类不应覆盖。
    """

    task_type: str = ""

    def __init__(self) -> None:
        self._task_id: str | None = None
        self._heartbeat: asyncio.Task[Any] | None = None

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
        except Exception as exc:
            # 故意宽口径：sqlite3.Error、requests.RequestException、json.JSONDecodeError、
            # KeyError、AttributeError 等都必须走 _handle_exception，否则会逃逸到
            # state._on_done，那里硬编码 task_type='unknown' 会改坏 DB 列、令前端"重试"按钮失效。
            # CancelledError 不在 Exception 链下，已由上一分支处理。
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
        pipeline_progress: dict | None = None,
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
        result_summary: dict | None = None,
        subtasks: list | None = None,
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
        error_msg: str | None = None,
        result_summary: dict | None = None,
        subtasks: list | None = None,
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
        error_msg: str | None = None,
        result_summary: dict | None = None,
        subtasks: list | None = None,
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
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat

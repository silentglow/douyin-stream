from __future__ import annotations
"""结构化日志上下文 —— 基于 contextvars 自动为每条日志注入 task_id / request_id 等字段。

用法：
  # HTTP 中间件自动设置 request_id，worker 中可手动设置 task_id：
  from media_tools.core.logging_context import task_context

  async def worker(task_id):
      with task_context(task_id=task_id):
          logger.info("starting transcribe")  # 自动包含 task_id
"""

from contextvars import ContextVar
from contextlib import contextmanager
from typing import Any, Generator, Optional


_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_task_id: ContextVar[Optional[str]] = ContextVar("task_id", default=None)
_creator_uid: ContextVar[Optional[str]] = ContextVar("creator_uid", default=None)


def get_logging_context() -> dict[str, str]:
    """返回当前上下文中所有非 None 的字段。"""
    ctx: dict[str, str] = {}
    for name, var in [
        ("request_id", _request_id),
        ("task_id", _task_id),
        ("creator_uid", _creator_uid),
    ]:
        val = var.get()
        if val:
            ctx[name] = val
    return ctx


def set_logging_context(**kwargs: Optional[str]) -> None:
    """批量设置上下文字段。传入 None 可清除对应字段。"""
    for key, value in kwargs.items():
        var = _CONTEXT_VARS.get(key)
        if var is not None:
            var.set(value)


def clear_logging_context() -> None:
    """清除所有上下文字段。"""
    for var in _CONTEXT_VARS.values():
        var.set(None)


_CONTEXT_VARS: dict[str, ContextVar[Optional[str]]] = {
    "request_id": _request_id,
    "task_id": _task_id,
    "creator_uid": _creator_uid,
}


@contextmanager
def task_context(
    *,
    task_id: Optional[str] = None,
    creator_uid: Optional[str] = None,
) -> Generator[None, None, None]:
    """上下文管理器：进入时设置 task_id / creator_uid，退出时恢复。

    适用于 worker 函数体，确保该函数内所有日志自动携带任务标识。
    """
    tokens: list[tuple[ContextVar[Optional[str]], Any]] = []
    if task_id is not None:
        tokens.append((_task_id, _task_id.set(task_id)))
    if creator_uid is not None:
        tokens.append((_creator_uid, _creator_uid.set(creator_uid)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)

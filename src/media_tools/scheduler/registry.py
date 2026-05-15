from __future__ import annotations
"""Worker 注册表 — 从 base.py 独立出来，避免循环导入。"""

from typing import Optional, TypeVar

T = TypeVar("T", bound="BaseWorker")

_WORKER_REGISTRY: dict[str, type] = {}


def register_worker(task_type: str):
    """装饰器：将 Worker 类注册到全局注册表。"""

    def decorator(cls: type[T]) -> type[T]:
        _WORKER_REGISTRY[task_type] = cls
        return cls

    return decorator

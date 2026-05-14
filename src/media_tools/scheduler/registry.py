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


def get_worker_class(task_type: str) -> Optional[type]:
    """按 task_type 查找 Worker 类，支持前缀匹配（creator_sync_*, full_sync_*）。"""
    if task_type in _WORKER_REGISTRY:
        return _WORKER_REGISTRY[task_type]
    for registered_type in _WORKER_REGISTRY:
        if task_type.startswith(registered_type + "_"):
            return _WORKER_REGISTRY[registered_type]
    return None


def list_worker_types() -> list[str]:
    return list(_WORKER_REGISTRY.keys())

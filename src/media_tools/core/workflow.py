from __future__ import annotations
"""任务状态机 — 定义合法的状态转移。"""

from enum import Enum, auto


class TaskStatus(Enum):
    """任务状态"""
    PENDING = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()
    PARTIAL_FAILED = auto()
    CANCELLED = auto()


# 合法状态转移图
VALID_TRANSITIONS: dict[TaskStatus, list[TaskStatus]] = {
    TaskStatus.PENDING: [TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED],
    TaskStatus.RUNNING: [TaskStatus.PAUSED, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.PARTIAL_FAILED, TaskStatus.CANCELLED],
    TaskStatus.PAUSED: [TaskStatus.RUNNING, TaskStatus.CANCELLED],
    TaskStatus.COMPLETED: [],
    TaskStatus.FAILED: [TaskStatus.RUNNING],
    TaskStatus.PARTIAL_FAILED: [TaskStatus.RUNNING],
    TaskStatus.CANCELLED: [TaskStatus.RUNNING],
}


class InvalidTransitionError(ValueError):
    """非法状态转移异常"""
    pass


def validate_transition_by_str(from_status_str: str, to_status_str: str) -> None:
    """字符串版本的状态转移验证。"""
    try:
        from_s = TaskStatus[from_status_str.upper()]
        to_s = TaskStatus[to_status_str.upper()]
    except KeyError as e:
        raise InvalidTransitionError(f"Unknown status: {e}") from e
    validate_transition(from_s, to_s)


def validate_transition(from_status: TaskStatus, to_status: TaskStatus) -> None:
    """验证状态转移是否合法。"""
    allowed = VALID_TRANSITIONS.get(from_status, [])
    if to_status not in allowed:
        raise InvalidTransitionError(
            f"Invalid transition: {from_status.name} -> {to_status.name}"
        )

"""PARTIAL_FAILED 任务状态机测试。

覆盖：
- workflow.PARTIAL_FAILED enum 存在 + 转移图正确（RUNNING -> PARTIAL_FAILED -> RUNNING 合法）
- 子任务三态决策：全成功 -> COMPLETED；混合 -> PARTIAL_FAILED；全失败 -> FAILED
- _complete_task(PARTIAL_FAILED) 不触发 schedule_auto_retry（避免重跑成功子任务）
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch, AsyncMock

import pytest

from media_tools.core.workflow import (
    TaskStatus,
    VALID_TRANSITIONS,
    validate_transition,
    validate_transition_by_str,
    InvalidTransitionError,
)


# ---------- workflow enum / transitions ----------

def test_partial_failed_enum_exists():
    assert TaskStatus.PARTIAL_FAILED in TaskStatus
    assert TaskStatus.PARTIAL_FAILED.value != TaskStatus.FAILED.value


def test_running_can_transition_to_partial_failed():
    validate_transition(TaskStatus.RUNNING, TaskStatus.PARTIAL_FAILED)


def test_partial_failed_can_transition_to_running_for_retry():
    validate_transition(TaskStatus.PARTIAL_FAILED, TaskStatus.RUNNING)


def test_partial_failed_is_terminal_no_other_transitions():
    # 终态：只能 -> RUNNING（重试），不能 -> COMPLETED / CANCELLED 等
    allowed = VALID_TRANSITIONS[TaskStatus.PARTIAL_FAILED]
    assert allowed == [TaskStatus.RUNNING]
    with pytest.raises(InvalidTransitionError):
        validate_transition(TaskStatus.PARTIAL_FAILED, TaskStatus.COMPLETED)
    with pytest.raises(InvalidTransitionError):
        validate_transition(TaskStatus.PARTIAL_FAILED, TaskStatus.FAILED)


def test_partial_failed_string_transitions():
    validate_transition_by_str("RUNNING", "PARTIAL_FAILED")
    validate_transition_by_str("PARTIAL_FAILED", "RUNNING")
    with pytest.raises(InvalidTransitionError):
        validate_transition_by_str("PENDING", "PARTIAL_FAILED")


# ---------- 三态决策（worker 内的 status 选择逻辑） ----------

def _three_state_decision(s_count: int, f_count: int) -> str:
    """复刻 local_transcribe_worker / creator_transcribe_worker 的三态判定，
    保持单元测试不需要拉起整个 worker 路径。"""
    if f_count == 0:
        return "COMPLETED"
    elif s_count > 0:
        return "PARTIAL_FAILED"
    else:
        return "FAILED"


@pytest.mark.parametrize("s_count,f_count,expected", [
    (10, 0, "COMPLETED"),    # 全成功
    (0, 10, "FAILED"),        # 全失败
    (7, 3, "PARTIAL_FAILED"), # 混合
    (1, 9, "PARTIAL_FAILED"), # 只成功 1 个也是部分失败
    (9, 1, "PARTIAL_FAILED"), # 只失败 1 个也是部分失败
    (0, 0, "COMPLETED"),      # 0 文件输入也算成功（worker 上层会拦截 total=0 走"没有有效文件"分支）
])
def test_three_state_decision(s_count, f_count, expected):
    assert _three_state_decision(s_count, f_count) == expected


# ---------- _complete_task: PARTIAL_FAILED 不触发 auto_retry ----------

@pytest.mark.asyncio
async def test_complete_task_partial_failed_does_not_trigger_auto_retry(monkeypatch, tmp_path):
    """关键不变量：PARTIAL_FAILED 不跑 schedule_auto_retry，
    因为重跑会让已成功的子任务白费一次（外部 API 调用 + 写盘）。
    用户可以通过 UI"只重试失败子任务"入口手动重新调度。
    """
    from media_tools.scheduler import ops as task_ops

    # 准备一个空 SQLite，让 _complete_task 内部的 SQL 能跑通
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("media_tools.common.paths.get_db_path", lambda: db_path)

    # 重置 db core 的连接缓存，让它用我们 monkey 后的路径
    from media_tools.db import core as db_core
    db_core.reset_db_cache()
    db_core._db_path = None
    db_core.init_db(db_path)

    # 插入一个 RUNNING 任务
    with db_core.get_db_connection() as conn:
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, payload, status, progress, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            ("t-partial-1", "local_transcribe", "{}", "RUNNING", 0.5),
        )
        conn.commit()

    # patch schedule_auto_retry 和 notify_task_update，确保其被/不被调用
    auto_retry_calls = []
    monkeypatch.setattr(
        task_ops, "schedule_auto_retry",
        lambda task_id: auto_retry_calls.append(task_id),
    )
    monkeypatch.setattr(task_ops, "notify_task_update", AsyncMock())

    await task_ops._complete_task(
        "t-partial-1",
        "local_transcribe",
        "部分失败：成功 7 个，失败 3 个",
        status="PARTIAL_FAILED",
        result_summary={"success": 7, "failed": 3, "total": 10},
    )

    # 关键断言：PARTIAL_FAILED 不进 auto_retry
    assert auto_retry_calls == [], (
        f"PARTIAL_FAILED 不应触发 schedule_auto_retry，实际调用了: {auto_retry_calls}"
    )

    # 但 notify_task_update 必须被调用，前端要看到状态更新
    task_ops.notify_task_update.assert_awaited_once()

    # DB 状态确实写成 PARTIAL_FAILED
    with db_core.get_db_connection() as conn:
        row = conn.execute(
            "SELECT status, progress FROM task_queue WHERE task_id = ?",
            ("t-partial-1",),
        ).fetchone()
    assert row is not None
    assert row[0] == "PARTIAL_FAILED"
    # PARTIAL_FAILED 保留现有进度（不强推 1.0）
    assert row[1] == 0.5


@pytest.mark.asyncio
async def test_complete_task_failed_still_triggers_auto_retry(monkeypatch, tmp_path):
    """对照组：FAILED 状态仍然触发 auto_retry，证明 PARTIAL_FAILED 的特殊行为是有意为之。"""
    from media_tools.scheduler import ops as task_ops

    db_path = tmp_path / "test.db"
    monkeypatch.setattr("media_tools.common.paths.get_db_path", lambda: db_path)

    from media_tools.db import core as db_core
    db_core.reset_db_cache()
    db_core._db_path = None
    db_core.init_db(db_path)

    with db_core.get_db_connection() as conn:
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, payload, status, progress, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            ("t-fail-1", "local_transcribe", "{}", "RUNNING", 0.3),
        )
        conn.commit()

    auto_retry_calls = []
    monkeypatch.setattr(
        task_ops, "schedule_auto_retry",
        lambda task_id: auto_retry_calls.append(task_id),
    )
    monkeypatch.setattr(task_ops, "notify_task_update", AsyncMock())

    await task_ops._complete_task(
        "t-fail-1",
        "local_transcribe",
        "全部失败",
        status="FAILED",
        result_summary={"success": 0, "failed": 10, "total": 10},
    )

    assert auto_retry_calls == ["t-fail-1"]

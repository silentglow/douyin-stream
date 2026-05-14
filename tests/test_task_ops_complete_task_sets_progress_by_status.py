from __future__ import annotations

import sqlite3
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from media_tools.scheduler import ops as task_ops


@pytest.mark.asyncio
async def test_complete_task_failed_sets_progress_zero() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE task_queue (
            task_id TEXT PRIMARY KEY,
            task_type TEXT,
            status TEXT,
            progress REAL,
            payload TEXT,
            create_time TEXT,
            update_time TEXT,
            error_msg TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO task_queue(task_id, task_type, status, progress, payload, create_time, update_time, error_msg)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("t1", "pipeline", "RUNNING", 0.0, "{}", "2026-04-27T00:00:00", "2026-04-27T00:00:00", None),
    )
    conn.commit()

    notify = AsyncMock()
    with patch.object(task_ops, "get_db_connection", return_value=conn), patch.object(
        task_ops, "notify_task_update", new=notify
    ):
        await task_ops._complete_task("t1", "pipeline", "fail", status="FAILED", error_msg="boom")

    assert notify.await_args.args[1] == 0.0


@pytest.mark.asyncio
async def test_complete_task_sends_pipeline_progress_and_updates_update_time() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE task_queue (
            task_id TEXT PRIMARY KEY,
            task_type TEXT,
            status TEXT,
            progress REAL,
            payload TEXT,
            create_time TEXT,
            update_time TEXT,
            error_msg TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO task_queue(task_id, task_type, status, progress, payload, create_time, update_time, error_msg)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "t1",
            "creator_sync_full",
            "RUNNING",
            0.6,
            '{"pipeline_progress":{"stage":"download","download":{"done":3,"total":3}}}',
            "2026-04-27T00:00:00",
            "2026-04-27T00:00:00",
            None,
        ),
    )
    conn.commit()

    notify = AsyncMock()

    class FakeDateTime:
        @classmethod
        def now(cls):  # noqa: N805
            return datetime(2026, 4, 29, 12, 0, 0)

    with patch.object(task_ops, "get_db_connection", return_value=conn), patch.object(
        task_ops, "notify_task_update", new=notify
    ), patch.object(task_ops, "datetime", FakeDateTime):
        await task_ops._complete_task("t1", "creator_sync_full", "ok", status="COMPLETED")

    row = conn.execute("SELECT update_time FROM task_queue WHERE task_id='t1'").fetchone()
    assert row is not None
    assert (row["update_time"] if isinstance(row, sqlite3.Row) else row[0]) == "2026-04-29T12:00:00"
    assert notify.await_args.kwargs.get("pipeline_progress") == {"stage": "download", "download": {"done": 3, "total": 3}}

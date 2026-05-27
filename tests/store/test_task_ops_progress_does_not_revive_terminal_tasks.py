from __future__ import annotations

import sqlite3
from unittest.mock import AsyncMock, patch

import pytest

from media_tools.scheduler import ops as task_ops


@pytest.mark.asyncio
async def test_update_task_progress_does_not_revive_failed_task() -> None:
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
        ("t1", "pipeline", "FAILED", 0.0, "{}", "2026-04-27T00:00:00", "2026-04-27T00:00:00", "boom"),
    )
    conn.commit()

    with (
        patch.object(task_ops, "get_db_connection", return_value=conn),
        patch.object(task_ops, "notify_task_update", new=AsyncMock()),
    ):
        await task_ops.update_task_progress("t1", 0.5, "progress", "pipeline")

    status = conn.execute("SELECT status FROM task_queue WHERE task_id = ?", ("t1",)).fetchone()["status"]
    assert status == "FAILED"

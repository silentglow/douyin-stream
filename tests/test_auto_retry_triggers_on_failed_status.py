from __future__ import annotations

import json
import sqlite3
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_handle_auto_retry_restarts_failed_task() -> None:
    import media_tools.scheduler.retry as auto_retry_module

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE task_queue (
            task_id TEXT PRIMARY KEY,
            task_type TEXT,
            payload TEXT,
            status TEXT,
            progress REAL,
            error_msg TEXT,
            auto_retry INTEGER DEFAULT 0,
            create_time TEXT,
            update_time TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO task_queue(task_id, task_type, payload, status, progress, error_msg, auto_retry, create_time, update_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("t1", "pipeline", json.dumps({}), "FAILED", 0.0, "boom", 1, "t0", "t0"),
    )
    conn.commit()

    start_worker = AsyncMock()
    with patch("media_tools.scheduler.retry.get_db_connection", return_value=conn), patch(
        "media_tools.scheduler.dispatcher._start_task_worker",
        new=start_worker,
    ):
        await auto_retry_module.handle_auto_retry("t1")

    row = conn.execute("SELECT status, progress, payload FROM task_queue WHERE task_id = ?", ("t1",)).fetchone()
    assert row["status"] == "RUNNING"
    assert row["progress"] == 0.0

    payload = json.loads(row["payload"])
    assert payload.get("_retry_count") == 1
    assert "自动重试" in payload.get("msg", "")
    assert start_worker.await_count == 1

from __future__ import annotations

import json
import sqlite3
from unittest.mock import AsyncMock, patch

import pytest

from media_tools.scheduler import ops as task_ops


@pytest.mark.asyncio
async def test_update_task_progress_persists_stage_into_payload_pipeline_progress() -> None:
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
            "pipeline",
            "RUNNING",
            0.0,
            json.dumps({"msg": "x"}, ensure_ascii=False),
            "2026-04-27T00:00:00",
            "2026-04-27T00:00:00",
            None,
        ),
    )
    conn.commit()

    with (
        patch.object(task_ops, "get_db_connection", return_value=conn),
        patch.object(task_ops, "notify_task_update", new=AsyncMock()),
    ):
        await task_ops.update_task_progress("t1", 0.2, "downloading", "pipeline", stage="download")

    row = conn.execute("SELECT payload FROM task_queue WHERE task_id = ?", ("t1",)).fetchone()
    assert row is not None
    payload = json.loads(row["payload"])
    assert payload["pipeline_progress"]["stage"] == "download"

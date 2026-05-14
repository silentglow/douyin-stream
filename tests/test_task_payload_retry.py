from __future__ import annotations

import json
import sqlite3
import unittest
from unittest.mock import AsyncMock, patch


class TaskPayloadRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_update_task_progress_preserves_original_payload_params(self) -> None:
        from media_tools.api.routers import tasks as tasks_router

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

        task_id = "task-1"
        original_payload = json.dumps(
            {
                "file_paths": ["/tmp/a.mp3"],
                "delete_after": False,
                "msg": "Initializing...",
            },
            ensure_ascii=False,
        )
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) VALUES (?, ?, 'RUNNING', 0.0, ?, 't0', 't0')",
            (task_id, "local_transcribe", original_payload),
        )
        conn.commit()

        from media_tools.services import task_ops

        with patch("media_tools.scheduler.ops.get_db_connection", return_value=conn), patch(
            "media_tools.scheduler.ops.notify_task_update",
            new=AsyncMock(),
        ):
            await task_ops.update_task_progress(task_id, 0.2, "正在转写 /tmp/a.mp3 (1/1)", "local_transcribe")

        row = conn.execute("SELECT payload FROM task_queue WHERE task_id = ?", (task_id,)).fetchone()
        self.assertIsNotNone(row)
        payload = json.loads(row["payload"])
        self.assertEqual(payload.get("file_paths"), ["/tmp/a.mp3"])
        self.assertEqual(payload.get("delete_after"), False)
        self.assertEqual(payload.get("msg"), "正在转写 /tmp/a.mp3 (1/1)")


if __name__ == "__main__":
    unittest.main()


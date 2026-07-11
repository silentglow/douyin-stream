from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from fastapi.testclient import TestClient

from media_tools.api.app import app


def test_clear_history_removes_non_active_tasks(monkeypatch) -> None:
    from media_tools.api.routers import tasks as tasks_router
    from media_tools.douyin.core import cancel_registry
    from media_tools.scheduler import repository as task_repository

    conn = sqlite3.connect(":memory:", check_same_thread=False)
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
          error_msg TEXT,
          auto_retry INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()

    conn.execute(
        "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("t_done", "pipeline", "COMPLETED", 1.0, "{}", "t0", "t0"),
    )
    conn.execute(
        "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("t_orphan", "pipeline", "RUNNING", 0.3, "{}", "t0", "t0"),
    )
    conn.execute(
        "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("t_active", "pipeline", "RUNNING", 0.5, "{}", "t0", "t0"),
    )
    conn.execute(
        "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("t_paused", "pipeline", "PAUSED", 0.4, "{}", "t0", "t0"),
    )
    conn.commit()

    @contextmanager
    def _get_conn():  # noqa: ANN001
        yield conn

    monkeypatch.setattr(task_repository, "get_db_connection", _get_conn)
    monkeypatch.setattr(tasks_router, "_active_tasks", {"t_active": object()})

    cancel_registry.set_cancel_event("t_done")
    cancel_registry.set_download_progress("t_orphan", {"progress": 0.3})

    client = TestClient(app)
    resp = client.delete("/api/v1/tasks/history")
    assert resp.status_code == 200

    rows = conn.execute("SELECT task_id FROM task_queue ORDER BY task_id").fetchall()
    assert [r["task_id"] for r in rows] == ["t_active", "t_paused"]

    assert cancel_registry.is_task_cancelled("t_done") is False
    assert cancel_registry.get_download_progress("t_orphan") is None

    cancel_registry.clear_cancel_event("t_active")
    cancel_registry.clear_download_progress("t_active")

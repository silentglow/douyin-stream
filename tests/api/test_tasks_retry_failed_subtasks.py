import contextlib
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from media_tools.api.app import app


def _skip_background_task(_task_id, coro):
    with contextlib.suppress(Exception):
        coro.close()
    return None


def test_retry_failed_subtasks_creates_local_transcribe_task(tmp_path: Path) -> None:
    from media_tools.api.routers import tasks as tasks_router

    conn = sqlite3.connect(":memory:", check_same_thread=False)
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
            create_time TEXT,
            update_time TEXT
        )
        """
    )
    conn.commit()

    failed_video = tmp_path / "failed.mp4"
    failed_video.write_bytes(b"video")
    missing_video = tmp_path / "missing.mp4"
    payload = {
        "delete_after": False,
        "directory_root": str(tmp_path),
        "subtasks": [
            {"title": "ok", "status": "completed", "video_path": str(tmp_path / "ok.mp4")},
            {"title": "failed", "status": "failed", "video_path": str(failed_video)},
            {"title": "missing", "status": "failed", "video_path": str(missing_video)},
        ],
    }
    conn.execute(
        """
        INSERT INTO task_queue(task_id, task_type, payload, status, progress, error_msg, create_time, update_time)
        VALUES (?, ?, ?, 'FAILED', 0.0, '', 't0', 't0')
        """,
        ("source-task", "local_transcribe", json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()

    with (
        patch(
            "media_tools.scheduler.repository.get_db_connection",
            return_value=conn,
        ),
        patch("media_tools.scheduler.dispatcher.notify_task_update"),
        patch("media_tools.scheduler.dispatcher._register_background_task", side_effect=_skip_background_task),
        patch("media_tools.scheduler.dispatcher._register_local_assets") as register_local_assets,
    ):
        client = TestClient(app)
        resp = client.post("/api/v1/tasks/source-task/retry-failed")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert data["file_count"] == 1
    assert data["task_id"] != "source-task"
    register_local_assets.assert_called_once_with([str(failed_video)], False, str(tmp_path))

    created = conn.execute(
        "SELECT task_type, payload, status FROM task_queue WHERE task_id = ?",
        (data["task_id"],),
    ).fetchone()
    assert created is not None
    assert created["task_type"] == "local_transcribe"
    assert created["status"] == "RUNNING"
    created_payload = json.loads(created["payload"])
    assert created_payload["file_paths"] == [str(failed_video)]
    assert created_payload["retry_failed_from_task_id"] == "source-task"


def test_retry_failed_subtasks_requires_existing_failed_paths(tmp_path: Path) -> None:
    from media_tools.api.routers import tasks as tasks_router

    conn = sqlite3.connect(":memory:", check_same_thread=False)
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
            create_time TEXT,
            update_time TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO task_queue(task_id, task_type, payload, status, progress, error_msg, create_time, update_time)
        VALUES (?, ?, ?, 'FAILED', 0.0, '', 't0', 't0')
        """,
        ("source-task", "local_transcribe", json.dumps({"subtasks": [{"status": "failed", "title": "no-path"}]})),
    )
    conn.commit()

    with (
        patch(
            "media_tools.scheduler.repository.get_db_connection",
            return_value=conn,
        ),
    ):
        client = TestClient(app)
        resp = client.post("/api/v1/tasks/source-task/retry-failed")

    assert resp.status_code == 409
    assert resp.json()["message"] == "没有可重试的失败视频路径"

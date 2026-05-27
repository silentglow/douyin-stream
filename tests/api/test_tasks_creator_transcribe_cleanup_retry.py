import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from media_tools.api.app import app


def test_creator_transcribe_cleanup_retry_deletes_allowlisted_and_updates_payload(tmp_path: Path) -> None:
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

    project_root = tmp_path / "proj"
    downloads_root = project_root / "downloads"
    transcripts_root = project_root / "transcripts"
    downloads_root.mkdir(parents=True)
    transcripts_root.mkdir(parents=True)

    should_delete = downloads_root / "a.tmp"
    should_delete.write_text("x", encoding="utf-8")
    outside_root = tmp_path / "outside.tmp"
    outside_root.write_text("y", encoding="utf-8")
    already_gone = downloads_root / "gone.tmp"

    payload = {
        "cleanup_deleted_count": 2,
        "cleanup_failed_count": 3,
        "cleanup_failed_paths": [
            {"path": str(should_delete), "reason": "permission_denied"},
            {"path": str(outside_root), "reason": "path_outside_root"},
            {"path": str(already_gone), "reason": "unknown"},
        ],
    }
    conn.execute(
        """
        INSERT INTO task_queue(task_id, task_type, payload, status, progress, error_msg, create_time, update_time)
        VALUES (?, ?, ?, 'FAILED', 0.0, '', 't0', 't0')
        """,
        ("t1", "local_transcribe", json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()

    with (
        patch(
            "media_tools.scheduler.repository.get_db_connection",
            return_value=conn,
        ),
        patch.object(tasks_router, "get_download_path", return_value=downloads_root),
        patch.object(tasks_router, "get_transcripts_path", return_value=transcripts_root),
    ):
        client = TestClient(app)
        resp = client.post("/api/v1/tasks/transcribe/creator/cleanup-retry", json={"task_id": "t1"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "t1"
    assert data["deleted_count"] == 1
    assert data["total_deleted_count"] == 3
    assert not should_delete.exists()
    assert data["failed_count"] == 1
    assert data["failed_paths"] == [{"path": str(outside_root.resolve()), "reason": "path_outside_root"}]

    payload_raw = conn.execute("SELECT payload FROM task_queue WHERE task_id = ?", ("t1",)).fetchone()["payload"]
    updated = json.loads(payload_raw)
    assert updated["cleanup_deleted_count"] == 3
    assert updated["cleanup_failed_count"] == 1
    assert updated["cleanup_failed_paths"] == [{"path": str(outside_root.resolve()), "reason": "path_outside_root"}]

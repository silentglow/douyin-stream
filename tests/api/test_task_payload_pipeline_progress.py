import json
import sqlite3
from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from media_tools.api.app import app


def test_task_history_injects_pipeline_progress_into_payload() -> None:
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
    now = datetime.now().isoformat()
    conn.execute(
        """
        INSERT INTO task_queue(task_id, task_type, payload, status, progress, error_msg, create_time, update_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("t-p1", "pipeline", json.dumps({"msg": "x"}, ensure_ascii=False), "RUNNING", 0.2, "", now, now),
    )
    conn.execute(
        """
        INSERT INTO task_queue(task_id, task_type, payload, status, progress, error_msg, create_time, update_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("t-p2", "pipeline", json.dumps({"msg": "y"}, ensure_ascii=False), "RUNNING", 0.7, "", now, now),
    )
    conn.execute(
        """
        INSERT INTO task_queue(task_id, task_type, payload, status, progress, error_msg, create_time, update_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "t-p3",
            "pipeline",
            json.dumps(
                {
                    "msg": "z",
                    "max_counts": 99,
                    "batch_size": 3,
                    "export_file": "/tmp/export.md",
                    "export_status": "saved",
                },
                ensure_ascii=False,
            ),
            "RUNNING",
            0.2,
            "",
            now,
            now,
        ),
    )
    conn.execute(
        """
        INSERT INTO task_queue(task_id, task_type, payload, status, progress, error_msg, create_time, update_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("t-other", "download", json.dumps({"msg": "z"}, ensure_ascii=False), "RUNNING", 0.3, "", now, now),
    )
    conn.execute(
        """
        INSERT INTO task_queue(task_id, task_type, payload, status, progress, error_msg, create_time, update_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "t-c1",
            "creator_sync_incremental",
            json.dumps({"msg": "c", "missing_items": [{"x": 1}, {"y": 2}]}, ensure_ascii=False),
            "RUNNING",
            0.05,
            "",
            now,
            now,
        ),
    )
    conn.commit()

    with patch("media_tools.api.routers.tasks.get_db_connection", return_value=conn), patch(
        "media_tools.scheduler.repository.get_db_connection", return_value=conn
    ):
        client = TestClient(app)
        resp = client.get("/api/v1/tasks/history")

    assert resp.status_code == 200
    tasks = resp.json()
    by_id = {t["task_id"]: t for t in tasks}

    payload_1 = json.loads(by_id["t-p1"]["payload"])
    assert payload_1["pipeline_progress"]["stage"] == "downloading"
    assert payload_1["pipeline_progress"]["list"] == {"done": 1, "total": 1}
    assert payload_1["pipeline_progress"]["download"]["total"] == 1
    assert payload_1["pipeline_progress"]["export"]["total"] == 1

    payload_2 = json.loads(by_id["t-p2"]["payload"])
    assert payload_2["pipeline_progress"]["stage"] == "transcribing"
    assert payload_2["pipeline_progress"]["transcribe"]["total"] >= 0

    payload_other = json.loads(by_id["t-other"]["payload"])
    assert payload_other["pipeline_progress"]["stage"] == "downloading"

    payload_3 = json.loads(by_id["t-p3"]["payload"])
    assert payload_3["pipeline_progress"]["download"]["total"] == 3
    assert payload_3["pipeline_progress"]["export"]["file"] == "/tmp/export.md"
    assert payload_3["pipeline_progress"]["export"]["status"] == "saved"

    payload_c1 = json.loads(by_id["t-c1"]["payload"])
    assert payload_c1["pipeline_progress"]["stage"] == "fetching"
    assert payload_c1["pipeline_progress"]["audit"]["missing"] == 2


def test_task_status_injects_pipeline_progress_into_payload() -> None:
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
    now = datetime.now().isoformat()
    conn.execute(
        """
        INSERT INTO task_queue(task_id, task_type, payload, status, progress, error_msg, create_time, update_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("t1", "pipeline", json.dumps({"msg": "x"}, ensure_ascii=False), "RUNNING", 0.2, "", now, now),
    )
    conn.execute(
        """
        INSERT INTO task_queue(task_id, task_type, payload, status, progress, error_msg, create_time, update_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("t2", "creator_sync_full", json.dumps({"msg": "y"}, ensure_ascii=False), "RUNNING", 0.2, "", now, now),
    )
    conn.commit()

    with patch("media_tools.api.routers.tasks.get_db_connection", return_value=conn), patch(
        "media_tools.scheduler.repository.get_db_connection", return_value=conn
    ):
        client = TestClient(app)
        resp_1 = client.get("/api/v1/tasks/t1")
        resp_2 = client.get("/api/v1/tasks/t2")

    assert resp_1.status_code == 200
    payload_1 = json.loads(resp_1.json()["payload"])
    assert payload_1["pipeline_progress"]["stage"] == "downloading"

    assert resp_2.status_code == 200
    payload_2 = json.loads(resp_2.json()["payload"])
    assert payload_2["pipeline_progress"]["stage"] in ("fetching", "downloading")

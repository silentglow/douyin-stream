from __future__ import annotations

import json


def test_task_repository_patch_payload_merges_fields(tmp_path, monkeypatch) -> None:
    import sqlite3
    from contextlib import contextmanager

    from media_tools.scheduler.repository import TaskRepository

    db_path = tmp_path / "t.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE task_queue(
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

    @contextmanager
    def _get_conn():  # noqa: ANN001
        yield conn

    monkeypatch.setattr("media_tools.scheduler.repository.get_db_connection", _get_conn)

    TaskRepository.create("t1", "local_transcribe", {"a": 1})
    TaskRepository.patch_payload("t1", {"b": 2})

    row = conn.execute("SELECT payload FROM task_queue WHERE task_id='t1'").fetchone()
    assert row is not None
    payload = json.loads(row[0])
    assert payload["a"] == 1
    assert payload["b"] == 2

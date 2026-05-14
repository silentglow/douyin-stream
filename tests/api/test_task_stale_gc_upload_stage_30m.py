import json
import sqlite3
from datetime import datetime, timedelta

from media_tools.scheduler.ops import cleanup_stale_tasks


def test_cleanup_stale_tasks_upload_stage_uses_30m(monkeypatch) -> None:
    """upload 阶段任务的 stale 阈值需要至少 30 分钟（OSS 大文件上传可能慢）。
    GC 由 scheduler 后台 job 调用 cleanup_stale_tasks 完成；本测试直接验证函数行为。"""
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

    now = datetime.now()
    payload_upload = json.dumps({"pipeline_progress": {"stage": "upload"}}, ensure_ascii=False)
    payload_other = json.dumps({"pipeline_progress": {"stage": "transcribe"}}, ensure_ascii=False)

    conn.execute(
        """
        INSERT INTO task_queue(task_id, task_type, payload, status, progress, error_msg, create_time, update_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "t-upload-25m",
            "pipeline",
            payload_upload,
            "RUNNING",
            0.1,
            "",
            now.isoformat(),
            (now - timedelta(minutes=25)).isoformat(),
        ),
    )
    conn.execute(
        """
        INSERT INTO task_queue(task_id, task_type, payload, status, progress, error_msg, create_time, update_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "t-upload-35m",
            "pipeline",
            payload_upload,
            "RUNNING",
            0.1,
            "",
            now.isoformat(),
            (now - timedelta(minutes=35)).isoformat(),
        ),
    )
    conn.execute(
        """
        INSERT INTO task_queue(task_id, task_type, payload, status, progress, error_msg, create_time, update_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "t-other-25m",
            "pipeline",
            payload_other,
            "RUNNING",
            0.1,
            "",
            now.isoformat(),
            (now - timedelta(minutes=25)).isoformat(),
        ),
    )
    conn.commit()

    monkeypatch.setenv("MEDIA_TOOLS_TASK_STALE_MINUTES", "20")
    cleanup_stale_tasks(conn)

    by_id = {
        row["task_id"]: dict(row)
        for row in conn.execute("SELECT task_id, status FROM task_queue").fetchall()
    }

    assert by_id["t-upload-25m"]["status"] == "RUNNING"
    assert by_id["t-upload-35m"]["status"] == "FAILED"
    assert by_id["t-other-25m"]["status"] == "FAILED"


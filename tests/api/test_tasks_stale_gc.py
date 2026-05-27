import sqlite3
from datetime import datetime, timedelta

from media_tools.scheduler.ops import cleanup_stale_tasks


def test_cleanup_stale_tasks_marks_long_running_failed(monkeypatch) -> None:
    """GC 由 scheduler 后台 job 调用 cleanup_stale_tasks 完成；
    本测试直接验证函数行为，不再依赖 GET /tasks/history 触发。"""
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
    stale_update_time = (now - timedelta(minutes=25)).isoformat()
    conn.execute(
        """
        INSERT INTO task_queue(task_id, task_type, payload, status, progress, error_msg, create_time, update_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "t-stale",
            "pipeline",
            "{}",
            "RUNNING",
            0.2,
            "",
            now.isoformat(),
            stale_update_time,
        ),
    )
    conn.commit()

    monkeypatch.setenv("MEDIA_TOOLS_TASK_STALE_MINUTES", "20")
    cleanup_stale_tasks(conn)

    row = conn.execute("SELECT status, error_msg FROM task_queue WHERE task_id = ?", ("t-stale",)).fetchone()
    assert row["status"] == "FAILED"
    assert row["error_msg"]

"""Tests for media_tools.scheduler.ops."""

from __future__ import annotations

import json
import sqlite3
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from media_tools.scheduler.ops import (
    DEFAULT_TASK_STALE_MINUTES,
    SERVER_RESTART_ERROR,
    UPLOAD_STAGE_STALE_MINUTES,
    _extract_payload_pipeline_stage,
    _fail_task,
    _get_stale_minutes_for_stage,
    _mark_task_cancelled,
    cleanup_stale_tasks,
    update_task_progress,
)


def _make_in_memory_conn() -> sqlite3.Connection:
    """Create an in-memory SQLite connection with the task_queue schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE task_queue (
            task_id TEXT PRIMARY KEY,
            task_type TEXT,
            payload TEXT,
            status TEXT,
            progress REAL,
            error_msg TEXT,
            create_time TEXT,
            update_time TEXT,
            auto_retry INTEGER DEFAULT 0
        )"""
    )
    conn.commit()
    return conn


@contextmanager
def _fake_get_db_connection(conn: sqlite3.Connection):
    """Context manager that yields the given connection."""
    yield conn


# ---------------------------------------------------------------------------
# Pure function tests: _extract_payload_pipeline_stage
# ---------------------------------------------------------------------------


class TestExtractPayloadPipelineStage(unittest.TestCase):
    """Tests for _extract_payload_pipeline_stage."""

    def test_none_returns_empty(self):
        self.assertEqual(_extract_payload_pipeline_stage(None), "")

    def test_empty_string_returns_empty(self):
        self.assertEqual(_extract_payload_pipeline_stage(""), "")

    def test_invalid_json_returns_empty(self):
        self.assertEqual(_extract_payload_pipeline_stage("not json{{"), "")

    def test_valid_json_no_pipeline_progress_returns_empty(self):
        self.assertEqual(_extract_payload_pipeline_stage('{"msg": "hello"}'), "")

    def test_valid_json_pipeline_progress_not_dict(self):
        payload = json.dumps({"pipeline_progress": "not_a_dict"})
        self.assertEqual(_extract_payload_pipeline_stage(payload), "")

    def test_valid_json_pipeline_progress_missing_stage(self):
        payload = json.dumps({"pipeline_progress": {"other": "value"}})
        self.assertEqual(_extract_payload_pipeline_stage(payload), "")

    def test_valid_json_stage_not_string(self):
        payload = json.dumps({"pipeline_progress": {"stage": 42}})
        self.assertEqual(_extract_payload_pipeline_stage(payload), "")

    def test_valid_json_with_stage(self):
        payload = json.dumps({"pipeline_progress": {"stage": "download"}})
        self.assertEqual(_extract_payload_pipeline_stage(payload), "download")

    def test_stage_whitespace_stripped(self):
        payload = json.dumps({"pipeline_progress": {"stage": "  upload  "}})
        self.assertEqual(_extract_payload_pipeline_stage(payload), "upload")

    def test_non_dict_json_returns_empty(self):
        self.assertEqual(_extract_payload_pipeline_stage('"just a string"'), "")

    def test_list_json_returns_empty(self):
        self.assertEqual(_extract_payload_pipeline_stage("[1, 2, 3]"), "")


# ---------------------------------------------------------------------------
# Pure function tests: _get_stale_minutes_for_stage
# ---------------------------------------------------------------------------


class TestGetStaleMinutesForStage(unittest.TestCase):
    """Tests for _get_stale_minutes_for_stage."""

    def test_upload_stage_returns_max_of_default_and_upload(self):
        # default < UPLOAD_STAGE_STALE_MINUTES -> returns upload constant
        result = _get_stale_minutes_for_stage("upload", 10)
        self.assertEqual(result, max(10, UPLOAD_STAGE_STALE_MINUTES))

    def test_upload_stage_default_already_larger(self):
        result = _get_stale_minutes_for_stage("upload", 999)
        self.assertEqual(result, 999)

    def test_upload_stage_default_equal(self):
        result = _get_stale_minutes_for_stage("upload", UPLOAD_STAGE_STALE_MINUTES)
        self.assertEqual(result, UPLOAD_STAGE_STALE_MINUTES)

    def test_non_upload_stage_returns_default(self):
        result = _get_stale_minutes_for_stage("download", 15)
        self.assertEqual(result, 15)

    def test_stage_case_insensitive(self):
        result = _get_stale_minutes_for_stage("UPLOAD", 10)
        self.assertEqual(result, max(10, UPLOAD_STAGE_STALE_MINUTES))

    def test_stage_whitespace_trimmed(self):
        result = _get_stale_minutes_for_stage("  Upload  ", 10)
        self.assertEqual(result, max(10, UPLOAD_STAGE_STALE_MINUTES))

    def test_empty_stage_returns_default(self):
        result = _get_stale_minutes_for_stage("", 20)
        self.assertEqual(result, 20)


# ---------------------------------------------------------------------------
# cleanup_stale_tasks — uses real in-memory SQLite
# ---------------------------------------------------------------------------


class TestCleanupStaleTasks(unittest.TestCase):
    """Tests for cleanup_stale_tasks."""

    def _insert_task(self, conn, task_id, status, update_time, payload="{}"):
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, "pipeline", status, 0.0, payload, update_time, update_time),
        )
        conn.commit()

    def test_old_running_task_marked_failed(self):
        conn = _make_in_memory_conn()
        old_time = (datetime.now() - timedelta(minutes=60)).isoformat()
        self._insert_task(conn, "t1", "RUNNING", old_time)

        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=20):
            count = cleanup_stale_tasks(conn, stale_minutes=20)

        self.assertEqual(count, 1)
        row = conn.execute("SELECT status, error_msg FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "FAILED")
        self.assertIn("自动标记", row["error_msg"])
        conn.close()

    def test_old_pending_task_marked_failed(self):
        conn = _make_in_memory_conn()
        old_time = (datetime.now() - timedelta(minutes=60)).isoformat()
        self._insert_task(conn, "t1", "PENDING", old_time)

        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=20):
            count = cleanup_stale_tasks(conn, stale_minutes=20)

        self.assertEqual(count, 1)
        row = conn.execute("SELECT status FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "FAILED")
        conn.close()

    def test_recent_task_not_touched(self):
        conn = _make_in_memory_conn()
        recent_time = (datetime.now() - timedelta(minutes=5)).isoformat()
        self._insert_task(conn, "t1", "RUNNING", recent_time)

        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=20):
            count = cleanup_stale_tasks(conn, stale_minutes=20)

        self.assertEqual(count, 0)
        row = conn.execute("SELECT status FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "RUNNING")
        conn.close()

    def test_completed_task_not_touched(self):
        conn = _make_in_memory_conn()
        old_time = (datetime.now() - timedelta(minutes=60)).isoformat()
        self._insert_task(conn, "t1", "COMPLETED", old_time)

        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=20):
            count = cleanup_stale_tasks(conn, stale_minutes=20)

        self.assertEqual(count, 0)
        row = conn.execute("SELECT status FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "COMPLETED")
        conn.close()

    def test_failed_task_not_touched(self):
        conn = _make_in_memory_conn()
        old_time = (datetime.now() - timedelta(minutes=60)).isoformat()
        self._insert_task(conn, "t1", "FAILED", old_time)

        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=20):
            count = cleanup_stale_tasks(conn, stale_minutes=20)

        self.assertEqual(count, 0)
        row = conn.execute("SELECT status FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "FAILED")
        conn.close()

    def test_cancelled_task_not_touched(self):
        conn = _make_in_memory_conn()
        old_time = (datetime.now() - timedelta(minutes=60)).isoformat()
        self._insert_task(conn, "t1", "CANCELLED", old_time)

        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=20):
            count = cleanup_stale_tasks(conn, stale_minutes=20)

        self.assertEqual(count, 0)
        row = conn.execute("SELECT status FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "CANCELLED")
        conn.close()

    def test_startup_uses_restart_error_message(self):
        conn = _make_in_memory_conn()
        old_time = (datetime.now() - timedelta(minutes=60)).isoformat()
        self._insert_task(conn, "t1", "RUNNING", old_time)

        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=20):
            cleanup_stale_tasks(conn, stale_minutes=20, is_startup=True)

        row = conn.execute("SELECT status, error_msg FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "FAILED")
        self.assertEqual(row["error_msg"], SERVER_RESTART_ERROR)
        conn.close()

    def test_preserves_existing_error_message(self):
        conn = _make_in_memory_conn()
        old_time = (datetime.now() - timedelta(minutes=60)).isoformat()
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, error_msg, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("t1", "pipeline", "RUNNING", 0.0, "{}", "original error", old_time, old_time),
        )
        conn.commit()

        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=20):
            cleanup_stale_tasks(conn, stale_minutes=20)

        row = conn.execute("SELECT error_msg FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["error_msg"], "original error")
        conn.close()

    def test_upload_stage_gets_longer_timeout(self):
        conn = _make_in_memory_conn()
        # 25 minutes old: stale with default=20, but NOT stale with upload=30
        old_time = (datetime.now() - timedelta(minutes=25)).isoformat()
        payload = json.dumps({"pipeline_progress": {"stage": "upload"}})
        self._insert_task(conn, "t1", "RUNNING", old_time, payload=payload)

        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=20):
            count = cleanup_stale_tasks(conn, stale_minutes=20)

        self.assertEqual(count, 0)  # upload stage has 30 min timeout, so 25 min is not stale
        row = conn.execute("SELECT status FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "RUNNING")
        conn.close()

    def test_upload_stage_stale_at_35_minutes(self):
        conn = _make_in_memory_conn()
        old_time = (datetime.now() - timedelta(minutes=35)).isoformat()
        payload = json.dumps({"pipeline_progress": {"stage": "upload"}})
        self._insert_task(conn, "t1", "RUNNING", old_time, payload=payload)

        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=20):
            count = cleanup_stale_tasks(conn, stale_minutes=20)

        self.assertEqual(count, 1)
        row = conn.execute("SELECT status FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "FAILED")
        conn.close()

    def test_invalid_update_time_skipped(self):
        conn = _make_in_memory_conn()
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("t1", "pipeline", "RUNNING", 0.0, "{}", "not-a-date", "not-a-date"),
        )
        conn.commit()

        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=20):
            count = cleanup_stale_tasks(conn, stale_minutes=20)

        self.assertEqual(count, 0)  # invalid date is skipped, not marked
        row = conn.execute("SELECT status FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "RUNNING")
        conn.close()

    def test_cleanup_deletes_old_failed_rows(self):
        conn = _make_in_memory_conn()
        # FAILED row older than 1 day should be deleted
        old_time = (datetime.now() - timedelta(days=2)).isoformat()
        self._insert_task(conn, "t1", "FAILED", old_time)

        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=20):
            cleanup_stale_tasks(conn, stale_minutes=20)

        remaining = conn.execute("SELECT * FROM task_queue WHERE task_id='t1'").fetchall()
        self.assertEqual(len(remaining), 0)
        conn.close()

    def test_cleanup_keeps_recent_failed_rows(self):
        conn = _make_in_memory_conn()
        recent_time = (datetime.now() - timedelta(hours=1)).isoformat()
        self._insert_task(conn, "t1", "FAILED", recent_time)

        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=20):
            cleanup_stale_tasks(conn, stale_minutes=20)

        remaining = conn.execute("SELECT * FROM task_queue WHERE task_id='t1'").fetchall()
        self.assertEqual(len(remaining), 1)
        conn.close()

    def test_cleanup_deletes_old_completed_rows(self):
        conn = _make_in_memory_conn()
        old_time = (datetime.now() - timedelta(days=4)).isoformat()
        self._insert_task(conn, "t1", "COMPLETED", old_time)

        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=20):
            cleanup_stale_tasks(conn, stale_minutes=20)

        remaining = conn.execute("SELECT * FROM task_queue WHERE task_id='t1'").fetchall()
        self.assertEqual(len(remaining), 0)
        conn.close()

    def test_cleanup_deletes_old_cancelled_rows(self):
        conn = _make_in_memory_conn()
        old_time = (datetime.now() - timedelta(days=2)).isoformat()
        self._insert_task(conn, "t1", "CANCELLED", old_time)

        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=20):
            cleanup_stale_tasks(conn, stale_minutes=20)

        remaining = conn.execute("SELECT * FROM task_queue WHERE task_id='t1'").fetchall()
        self.assertEqual(len(remaining), 0)
        conn.close()

    def test_multiple_tasks_mixed(self):
        conn = _make_in_memory_conn()
        old_time = (datetime.now() - timedelta(minutes=60)).isoformat()
        recent_time = (datetime.now() - timedelta(minutes=5)).isoformat()
        self._insert_task(conn, "old_running", "RUNNING", old_time)
        self._insert_task(conn, "recent_running", "RUNNING", recent_time)
        self._insert_task(conn, "old_completed", "COMPLETED", old_time)

        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=20):
            count = cleanup_stale_tasks(conn, stale_minutes=20)

        self.assertEqual(count, 1)  # only old_running
        row = conn.execute("SELECT status FROM task_queue WHERE task_id='old_running'").fetchone()
        self.assertEqual(row["status"], "FAILED")
        row = conn.execute("SELECT status FROM task_queue WHERE task_id='recent_running'").fetchone()
        self.assertEqual(row["status"], "RUNNING")
        conn.close()

    def test_default_stale_minutes_zero_falls_back(self):
        conn = _make_in_memory_conn()
        old_time = (datetime.now() - timedelta(minutes=25)).isoformat()
        self._insert_task(conn, "t1", "RUNNING", old_time)

        # stale_minutes=0 triggers the fallback to DEFAULT_TASK_STALE_MINUTES
        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=DEFAULT_TASK_STALE_MINUTES):
            count = cleanup_stale_tasks(conn, stale_minutes=0)

        self.assertEqual(count, 1)
        conn.close()

    def test_stale_minutes_none_uses_config(self):
        conn = _make_in_memory_conn()
        old_time = (datetime.now() - timedelta(minutes=60)).isoformat()
        self._insert_task(conn, "t1", "RUNNING", old_time)

        with patch("media_tools.scheduler.ops.get_task_stale_minutes", return_value=20):
            count = cleanup_stale_tasks(conn, stale_minutes=None)

        self.assertEqual(count, 1)
        conn.close()


# ---------------------------------------------------------------------------
# Async function tests — update_task_progress, _mark_task_cancelled, _fail_task
# ---------------------------------------------------------------------------


class TestUpdateTaskProgress(unittest.IsolatedAsyncioTestCase):
    """Tests for update_task_progress."""

    def _make_shared_conn_ctx(self, conn):
        @contextmanager
        def ctx():
            yield conn

        return ctx

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_updates_running_task_progress(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("t1", "pipeline", "RUNNING", 0.0, '{"msg":"init"}', now, now),
        )
        conn.commit()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await update_task_progress("t1", 0.5, "halfway")

        row = conn.execute("SELECT status, progress FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "RUNNING")
        self.assertAlmostEqual(row["progress"], 0.5)
        mock_broadcast.assert_called_once()
        conn.close()

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_skips_update_if_completed(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("t1", "pipeline", "COMPLETED", 1.0, '{"msg":"done"}', now, now),
        )
        conn.commit()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await update_task_progress("t1", 0.5, "should not update")

        row = conn.execute("SELECT status, progress FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "COMPLETED")
        self.assertAlmostEqual(row["progress"], 1.0)
        mock_broadcast.assert_not_called()
        conn.close()

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_skips_update_if_failed(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("t1", "pipeline", "FAILED", 0.0, '{"msg":"err"}', now, now),
        )
        conn.commit()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await update_task_progress("t1", 0.5, "should not update")

        mock_broadcast.assert_not_called()
        conn.close()

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_skips_update_if_cancelled(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("t1", "pipeline", "CANCELLED", 0.0, '{"msg":"cancelled"}', now, now),
        )
        conn.commit()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await update_task_progress("t1", 0.5, "should not update")

        mock_broadcast.assert_not_called()
        conn.close()

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_creates_task_if_not_found(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await update_task_progress("new_task", 0.3, "creating", task_type="download")

        row = conn.execute("SELECT * FROM task_queue WHERE task_id='new_task'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "RUNNING")
        self.assertAlmostEqual(row["progress"], 0.3)
        self.assertEqual(row["task_type"], "download")
        mock_broadcast.assert_called_once()
        conn.close()

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_creates_task_with_pipeline_progress(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await update_task_progress("t1", 0.5, "msg", stage="download", pipeline_progress={"step": 2})

        row = conn.execute("SELECT payload FROM task_queue WHERE task_id='t1'").fetchone()
        payload = json.loads(row["payload"])
        self.assertEqual(payload["pipeline_progress"]["stage"], "download")
        self.assertEqual(payload["pipeline_progress"]["step"], 2)
        conn.close()

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_updates_pending_task_to_running(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("t1", "pipeline", "PENDING", 0.0, '{"msg":"init"}', now, now),
        )
        conn.commit()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await update_task_progress("t1", 0.5, "started")

        row = conn.execute("SELECT status FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "RUNNING")
        mock_broadcast.assert_called_once()
        conn.close()

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_broadcast_not_called_on_db_error(self, mock_broadcast, _mock_retry):
        """If get_db_connection raises, no broadcast should happen."""

        def raise_error():
            raise OSError("disk full")

        # get_db_connection is used as a context manager, so we need
        # the context manager to raise on __enter__
        @contextmanager
        def broken_conn():
            raise OSError("disk full")
            yield  # pragma: no cover

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=broken_conn):
            await update_task_progress("t1", 0.5, "msg")

        mock_broadcast.assert_not_called()


class TestMarkTaskCancelled(unittest.IsolatedAsyncioTestCase):
    """Tests for _mark_task_cancelled."""

    def _make_shared_conn_ctx(self, conn):
        @contextmanager
        def ctx():
            yield conn

        return ctx

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_marks_running_task_cancelled(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("t1", "pipeline", "RUNNING", 0.5, '{"msg":"working"}', now, now),
        )
        conn.commit()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await _mark_task_cancelled("t1", "pipeline")

        row = conn.execute("SELECT status FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "CANCELLED")
        mock_broadcast.assert_called_once()
        conn.close()

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_marks_pending_task_cancelled(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("t1", "pipeline", "PENDING", 0.0, "{}", now, now),
        )
        conn.commit()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await _mark_task_cancelled("t1", "pipeline")

        row = conn.execute("SELECT status FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "CANCELLED")
        mock_broadcast.assert_called_once()
        conn.close()

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_skips_if_already_completed(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("t1", "pipeline", "COMPLETED", 1.0, '{"msg":"done"}', now, now),
        )
        conn.commit()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await _mark_task_cancelled("t1", "pipeline")

        row = conn.execute("SELECT status FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "COMPLETED")
        mock_broadcast.assert_not_called()
        conn.close()

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_skips_if_already_cancelled(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("t1", "pipeline", "CANCELLED", 0.0, "{}", now, now),
        )
        conn.commit()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await _mark_task_cancelled("t1", "pipeline")

        row = conn.execute("SELECT status FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "CANCELLED")
        # CANCELLED is not IN ('PENDING', 'RUNNING'), so no update happens
        mock_broadcast.assert_not_called()
        conn.close()

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_nonexistent_task_no_broadcast(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await _mark_task_cancelled("nonexistent", "pipeline")

        mock_broadcast.assert_not_called()
        conn.close()


class TestFailTask(unittest.IsolatedAsyncioTestCase):
    """Tests for _fail_task."""

    def _make_shared_conn_ctx(self, conn):
        @contextmanager
        def ctx():
            yield conn

        return ctx

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_marks_task_failed(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("t1", "pipeline", "RUNNING", 0.5, '{"msg":"working"}', now, now),
        )
        conn.commit()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await _fail_task("t1", "pipeline", "something broke")

        row = conn.execute("SELECT status, error_msg FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "FAILED")
        self.assertEqual(row["error_msg"], "something broke")
        mock_broadcast.assert_called_once()
        _mock_retry.assert_called_once_with("t1")
        conn.close()

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_fails_pending_task(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("t1", "pipeline", "PENDING", 0.0, "{}", now, now),
        )
        conn.commit()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await _fail_task("t1", "pipeline", "init failed")

        row = conn.execute("SELECT status, error_msg FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "FAILED")
        self.assertEqual(row["error_msg"], "init failed")
        conn.close()

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_skips_if_already_completed(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("t1", "pipeline", "COMPLETED", 1.0, '{"msg":"done"}', now, now),
        )
        conn.commit()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await _fail_task("t1", "pipeline", "should not fail")

        row = conn.execute("SELECT status, error_msg FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "COMPLETED")
        self.assertIsNone(row["error_msg"])
        mock_broadcast.assert_not_called()
        _mock_retry.assert_not_called()
        conn.close()

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_skips_if_already_cancelled(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("t1", "pipeline", "CANCELLED", 0.0, "{}", now, now),
        )
        conn.commit()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await _fail_task("t1", "pipeline", "should not fail")

        row = conn.execute("SELECT status FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "CANCELLED")
        mock_broadcast.assert_not_called()
        conn.close()

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_already_failed_can_be_re_failed(self, mock_broadcast, _mock_retry):
        """_fail_task does NOT exclude FAILED in its WHERE clause, so a FAILED
        task can be re-failed with a new error message and will re-trigger
        schedule_auto_retry."""
        conn = _make_in_memory_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("t1", "pipeline", "FAILED", 0.0, "{}", now, now),
        )
        conn.commit()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await _fail_task("t1", "pipeline", "new error")

        row = conn.execute("SELECT status, error_msg FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["status"], "FAILED")
        self.assertEqual(row["error_msg"], "new error")
        mock_broadcast.assert_called_once()
        _mock_retry.assert_called_once_with("t1")
        conn.close()

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_nonexistent_task_no_broadcast(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await _fail_task("nonexistent", "pipeline", "error")

        mock_broadcast.assert_not_called()
        _mock_retry.assert_not_called()
        conn.close()

    @patch("media_tools.scheduler.ops.schedule_auto_retry")
    @patch("media_tools.scheduler.ops.manager.broadcast", new_callable=AsyncMock)
    async def test_error_converted_to_string(self, mock_broadcast, _mock_retry):
        conn = _make_in_memory_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("t1", "pipeline", "RUNNING", 0.5, "{}", now, now),
        )
        conn.commit()

        with patch("media_tools.scheduler.ops.get_db_connection", side_effect=self._make_shared_conn_ctx(conn)):
            await _fail_task("t1", "pipeline", 42)

        row = conn.execute("SELECT error_msg FROM task_queue WHERE task_id='t1'").fetchone()
        self.assertEqual(row["error_msg"], "42")
        conn.close()


if __name__ == "__main__":
    unittest.main()

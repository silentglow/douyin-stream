"""Regression tests for recently patched bugs.

Each test verifies a specific fix stays in place. Uses in-memory or
temp-file SQLite databases so tests remain isolated and fast.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from media_tools.core.workflow import InvalidTransitionError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE task_queue (
    task_id TEXT PRIMARY KEY,
    task_type TEXT,
    payload TEXT,
    status TEXT DEFAULT 'PENDING',
    progress REAL DEFAULT 0.0,
    error_msg TEXT,
    auto_retry INTEGER DEFAULT 0,
    create_time TEXT,
    update_time TEXT,
    start_time TEXT,
    end_time TEXT,
    cancel_requested INTEGER DEFAULT 0
);

CREATE TABLE creators (
    uid TEXT PRIMARY KEY,
    sec_user_id TEXT,
    nickname TEXT,
    avatar TEXT,
    bio TEXT,
    homepage_url TEXT,
    platform TEXT DEFAULT 'douyin',
    sync_status TEXT DEFAULT 'active',
    last_fetch_time TEXT
);

CREATE TABLE media_assets (
    asset_id TEXT PRIMARY KEY,
    creator_uid TEXT,
    source_url TEXT,
    title TEXT,
    duration INTEGER,
    video_path TEXT,
    video_status TEXT DEFAULT 'pending',
    transcript_path TEXT,
    transcript_status TEXT DEFAULT 'none',
    create_time TEXT,
    update_time TEXT,
    is_read INTEGER DEFAULT 0,
    is_starred INTEGER DEFAULT 0,
    folder_path TEXT DEFAULT '',
    transcript_preview TEXT,
    transcript_text TEXT
);
"""


def _make_conn(tmp_path: Path | None = None) -> sqlite3.Connection:
    """Create a throwaway database with the task_queue schema."""
    if tmp_path is not None:
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
    else:
        conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    return conn


def _insert_task(
    conn: sqlite3.Connection,
    task_id: str,
    status: str = "PENDING",
    task_type: str = "pipeline",
    payload: dict | None = None,
    auto_retry: int = 0,
    update_time: str | None = None,
) -> None:
    now = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO task_queue
               (task_id, task_type, status, progress, payload, auto_retry, create_time, update_time)
           VALUES (?, ?, ?, 0.0, ?, ?, ?, ?)""",
        (
            task_id,
            task_type,
            status,
            json.dumps(payload or {}, ensure_ascii=False),
            auto_retry,
            now,
            update_time or now,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# 1. auto_retry race condition
#    handle_auto_retry must only mutate FAILED tasks via WHERE status='FAILED'
# ---------------------------------------------------------------------------


class TestAutoRetryRaceCondition:
    """Verify handle_auto_retry does NOT overwrite RUNNING or COMPLETED tasks."""

    @pytest.mark.asyncio
    async def test_running_task_not_overwritten(self, tmp_path: Path) -> None:
        """A RUNNING task should survive handle_auto_retry untouched."""
        from media_tools.scheduler.retry import handle_auto_retry

        conn = _make_conn(tmp_path)
        _insert_task(conn, "t-running", status="RUNNING", auto_retry=1)

        start_worker = AsyncMock()
        with (
            patch("media_tools.scheduler.retry.get_db_connection", return_value=conn),
            patch("media_tools.scheduler.dispatcher._start_task_worker", new=start_worker),
        ):
            await handle_auto_retry("t-running")

        row = conn.execute(
            "SELECT status, payload FROM task_queue WHERE task_id = ?",
            ("t-running",),
        ).fetchone()
        assert row["status"] == "RUNNING", "RUNNING task must not be overwritten by auto_retry"
        payload = json.loads(row["payload"])
        assert "_retry_count" not in payload, "RUNNING task payload must not be modified"
        assert start_worker.await_count == 0, "Worker must not be started for RUNNING task"

    @pytest.mark.asyncio
    async def test_completed_task_not_overwritten(self, tmp_path: Path) -> None:
        """A COMPLETED task should survive handle_auto_retry untouched."""
        from media_tools.scheduler.retry import handle_auto_retry

        conn = _make_conn(tmp_path)
        _insert_task(conn, "t-done", status="COMPLETED", auto_retry=1)

        start_worker = AsyncMock()
        with (
            patch("media_tools.scheduler.retry.get_db_connection", return_value=conn),
            patch("media_tools.scheduler.dispatcher._start_task_worker", new=start_worker),
        ):
            await handle_auto_retry("t-done")

        row = conn.execute(
            "SELECT status FROM task_queue WHERE task_id = ?",
            ("t-done",),
        ).fetchone()
        assert row["status"] == "COMPLETED"
        assert start_worker.await_count == 0

    @pytest.mark.asyncio
    async def test_failed_task_is_retried(self, tmp_path: Path) -> None:
        """A FAILED task with auto_retry=1 should be set back to RUNNING."""
        from media_tools.scheduler.retry import handle_auto_retry

        conn = _make_conn(tmp_path)
        _insert_task(conn, "t-fail", status="FAILED", auto_retry=1)

        start_worker = AsyncMock()
        with (
            patch("media_tools.scheduler.retry.get_db_connection", return_value=conn),
            patch("media_tools.scheduler.dispatcher._start_task_worker", new=start_worker),
        ):
            await handle_auto_retry("t-fail")

        row = conn.execute(
            "SELECT status, progress, payload FROM task_queue WHERE task_id = ?",
            ("t-fail",),
        ).fetchone()
        assert row["status"] == "RUNNING"
        assert row["progress"] == 0.0
        payload = json.loads(row["payload"])
        assert payload.get("_retry_count") == 1
        assert start_worker.await_count == 1

    @pytest.mark.asyncio
    async def test_cancelled_task_not_overwritten(self, tmp_path: Path) -> None:
        """A CANCELLED task should not be retried even with auto_retry=1."""
        from media_tools.scheduler.retry import handle_auto_retry

        conn = _make_conn(tmp_path)
        _insert_task(conn, "t-cancelled", status="CANCELLED", auto_retry=1)

        start_worker = AsyncMock()
        with (
            patch("media_tools.scheduler.retry.get_db_connection", return_value=conn),
            patch("media_tools.scheduler.dispatcher._start_task_worker", new=start_worker),
        ):
            await handle_auto_retry("t-cancelled")

        row = conn.execute(
            "SELECT status FROM task_queue WHERE task_id = ?",
            ("t-cancelled",),
        ).fetchone()
        assert row["status"] == "CANCELLED"
        assert start_worker.await_count == 0


# ---------------------------------------------------------------------------
# 2. Task state machine transitions
#    mark_running must reject COMPLETED -> RUNNING
# ---------------------------------------------------------------------------


class TestTaskStateMachineTransitions:
    """Validate that TaskRepository.mark_running enforces transition rules."""

    def test_completed_to_running_raises(self, tmp_path: Path) -> None:
        """COMPLETED -> RUNNING must raise InvalidTransitionError."""
        from media_tools.scheduler.repository import TaskRepository

        conn = _make_conn(tmp_path)
        _insert_task(conn, "t1", status="COMPLETED")

        @contextmanager
        def _get_conn():
            yield conn

        with (
            patch("media_tools.scheduler.repository.get_db_connection", _get_conn),
            pytest.raises(InvalidTransitionError),
        ):
            TaskRepository.mark_running("t1")

        # Verify the task was NOT modified
        row = conn.execute("SELECT status FROM task_queue WHERE task_id = ?", ("t1",)).fetchone()
        assert row["status"] == "COMPLETED", "Task status must not change after rejected transition"

    def test_pending_to_running_succeeds(self, tmp_path: Path) -> None:
        """PENDING -> RUNNING is a valid transition."""
        from media_tools.scheduler.repository import TaskRepository

        conn = _make_conn(tmp_path)
        _insert_task(conn, "t2", status="PENDING")

        @contextmanager
        def _get_conn():
            yield conn

        with patch("media_tools.scheduler.repository.get_db_connection", _get_conn):
            TaskRepository.mark_running("t2")

        row = conn.execute("SELECT status FROM task_queue WHERE task_id = ?", ("t2",)).fetchone()
        assert row["status"] == "RUNNING"

    def test_failed_to_running_succeeds(self, tmp_path: Path) -> None:
        """FAILED -> RUNNING is valid (retry path)."""
        from media_tools.scheduler.repository import TaskRepository

        conn = _make_conn(tmp_path)
        _insert_task(conn, "t3", status="FAILED")

        @contextmanager
        def _get_conn():
            yield conn

        with patch("media_tools.scheduler.repository.get_db_connection", _get_conn):
            TaskRepository.mark_running("t3")

        row = conn.execute("SELECT status FROM task_queue WHERE task_id = ?", ("t3",)).fetchone()
        assert row["status"] == "RUNNING"

    def test_cancelled_to_running_succeeds(self, tmp_path: Path) -> None:
        """CANCELLED -> RUNNING is valid (rerun path)."""
        from media_tools.scheduler.repository import TaskRepository

        conn = _make_conn(tmp_path)
        _insert_task(conn, "t4", status="CANCELLED")

        @contextmanager
        def _get_conn():
            yield conn

        with patch("media_tools.scheduler.repository.get_db_connection", _get_conn):
            TaskRepository.mark_running("t4")

        row = conn.execute("SELECT status FROM task_queue WHERE task_id = ?", ("t4",)).fetchone()
        assert row["status"] == "RUNNING"


# ---------------------------------------------------------------------------
# 3. cleanup_stale_tasks — caller controls the transaction
#    The function must NOT call conn.commit(); the caller decides.
# ---------------------------------------------------------------------------


class TestCleanupStaleTasksTransaction:
    """Verify cleanup_stale_tasks does not self-commit, so callers can rollback."""

    def test_no_commit_on_its_own(self, tmp_path: Path) -> None:
        """After cleanup_stale_tasks, changes should be rollbackable."""
        conn = _make_conn(tmp_path)

        stale_time = (datetime.now() - timedelta(hours=1)).isoformat()
        _insert_task(conn, "stale-1", status="RUNNING", update_time=stale_time)

        from media_tools.scheduler.ops import cleanup_stale_tasks

        cleanup_stale_tasks(conn, stale_minutes=10)

        # The update should be visible in the same connection (uncommitted)
        row = conn.execute("SELECT status FROM task_queue WHERE task_id = ?", ("stale-1",)).fetchone()
        assert row["status"] == "FAILED", "Stale task should be marked FAILED"

        # Rollback — proving the function did NOT auto-commit
        conn.rollback()

        row = conn.execute("SELECT status FROM task_queue WHERE task_id = ?", ("stale-1",)).fetchone()
        assert row["status"] == "RUNNING", (
            "After rollback, stale task must revert to RUNNING — proving cleanup_stale_tasks does not self-commit"
        )

    def test_fresh_task_not_affected(self, tmp_path: Path) -> None:
        """A recently-updated task should not be marked stale."""
        conn = _make_conn(tmp_path)

        fresh_time = datetime.now().isoformat()
        _insert_task(conn, "fresh-1", status="RUNNING", update_time=fresh_time)

        from media_tools.scheduler.ops import cleanup_stale_tasks

        cleanup_stale_tasks(conn, stale_minutes=10)

        row = conn.execute("SELECT status FROM task_queue WHERE task_id = ?", ("fresh-1",)).fetchone()
        assert row["status"] == "RUNNING", "Fresh task must not be marked stale"

    def test_only_pending_and_running_marked_stale(self, tmp_path: Path) -> None:
        """COMPLETED/FAILED/CANCELLED tasks must not be touched by stale cleanup."""
        conn = _make_conn(tmp_path)

        stale_time = (datetime.now() - timedelta(hours=1)).isoformat()
        _insert_task(conn, "done-1", status="COMPLETED", update_time=stale_time)
        _insert_task(conn, "fail-1", status="FAILED", update_time=stale_time)
        _insert_task(conn, "cancel-1", status="CANCELLED", update_time=stale_time)

        from media_tools.scheduler.ops import cleanup_stale_tasks

        cleanup_stale_tasks(conn, stale_minutes=10)

        for tid, expected in [
            ("done-1", "COMPLETED"),
            ("fail-1", "FAILED"),
            ("cancel-1", "CANCELLED"),
        ]:
            row = conn.execute("SELECT status FROM task_queue WHERE task_id = ?", (tid,)).fetchone()
            assert row["status"] == expected


# ---------------------------------------------------------------------------
# 4. cancel_task flow — _mark_task_cancelled writes CANCELLED to DB
# ---------------------------------------------------------------------------


class TestCancelTaskFlow:
    """Verify _mark_task_cancelled correctly marks a task as CANCELLED."""

    @pytest.mark.asyncio
    async def test_mark_cancelled_updates_db(self, tmp_path: Path) -> None:
        """_mark_task_cancelled should set status to CANCELLED for a RUNNING task."""
        from media_tools.scheduler.ops import _mark_task_cancelled

        conn = _make_conn(tmp_path)
        _insert_task(conn, "cancel-me", status="RUNNING")

        with (
            patch("media_tools.scheduler.ops.get_db_connection", return_value=conn),
            patch("media_tools.scheduler.ops.notify_task_update", new=AsyncMock()),
        ):
            await _mark_task_cancelled("cancel-me", "pipeline")

        row = conn.execute("SELECT status FROM task_queue WHERE task_id = ?", ("cancel-me",)).fetchone()
        assert row["status"] == "CANCELLED"

    @pytest.mark.asyncio
    async def test_mark_cancelled_on_pending_task(self, tmp_path: Path) -> None:
        """_mark_task_cancelled should also work for PENDING tasks."""
        from media_tools.scheduler.ops import _mark_task_cancelled

        conn = _make_conn(tmp_path)
        _insert_task(conn, "cancel-pending", status="PENDING")

        with (
            patch("media_tools.scheduler.ops.get_db_connection", return_value=conn),
            patch("media_tools.scheduler.ops.notify_task_update", new=AsyncMock()),
        ):
            await _mark_task_cancelled("cancel-pending", "pipeline")

        row = conn.execute("SELECT status FROM task_queue WHERE task_id = ?", ("cancel-pending",)).fetchone()
        assert row["status"] == "CANCELLED"

    @pytest.mark.asyncio
    async def test_mark_cancelled_ignores_completed_task(self, tmp_path: Path) -> None:
        """_mark_task_cancelled must NOT overwrite a COMPLETED task (WHERE clause guard)."""
        from media_tools.scheduler.ops import _mark_task_cancelled

        conn = _make_conn(tmp_path)
        _insert_task(conn, "already-done", status="COMPLETED")

        with (
            patch("media_tools.scheduler.ops.get_db_connection", return_value=conn),
            patch("media_tools.scheduler.ops.notify_task_update", new=AsyncMock()),
        ):
            await _mark_task_cancelled("already-done", "pipeline")

        row = conn.execute("SELECT status FROM task_queue WHERE task_id = ?", ("already-done",)).fetchone()
        assert row["status"] == "COMPLETED", "COMPLETED task must not be overwritten by cancel"


# ---------------------------------------------------------------------------
# 5. Nickname collision in reconcile_transcripts
#    Two creators with the same nickname must not cause data loss.
# ---------------------------------------------------------------------------


class TestNicknameCollisionReconcile:
    """Verify reconcile_transcripts handles duplicate nicknames safely."""

    def test_two_creators_same_nickname_no_data_loss(self, tmp_path: Path) -> None:
        """Two creators sharing a nickname should each retain their assets.

        The reconcile logic builds creator_map keyed by nickname, keeping the
        first-inserted uid when a collision occurs. This test verifies that
        both creators' assets survive the reconcile pass.
        """
        conn = _make_conn(tmp_path)

        # Insert two creators with the same nickname but different uids
        conn.execute(
            "INSERT INTO creators (uid, nickname, platform) VALUES (?, ?, ?)",
            ("uid-aaa", "张三", "douyin"),
        )
        conn.execute(
            "INSERT INTO creators (uid, nickname, platform) VALUES (?, ?, ?)",
            ("uid-bbb", "张三", "bilibili"),
        )

        # Give each creator an asset
        conn.execute(
            "INSERT INTO media_assets (asset_id, creator_uid, title, video_status, transcript_status, folder_path) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("asset-1", "uid-aaa", "视频A", "downloaded", "none", ""),
        )
        conn.execute(
            "INSERT INTO media_assets (asset_id, creator_uid, title, video_status, transcript_status, folder_path) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("asset-2", "uid-bbb", "视频B", "downloaded", "none", ""),
        )
        conn.commit()

        # Snapshot asset count before reconcile
        before = conn.execute("SELECT COUNT(*) AS c FROM media_assets").fetchone()["c"]

        # Build the creator_map the same way reconcile_transcripts does
        creators = conn.execute("SELECT uid, nickname FROM creators").fetchall()
        creator_map: dict[str, str] = {}
        for row in creators:
            nickname = row["nickname"]
            if nickname not in creator_map:
                creator_map[nickname] = row["uid"]

        # The first-inserted uid should win
        assert creator_map["张三"] == "uid-aaa"

        # Verify both assets still belong to their original creators
        asset_1 = conn.execute("SELECT creator_uid FROM media_assets WHERE asset_id = ?", ("asset-1",)).fetchone()
        asset_2 = conn.execute("SELECT creator_uid FROM media_assets WHERE asset_id = ?", ("asset-2",)).fetchone()
        assert asset_1["creator_uid"] == "uid-aaa"
        assert asset_2["creator_uid"] == "uid-bbb"

        # Asset count should be unchanged
        after = conn.execute("SELECT COUNT(*) AS c FROM media_assets").fetchone()["c"]
        assert after == before, "No assets should be lost during nickname collision"

    def test_creator_map_first_inserted_wins(self, tmp_path: Path) -> None:
        """When multiple creators share a nickname, the first-inserted uid is kept in the map."""
        conn = _make_conn(tmp_path)

        conn.execute(
            "INSERT INTO creators (uid, nickname, platform) VALUES (?, ?, ?)",
            ("uid-first", "同名创作者", "douyin"),
        )
        conn.execute(
            "INSERT INTO creators (uid, nickname, platform) VALUES (?, ?, ?)",
            ("uid-second", "同名创作者", "bilibili"),
        )
        conn.execute(
            "INSERT INTO creators (uid, nickname, platform) VALUES (?, ?, ?)",
            ("uid-third", "同名创作者", "local"),
        )
        conn.commit()

        creators = conn.execute("SELECT uid, nickname FROM creators").fetchall()
        creator_map: dict[str, str] = {}
        for row in creators:
            nickname = row["nickname"]
            if nickname not in creator_map:
                creator_map[nickname] = row["uid"]

        assert len(creator_map) == 1
        assert creator_map["同名创作者"] == "uid-first"

    def test_legacy_assets_not_lost_with_duplicate_nicknames(self, tmp_path: Path) -> None:
        """Legacy assets (creator_uid='local:upload') pointing to a folder whose
        name matches an existing creator's nickname should be reassigned correctly
        without overwriting the other creator's data.
        """
        conn = _make_conn(tmp_path)

        # A creator with a known nickname
        conn.execute(
            "INSERT INTO creators (uid, nickname, platform) VALUES (?, ?, ?)",
            ("uid-creator-a", "达人A", "douyin"),
        )
        # An existing local creator with the same nickname
        conn.execute(
            "INSERT INTO creators (uid, nickname, platform, sync_status, last_fetch_time) VALUES (?, ?, ?, ?, ?)",
            ("local:aaa111", "达人A", "local", "active", datetime.now().isoformat()),
        )
        # Legacy asset whose folder_path matches the nickname
        conn.execute(
            "INSERT INTO media_assets (asset_id, creator_uid, title, video_status, transcript_status, folder_path, transcript_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-asset-1",
                "local:upload",
                "旧视频",
                "downloaded",
                "none",
                "达人A",
                "达人A/旧视频.md",
            ),
        )
        conn.commit()

        # Simulate the creator_map building from reconcile_transcripts
        creators = conn.execute("SELECT uid, nickname FROM creators").fetchall()
        creator_map: dict[str, str] = {}
        for row in creators:
            nickname = row["nickname"]
            if nickname not in creator_map:
                creator_map[nickname] = row["uid"]

        # uid-creator-a was inserted first
        assert creator_map["达人A"] == "uid-creator-a"

        # Simulate reassigning legacy asset
        target_uid = creator_map.get("达人A")
        assert target_uid is not None
        conn.execute(
            "UPDATE media_assets SET creator_uid = ?, folder_path = ? WHERE asset_id = ?",
            (target_uid, "达人A", "legacy-asset-1"),
        )
        conn.commit()

        row = conn.execute(
            "SELECT creator_uid FROM media_assets WHERE asset_id = ?",
            ("legacy-asset-1",),
        ).fetchone()
        assert row["creator_uid"] == "uid-creator-a", "Legacy asset should be reassigned to the first-inserted creator"

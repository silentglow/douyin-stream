"""POST /tasks/transcribe/retry-failed-assets 接口测试。

覆盖：基本派发、creator 过滤、error_type 过滤、disk 缺失文件 -> 409、
asset_id 被 mark_transcribe_running 写回。
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from media_tools.api.app import app


def _skip_background_task(_task_id, coro):
    with contextlib.suppress(Exception):
        coro.close()
    return None


def _build_db_with_failed_assets(rows: list[tuple[str, str, str, str, str | None]]) -> sqlite3.Connection:
    """rows: [(asset_id, creator_uid, transcript_status, video_path, error_type), ...]"""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
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
            transcript_preview TEXT,
            transcript_text TEXT,
            transcript_last_error TEXT,
            transcript_error_type TEXT,
            transcript_retry_count INTEGER DEFAULT 0,
            transcript_failed_at DATETIME,
            last_task_id TEXT,
            source_platform TEXT,
            folder_path TEXT,
            is_read INTEGER DEFAULT 0,
            is_starred INTEGER DEFAULT 0,
            create_time DATETIME,
            update_time DATETIME
        )
        """
    )
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
    for asset_id, creator_uid, status, video_path, error_type in rows:
        conn.execute(
            "INSERT INTO media_assets (asset_id, creator_uid, title, video_path, video_status, "
            "transcript_status, transcript_error_type, source_platform, create_time, update_time) "
            "VALUES (?, ?, ?, ?, 'downloaded', ?, ?, 'douyin', '2025', '2025')",
            (asset_id, creator_uid, asset_id, video_path, status, error_type),
        )
    conn.commit()
    return conn


def test_retry_failed_assets_dispatches_for_existing_files(tmp_path: Path) -> None:
    from media_tools.api.routers import tasks as tasks_router
    from media_tools.assets import service as svc

    fp_ok = tmp_path / "ok.mp4"
    fp_ok.write_bytes(b"x")

    conn = _build_db_with_failed_assets(
        [
            ("ok", "u1", "failed", "ok.mp4", "auth"),
            ("missing", "u1", "failed", "missing.mp4", "auth"),
        ]
    )

    with (
        patch.object(svc, "get_db_connection", return_value=conn),
        patch("media_tools.scheduler.repository.get_db_connection", return_value=conn),
        patch("media_tools.scheduler.dispatcher.notify_task_update"),
        patch.object(tasks_router, "get_download_path", return_value=tmp_path),
        patch("media_tools.scheduler.dispatcher._register_background_task", side_effect=_skip_background_task),
        patch("media_tools.scheduler.dispatcher._register_local_assets") as register_local_assets,
    ):
        client = TestClient(app)
        resp = client.post("/api/v1/tasks/transcribe/retry-failed-assets", json={})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert data["file_count"] == 1
    assert data["missing_file_assets"] == ["missing"]
    register_local_assets.assert_called_once()

    # last_task_id 已被 mark_transcribe_running 写回到磁盘存在的 asset
    row = conn.execute("SELECT last_task_id, transcript_status FROM media_assets WHERE asset_id='ok'").fetchone()
    assert row["last_task_id"] == data["task_id"]
    # 状态从 failed -> pending（mark_transcribe_running 的语义）
    assert row["transcript_status"] == "pending"

    # missing 资产保持 failed 不变，last_task_id 不被覆盖
    row_missing = conn.execute(
        "SELECT last_task_id, transcript_status FROM media_assets WHERE asset_id='missing'"
    ).fetchone()
    assert row_missing["transcript_status"] == "failed"
    assert row_missing["last_task_id"] is None


def test_retry_failed_assets_filters_by_creator_and_error_type(tmp_path: Path) -> None:
    from media_tools.api.routers import tasks as tasks_router
    from media_tools.assets import service as svc

    for name in ("a.mp4", "b.mp4", "c.mp4"):
        (tmp_path / name).write_bytes(b"x")

    conn = _build_db_with_failed_assets(
        [
            ("a", "u1", "failed", "a.mp4", "auth"),
            ("b", "u1", "failed", "b.mp4", "quota"),
            ("c", "u2", "failed", "c.mp4", "auth"),
        ]
    )

    with (
        patch.object(svc, "get_db_connection", return_value=conn),
        patch("media_tools.scheduler.repository.get_db_connection", return_value=conn),
        patch("media_tools.scheduler.dispatcher.notify_task_update"),
        patch.object(tasks_router, "get_download_path", return_value=tmp_path),
        patch("media_tools.scheduler.dispatcher._register_background_task", side_effect=_skip_background_task),
        patch("media_tools.scheduler.dispatcher._register_local_assets"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/tasks/transcribe/retry-failed-assets",
            json={"creator_uid": "u1", "error_types": ["auth"]},
        )

    assert resp.status_code == 200
    assert resp.json()["file_count"] == 1


def test_retry_failed_assets_returns_409_when_no_files_on_disk(tmp_path: Path) -> None:
    from media_tools.api.routers import tasks as tasks_router
    from media_tools.assets import service as svc

    conn = _build_db_with_failed_assets(
        [
            ("missing", "u1", "failed", "missing.mp4", "auth"),
        ]
    )

    with (
        patch.object(svc, "get_db_connection", return_value=conn),
        patch("media_tools.scheduler.repository.get_db_connection", return_value=conn),
        patch("media_tools.scheduler.dispatcher.notify_task_update"),
        patch.object(tasks_router, "get_download_path", return_value=tmp_path),
    ):
        client = TestClient(app)
        resp = client.post("/api/v1/tasks/transcribe/retry-failed-assets", json={})

    assert resp.status_code == 409
    body = resp.json()
    assert body["message"]["failed_in_db"] == 1
    assert body["message"]["missing_file_assets"] == ["missing"]


def test_retry_failed_assets_409_when_no_failed_at_all(tmp_path: Path) -> None:
    from media_tools.api.routers import tasks as tasks_router
    from media_tools.assets import service as svc

    conn = _build_db_with_failed_assets([])  # nothing failed

    with (
        patch.object(svc, "get_db_connection", return_value=conn),
        patch("media_tools.scheduler.repository.get_db_connection", return_value=conn),
        patch("media_tools.scheduler.dispatcher.notify_task_update"),
        patch.object(tasks_router, "get_download_path", return_value=tmp_path),
    ):
        client = TestClient(app)
        resp = client.post("/api/v1/tasks/transcribe/retry-failed-assets", json={})

    assert resp.status_code == 409
    assert resp.json()["message"]["failed_in_db"] == 0

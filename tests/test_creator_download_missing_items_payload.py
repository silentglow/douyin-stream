from __future__ import annotations

import json
import sqlite3
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_creator_download_sets_missing_items_in_payload() -> None:
    from media_tools.workers.creator_sync import CreatorSyncWorker

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE creators (
          uid TEXT PRIMARY KEY,
          sec_user_id TEXT,
          nickname TEXT,
          platform TEXT,
          sync_status TEXT,
          last_fetch_time DATETIME
        );
        CREATE TABLE task_queue (
          task_id TEXT PRIMARY KEY,
          task_type TEXT,
          status TEXT,
          progress REAL,
          payload TEXT,
          error_msg TEXT,
          update_time TEXT
        );
        CREATE TABLE video_metadata (
          aweme_id TEXT PRIMARY KEY,
          uid TEXT NOT NULL,
          desc TEXT
        );
        CREATE TABLE media_assets (
          asset_id TEXT PRIMARY KEY,
          creator_uid TEXT,
          title TEXT,
          video_path TEXT,
          video_status TEXT,
          transcript_status TEXT
        );
        """
    )

    creator_uid = "douyin:123"
    conn.execute(
        "INSERT INTO creators(uid, sec_user_id, nickname, platform, sync_status, last_fetch_time) VALUES(?,?,?,?, 'active', NULL)",
        (creator_uid, "MS4wxxx", "n", "douyin"),
    )
    task_id = "t1"
    conn.execute(
        "INSERT INTO task_queue(task_id, task_type, status, progress, payload, update_time) VALUES(?, ?, 'RUNNING', 0.0, '{}', CURRENT_TIMESTAMP)",
        (task_id, "creator_sync_incremental"),
    )

    conn.execute("INSERT INTO video_metadata(aweme_id, uid, desc) VALUES(?,?,?)", ("a_ok", creator_uid, "ok title"))
    conn.execute(
        "INSERT INTO video_metadata(aweme_id, uid, desc) VALUES(?,?,?)",
        ("a_missing", creator_uid, "missing title"),
    )

    conn.execute(
        "INSERT INTO media_assets(asset_id, creator_uid, title, video_path, video_status, transcript_status) VALUES(?,?,?,?,?,?)",
        ("a_ok", creator_uid, "ok title", "x.mp4", "downloaded", "none"),
    )
    conn.commit()

    with patch("media_tools.workers.creator_sync.get_db_connection", return_value=conn), patch(
        "media_tools.scheduler.ops.get_db_connection",
        return_value=conn,
    ), patch(
        "media_tools.workers.creator_sync.get_runtime_setting_bool",
        return_value=False,
    ), patch(
        "media_tools.workers.base.update_task_progress",
        new=AsyncMock(),
    ), patch(
        "media_tools.workers.base._task_heartbeat",
        new=AsyncMock(),
    ), patch(
        "media_tools.workers.creator_sync.asyncio.to_thread",
        new=AsyncMock(return_value={"success": True, "new_files": []}),
    ):
        await CreatorSyncWorker().execute(task_id, uid=creator_uid, mode="incremental")

    payload_raw = conn.execute("SELECT payload FROM task_queue WHERE task_id = ?", (task_id,)).fetchone()[0]
    payload = json.loads(payload_raw)

    assert payload["missing_items"] == [
        {
            "aweme_id": "a_missing",
            "title": "missing title",
            "status": "manual_required",
            "reason": "未找到已下载文件",
            "attempts": 0,
        }
    ]
    assert any(
        s.get("status") == "manual_required" and s.get("title") == "missing title"
        for s in (payload.get("subtasks") or [])
    )

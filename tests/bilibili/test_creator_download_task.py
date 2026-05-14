from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


class BilibiliCreatorDownloadTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_creator_download_triggers_transcribe_and_deletes_video_when_enabled(self) -> None:
        from media_tools.workers.creator_sync import CreatorSyncWorker

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE creators (
              uid TEXT PRIMARY KEY,
              sec_user_id TEXT,
              nickname TEXT,
              platform TEXT,
              sync_status TEXT,
              last_fetch_time DATETIME
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE task_queue (
              task_id TEXT PRIMARY KEY,
              status TEXT,
              progress REAL,
              payload TEXT,
              error_msg TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE SystemSettings (
              key TEXT PRIMARY KEY,
              value TEXT
            )
            """
        )
        conn.execute("INSERT INTO SystemSettings (key, value) VALUES (?, ?)", ("auto_transcribe", "true"))
        conn.execute("INSERT INTO SystemSettings (key, value) VALUES (?, ?)", ("auto_delete", "true"))

        creator_uid = "bilibili:596133959"
        conn.execute(
            "INSERT INTO creators (uid, sec_user_id, nickname, platform, sync_status) VALUES (?, ?, ?, ?, 'active')",
            (creator_uid, "596133959", "TestUP", "bilibili"),
        )
        task_id = "task-1"
        conn.execute(
            "INSERT INTO task_queue (task_id, status, progress, payload) VALUES (?, 'RUNNING', 0.0, '{}')",
            (task_id,),
        )
        conn.commit()

        tmp_video = Path("/tmp/bili_test_video.mp4")
        tmp_video.write_bytes(b"ok")

        fake_config = SimpleNamespace(is_auto_transcribe=lambda: True, is_auto_delete_video=lambda: True)
        from media_tools.pipeline.models import BatchReport
        report = BatchReport(total=1, success=1, failed=0)
        report.results.append({"video_path": str(tmp_video), "success": True, "error": None, "error_type": "none"})
        orchestrator = SimpleNamespace(transcribe_batch=AsyncMock(return_value=report))

        with patch("media_tools.workers.creator_sync.get_db_connection", return_value=conn), patch(
            "media_tools.scheduler.base.update_task_progress",
            new=AsyncMock(),
        ), patch(
            "media_tools.scheduler.base._task_heartbeat",
            new=AsyncMock(),
        ), patch(
            "media_tools.workers.creator_sync.asyncio.to_thread",
            new=AsyncMock(return_value={"success": True, "new_files": [str(tmp_video)]}),
        ), patch(
            "media_tools.pipeline.orchestrator.create_orchestrator",
            return_value=orchestrator,
        ):
            await CreatorSyncWorker().execute(task_id, uid=creator_uid, mode="incremental")

        orchestrator.transcribe_batch.assert_awaited_once()
        self.assertFalse(tmp_video.exists())


if __name__ == "__main__":
    unittest.main()

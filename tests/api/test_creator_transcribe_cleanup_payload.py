from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def test_creator_transcribe_writes_cleanup_payload_and_deletes_files(tmp_path: Path, monkeypatch) -> None:
    from media_tools.workers.creator_transcribe_worker import CreatorTranscribeWorker

    downloads = tmp_path / "downloads"
    project_root = tmp_path / "proj"
    transcripts_root = project_root / "transcripts"

    creator_folder = "alice"
    video_dir = downloads / creator_folder
    video_dir.mkdir(parents=True, exist_ok=True)
    video = video_dir / "a.mp4"
    wav = video_dir / "a.wav"
    tmp = video_dir / "a.tmp"
    video.write_bytes(b"1")
    wav.write_bytes(b"2")
    tmp.write_bytes(b"3")

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE creators (
          uid TEXT PRIMARY KEY,
          sec_user_id TEXT,
          nickname TEXT,
          platform TEXT,
          sync_status TEXT
        );
        CREATE TABLE media_assets (
          asset_id TEXT PRIMARY KEY,
          creator_uid TEXT,
          source_url TEXT,
          title TEXT,
          video_path TEXT,
          video_status TEXT,
          transcript_status TEXT,
          folder_path TEXT,
          create_time TEXT,
          update_time TEXT
        );
        CREATE TABLE task_queue (
          task_id TEXT PRIMARY KEY,
          task_type TEXT,
          payload TEXT,
          status TEXT,
          progress REAL,
          error_msg TEXT,
          create_time TEXT,
          update_time TEXT,
          auto_retry INTEGER DEFAULT 0
        );
        """
    )
    uid = "u1"
    task_id = "t1"
    conn.execute(
        "INSERT INTO creators(uid, sec_user_id, nickname, platform, sync_status) VALUES(?,?,?,?,?)",
        (uid, "", creator_folder, "douyin", "active"),
    )
    conn.execute(
        """
        INSERT INTO media_assets(asset_id, creator_uid, source_url, title, video_path, video_status, transcript_status, folder_path, create_time, update_time)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        ("a1", uid, "", "a", f"{creator_folder}/a.mp4", "downloaded", "pending", creator_folder, "", ""),
    )
    conn.execute(
        "INSERT INTO task_queue(task_id, task_type, payload, status, progress, error_msg, create_time, update_time) VALUES(?,?,?,?,?,?,?,?)",
        (task_id, "local_transcribe", "{}", "RUNNING", 0.0, "", "", ""),
    )
    conn.commit()

    @contextmanager
    def _get_conn():  # noqa: ANN001
        yield conn

    monkeypatch.setattr("media_tools.workers.creator_transcribe_worker.get_db_connection", _get_conn)
    monkeypatch.setattr("media_tools.scheduler.ops.get_db_connection", _get_conn)
    monkeypatch.setattr("media_tools.scheduler.repository.get_db_connection", _get_conn)
    monkeypatch.setattr("media_tools.scheduler.state.get_db_connection", _get_conn)
    monkeypatch.setattr("media_tools.workers.creator_transcribe_worker.get_download_path", lambda: downloads)
    monkeypatch.setattr("media_tools.workers.creator_transcribe_worker.get_transcripts_path", lambda: transcripts_root)
    monkeypatch.setenv("MEDIA_TOOLS_CLEANUP_RETRY_DELAY", "0")

    async def _fake_run_local_transcribe(file_paths, update_progress_fn=None, delete_after=False, task_id=None):  # noqa: ANN001
        return {
            "success_count": 1,
            "failed_count": 0,
            "total": 1,
            "success_paths": [str(video)],
            "failed_paths": [],
            "subtasks": [],
        }

    monkeypatch.setattr(
        "media_tools.workers.creator_transcribe_worker.run_local_transcribe", _fake_run_local_transcribe
    )

    asyncio.run(CreatorTranscribeWorker().execute(task_id, uid=uid))

    assert not video.exists()
    assert not wav.exists()
    assert not tmp.exists()

    cache_dir = transcripts_root / creator_folder / ".cache" / task_id
    assert not cache_dir.exists()

    row = conn.execute("SELECT status, payload FROM task_queue WHERE task_id=?", (task_id,)).fetchone()
    assert row is not None
    assert row["status"] == "COMPLETED"
    payload = json.loads(row["payload"])
    assert payload["cleanup_cache_dir"] == str(cache_dir)
    assert payload["cleanup_deleted_count"] == 3
    assert payload["cleanup_failed_count"] == 0
    assert payload["cleanup_failed_paths"] == []
    assert payload["pipeline_progress"]["stage"] == "done"

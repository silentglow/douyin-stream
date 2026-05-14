from __future__ import annotations

import sqlite3
from pathlib import Path


def test_db_init_adds_media_assets_folder_path(tmp_path) -> None:
    from media_tools.db.core import init_db

    db_path = tmp_path / "t.db"
    init_db(str(db_path))

    conn = sqlite3.connect(str(db_path))
    cols = [row[1] for row in conn.execute("PRAGMA table_info(media_assets)").fetchall()]
    assert "folder_path" in cols


def test_local_transcribe_request_accepts_directory_root() -> None:
    from media_tools.api.routers.tasks import LocalTranscribeRequest

    req = LocalTranscribeRequest(
        file_paths=["/tmp/a.mp3"],
        delete_after=False,
        directory_root="/tmp",
    )
    assert req.directory_root == "/tmp"


def test_register_local_assets_writes_folder_path(tmp_path, monkeypatch) -> None:
    from media_tools.api.routers import tasks as tasks_router

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE creators (
          uid TEXT PRIMARY KEY,
          sec_user_id TEXT,
          nickname TEXT,
          avatar TEXT,
          bio TEXT,
          platform TEXT,
          sync_status TEXT,
          last_fetch_time DATETIME
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE media_assets (
          asset_id TEXT PRIMARY KEY,
          creator_uid TEXT,
          source_url TEXT,
          title TEXT,
          duration INTEGER,
          video_path TEXT,
          video_status TEXT,
          transcript_path TEXT,
          transcript_status TEXT,
          folder_path TEXT DEFAULT '',
          is_read BOOLEAN DEFAULT 0,
          is_starred BOOLEAN DEFAULT 0,
          create_time DATETIME,
          update_time DATETIME
        )
        """
    )
    conn.commit()

    root = tmp_path / "root"
    sub = root / "chapter1"
    sub.mkdir(parents=True)
    f = sub / "a.mp3"
    f.write_bytes(b"ok")

    monkeypatch.setattr("media_tools.services.local_asset_service.get_db_connection", lambda: conn)

    from media_tools.services.local_asset_service import _register_local_assets
    _register_local_assets([str(f)], delete_after=False, directory_root=str(root))

    row = conn.execute("SELECT folder_path FROM media_assets").fetchone()
    assert row is not None
    assert row["folder_path"] == "chapter1"


def test_list_assets_returns_folder_path(monkeypatch) -> None:
    from media_tools.api.routers import assets as assets_router

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE media_assets (
          asset_id TEXT PRIMARY KEY,
          creator_uid TEXT,
          title TEXT,
          video_status TEXT,
          transcript_status TEXT,
          transcript_path TEXT,
          transcript_preview TEXT,
          folder_path TEXT DEFAULT '',
          is_read BOOLEAN DEFAULT 0,
          is_starred BOOLEAN DEFAULT 0,
          transcript_error_type TEXT,
          transcript_last_error TEXT,
          transcript_retry_count INTEGER DEFAULT 0,
          transcript_failed_at DATETIME,
          source_platform TEXT,
          last_task_id TEXT,
          create_time DATETIME,
          update_time DATETIME
        )
        """
    )
    conn.execute(
        "INSERT INTO media_assets(asset_id, creator_uid, title, video_status, transcript_status, transcript_path, folder_path, is_read, is_starred) VALUES(?,?,?,?,?,?,?,?,?)",
        ("a1", "local:upload", "t", "downloaded", "pending", None, "chapter1", 0, 0),
    )
    conn.commit()
    monkeypatch.setattr("media_tools.api.routers.assets.get_db_connection", lambda: conn)
    monkeypatch.setattr("media_tools.repositories.asset_repository.get_db_connection", lambda: conn)

    rows = assets_router.list_assets(creator_uid="local:upload")
    assert rows[0]["folder_path"] == "chapter1"


def test_get_transcript_deletes_db_row_when_file_missing(tmp_path, monkeypatch) -> None:
    from media_tools.api.routers import assets as assets_router

    class _Cfg:
        def __init__(self, root: Path) -> None:
            self.project_root = root

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE media_assets (
          asset_id TEXT PRIMARY KEY,
          creator_uid TEXT,
          title TEXT,
          video_status TEXT,
          transcript_status TEXT,
          transcript_path TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO media_assets(asset_id, creator_uid, title, video_status, transcript_status, transcript_path) VALUES(?,?,?,?,?,?)",
        ("a1", "local:upload", "t", "downloaded", "completed", "本地上传/t.md"),
    )
    conn.commit()

    monkeypatch.setattr("media_tools.api.routers.assets.get_db_connection", lambda: conn)
    monkeypatch.setattr("media_tools.api.routers.assets.get_project_root", lambda: tmp_path)

    try:
        assets_router.get_transcript("a1")
        assert False
    except Exception as e:
        assert getattr(e, "status_code", None) == 404

    remaining = conn.execute("SELECT COUNT(*) FROM media_assets").fetchone()[0]
    assert remaining == 1
    status = conn.execute("SELECT transcript_status FROM media_assets WHERE asset_id='a1'").fetchone()[0]
    assert status == "completed"

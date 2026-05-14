from __future__ import annotations

import sqlite3
from contextlib import contextmanager


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE creators (
          uid TEXT PRIMARY KEY,
          nickname TEXT,
          sec_user_id TEXT,
          platform TEXT,
          sync_status TEXT,
          avatar TEXT,
          bio TEXT,
          homepage_url TEXT,
          last_fetch_time TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE media_assets (
          asset_id TEXT PRIMARY KEY,
          creator_uid TEXT,
          video_status TEXT,
          transcript_status TEXT,
          is_read BOOLEAN DEFAULT 0
        )
        """
    )
    conn.execute(
        "INSERT INTO creators(uid, nickname, sec_user_id, platform, sync_status, avatar, bio, homepage_url, last_fetch_time) VALUES(?,?,?,?,?,?,?,?,?)",
        ("c1", "alice", "s1", "douyin", "active", "", "", "", None),
    )
    conn.commit()
    return conn


def test_creators_disk_counts_strict_stem_matching(tmp_path, monkeypatch) -> None:
    from media_tools.api.routers import creators as creators_router

    conn = _make_conn()

    downloads = tmp_path / "downloads"
    transcripts_root = tmp_path / "transcripts"
    (downloads / "alice").mkdir(parents=True, exist_ok=True)
    (transcripts_root / "alice").mkdir(parents=True, exist_ok=True)

    (downloads / "alice" / "a.mp4").write_bytes(b"1")
    (downloads / "alice" / "b.mp4").write_bytes(b"2")
    (downloads / "alice" / "c_1.mp4").write_bytes(b"3")
    (transcripts_root / "alice" / "a.md").write_text("ok", encoding="utf-8")
    (transcripts_root / "alice" / "c.md").write_text("not-matching-c_1", encoding="utf-8")
    (transcripts_root / "alice" / "d.md").write_text("orphan", encoding="utf-8")

    @contextmanager
    def _get_conn():  # noqa: ANN001
        yield conn

    creators_router._disk_counts_cache.clear()
    monkeypatch.setattr("media_tools.api.routers.creators.get_db_connection", _get_conn)
    monkeypatch.setattr("media_tools.creators.repository.get_db_connection", _get_conn)
    monkeypatch.setattr("media_tools.api.routers.creators.get_download_path", lambda: downloads)
    monkeypatch.setattr("media_tools.api.routers.creators.get_project_root", lambda: tmp_path)

    rows = creators_router.list_creators()
    assert len(rows) == 1
    row = rows[0]

    assert row["disk_asset_count"] == 4
    assert row["disk_transcript_completed_count"] == 3
    assert row["disk_transcript_pending_count"] == 1
    assert "asset_count" in row
    assert "transcript_completed_count" in row
    assert "transcript_pending_count" in row


def test_creators_disk_counts_cache_ttl(tmp_path, monkeypatch) -> None:
    from media_tools.api.routers import creators as creators_router

    conn = _make_conn()

    downloads = tmp_path / "downloads"
    transcripts_root = tmp_path / "transcripts"
    (downloads / "alice").mkdir(parents=True, exist_ok=True)
    (transcripts_root / "alice").mkdir(parents=True, exist_ok=True)

    (downloads / "alice" / "a.mp4").write_bytes(b"1")
    (transcripts_root / "alice" / "a.md").write_text("ok", encoding="utf-8")

    @contextmanager
    def _get_conn():  # noqa: ANN001
        yield conn

    now = {"t": 0.0}

    def _mono() -> float:
        return float(now["t"])

    creators_router._disk_counts_cache.clear()
    monkeypatch.setattr("media_tools.api.routers.creators.get_db_connection", _get_conn)
    monkeypatch.setattr("media_tools.creators.repository.get_db_connection", _get_conn)
    monkeypatch.setattr("media_tools.api.routers.creators.get_download_path", lambda: downloads)
    monkeypatch.setattr("media_tools.api.routers.creators.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("media_tools.api.routers.creators.time.monotonic", _mono)

    first = creators_router.list_creators()[0]
    assert first["disk_asset_count"] == 1

    (downloads / "alice" / "b.mp4").write_bytes(b"2")

    now["t"] = 5.0
    second = creators_router.list_creators()[0]
    assert second["disk_asset_count"] == 1

    now["t"] = 11.0
    third = creators_router.list_creators()[0]
    assert third["disk_asset_count"] == 2

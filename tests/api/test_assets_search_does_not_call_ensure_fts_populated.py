from __future__ import annotations

import sqlite3
from unittest.mock import patch

from fastapi.testclient import TestClient

from media_tools.api.app import app


def test_assets_search_does_not_call_ensure_fts_populated() -> None:
    called = {"count": 0}

    def _fake_ensure() -> bool:
        called["count"] += 1
        return True

    conn = sqlite3.connect(":memory:", check_same_thread=False)
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
            folder_path TEXT,
            is_read BOOLEAN,
            is_starred BOOLEAN,
            create_time TEXT,
            update_time TEXT
        )
        """
    )
    conn.execute("CREATE VIRTUAL TABLE assets_fts USING fts5(asset_id UNINDEXED, title, transcript_text)")
    conn.execute(
        "INSERT INTO media_assets(asset_id, creator_uid, title, video_status, transcript_status, transcript_path, transcript_preview, folder_path, is_read, is_starred, create_time, update_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("a1", "c1", "hello", "ready", "ready", None, None, "", 0, 0, "t0", "t0"),
    )
    conn.execute(
        "INSERT INTO assets_fts(asset_id, title, transcript_text) VALUES (?, ?, ?)",
        ("a1", "hello", "hello world"),
    )
    conn.commit()

    with (
        patch("media_tools.store.db.ensure_fts_populated", side_effect=_fake_ensure),
        patch(
            "media_tools.api.routers.assets.get_db_connection",
            return_value=conn,
        ),
        TestClient(app) as client,
    ):
        resp = client.get("/api/v1/assets/search?q=hello")

    assert resp.status_code == 200
    assert called["count"] == 1

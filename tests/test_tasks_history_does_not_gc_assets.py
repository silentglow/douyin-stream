from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from media_tools.db.core import init_db
from media_tools.scheduler.repository import TaskRepository
from media_tools.scheduler.ops import cleanup_stale_tasks


def test_cleanup_stale_tasks_does_not_delete_media_assets() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        init_db(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        now = "2026-04-27T00:00:00"

        conn.execute(
            """
            INSERT OR REPLACE INTO media_assets
            (asset_id, creator_uid, source_url, title, video_path, video_status, transcript_path, transcript_status, create_time, update_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "asset-1",
                "creator-1",
                "https://example.invalid",
                "t",
                "v.mp4",
                "deleted",
                "",
                "none",
                now,
                now,
            ),
        )
        conn.execute(
            "INSERT OR REPLACE INTO assets_fts(asset_id, title, transcript_text) VALUES (?, ?, ?)",
            ("asset-1", "t", ""),
        )
        conn.commit()

        cleanup_stale_tasks(conn)
        conn.commit()
        TaskRepository.clear_all_history()

        remaining_assets = conn.execute(
            "SELECT COUNT(1) AS c FROM media_assets WHERE asset_id = ?",
            ("asset-1",),
        ).fetchone()["c"]
        remaining_fts = conn.execute(
            "SELECT COUNT(1) AS c FROM assets_fts WHERE asset_id = ?",
            ("asset-1",),
        ).fetchone()["c"]

        assert remaining_assets == 1
        assert remaining_fts == 1
    finally:
        try:
            conn.close()
        except Exception:
            pass
        db_path.unlink(missing_ok=True)


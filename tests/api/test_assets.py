import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from media_tools.api.app import app

client = TestClient(app)


def test_get_assets_by_creator():
    response = client.get("/api/v1/assets?creator_uid=123")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_bulk_delete_commits_db_before_file_delete():
    """新设计：先在事务里删除 DB 行（避免 partial failure 留下 DB-File 不一致），
    commit 后再尽力删除文件；文件删除失败仅记录日志，不影响 DB 提交。
    """
    from media_tools.api.routers import assets as assets_router
    from media_tools.store.db import init_db

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db_path = root / "test.db"
        init_db(db_path)

        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        downloads = root / "downloads"
        transcripts = root / "transcripts"
        downloads.mkdir(parents=True, exist_ok=True)
        transcripts.mkdir(parents=True, exist_ok=True)

        (downloads / "v.mp4").write_bytes(b"x")
        (transcripts / "t.txt").write_text("x", encoding="utf-8")

        conn.execute(
            """
            INSERT INTO media_assets
            (asset_id, creator_uid, source_url, title, video_path, video_status, transcript_path, transcript_status, create_time, update_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "a1",
                "c1",
                None,
                "t",
                "v.mp4",
                "ready",
                "t.txt",
                "ready",
                "2026-04-27T00:00:00",
                "2026-04-27T00:00:00",
            ),
        )
        conn.commit()

        events: dict[str, bool] = {"began": False, "committed": False}

        class _ConnProxy:
            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def execute(self, sql, params=()):
                if sql == "BEGIN IMMEDIATE":
                    events["began"] = True
                return self._inner.execute(sql, params)

            def commit(self):
                events["committed"] = True
                return self._inner.commit()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def _delete_asset_files(*_args, **_kwargs):
            # File delete must happen AFTER DB commit so partial failure can never leave DB-File mismatch
            assert events["began"] is True, "BEGIN IMMEDIATE should have run before file delete"
            assert events["committed"] is True, "DB commit must precede file delete"
            return []

        with (
            patch.object(assets_router, "get_db_connection", return_value=_ConnProxy(conn)),
            patch.object(assets_router, "get_download_path", return_value=downloads),
            patch.object(assets_router, "delete_asset_files", side_effect=_delete_asset_files),
        ):
            resp = client.post("/api/v1/assets/bulk_delete", json={"ids": ["a1"]})

        assert resp.status_code == 200
        assert events["began"] is True
        assert events["committed"] is True


def test_get_asset_transcript_missing_file_does_not_write_db() -> None:
    from media_tools.api.routers import assets as assets_router
    from media_tools.store.db import init_db

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db_path = root / "test.db"
        init_db(db_path)

        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        conn.execute(
            """
            INSERT INTO media_assets
            (asset_id, creator_uid, source_url, title, video_path, video_status, transcript_path, transcript_status, create_time, update_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "a1",
                "c1",
                None,
                "t",
                None,
                "ready",
                "missing.md",
                "ready",
                "2026-04-27T00:00:00",
                "2026-04-27T00:00:00",
            ),
        )
        conn.commit()

        with (
            patch.object(assets_router, "get_db_connection", return_value=conn),
        ):
            resp = client.get("/api/v1/assets/a1/transcript")

        assert resp.status_code == 404
        status = conn.execute(
            "SELECT transcript_status FROM media_assets WHERE asset_id = ?",
            ("a1",),
        ).fetchone()["transcript_status"]
        assert status == "ready"

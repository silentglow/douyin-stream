from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from media_tools.store.db import local_asset_id


def _build_db() -> sqlite3.Connection:
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
    conn.execute("CREATE TABLE assets_fts (asset_id TEXT PRIMARY KEY, title TEXT, transcript_text TEXT)")
    conn.commit()
    return conn


def _insert_local_asset(
    conn: sqlite3.Connection,
    *,
    video_path: Path,
    transcript_path: str | None,
    transcript_status: str = "completed",
) -> str:
    asset_id = local_asset_id(video_path)
    conn.execute(
        """
        INSERT INTO media_assets (asset_id, creator_uid, source_url, title, video_path,
            video_status, transcript_status, transcript_path, create_time, update_time)
        VALUES (?, 'local:upload', ?, ?, '', 'downloaded', ?, ?, '2026', '2026')
        """,
        (asset_id, str(video_path.resolve()), video_path.stem, transcript_status, transcript_path),
    )
    conn.commit()
    return asset_id


class _Pool:
    effective_concurrency = 1

    def resolve_accounts(self) -> None:
        return None


@pytest.mark.asyncio
async def test_delete_after_cleans_successful_file_on_progress_even_if_batch_later_errors(tmp_path: Path) -> None:
    from media_tools.transcribe.worker import run_local_transcribe

    output_dir = tmp_path / "transcripts"
    transcript_rel = "folder/clip.md"
    transcript_file = output_dir / transcript_rel
    transcript_file.parent.mkdir(parents=True)
    transcript_file.write_text("transcribed", encoding="utf-8")

    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"v" * 10240)

    conn = _build_db()
    asset_id = _insert_local_asset(conn, video_path=video_path, transcript_path=transcript_rel)

    class FakeOrchestrator:
        def __init__(self) -> None:
            self._account_pool_service = _Pool()
            self.on_progress = None

        async def transcribe_batch(self, paths, resume=False):  # noqa: ANN001, ARG002
            assert self.on_progress is not None
            self.on_progress(1, 1, Path(paths[0]), "成功")
            raise RuntimeError("batch failed after one success")

    fake = FakeOrchestrator()
    with (
        patch(
            "media_tools.core.config.load_pipeline_config",
            return_value=SimpleNamespace(output_dir=str(output_dir), concurrency=1),
        ),
        patch("media_tools.transcribe.service.create_orchestrator", return_value=fake),
        patch("media_tools.transcribe.worker.get_db_connection", return_value=conn),
        patch("media_tools.assets.service.get_db_connection", return_value=conn),
    ):
        with pytest.raises(RuntimeError, match="batch failed"):
            await run_local_transcribe([str(video_path)], update_progress_fn=None, delete_after=True)

    row = conn.execute("SELECT video_status FROM media_assets WHERE asset_id = ?", (asset_id,)).fetchone()
    assert row["video_status"] == "archived"
    assert not video_path.exists()


@pytest.mark.asyncio
async def test_delete_after_resolves_relative_transcript_path_from_report(tmp_path: Path) -> None:
    from media_tools.transcribe.worker import run_local_transcribe

    output_dir = tmp_path / "transcripts"
    transcript_rel = "folder/clip.md"
    transcript_file = output_dir / transcript_rel
    transcript_file.parent.mkdir(parents=True)
    transcript_file.write_text("transcribed body", encoding="utf-8")

    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"v" * 10240)

    conn = _build_db()
    asset_id = _insert_local_asset(conn, video_path=video_path, transcript_path=None, transcript_status="pending")

    class FakeOrchestrator:
        def __init__(self) -> None:
            self._account_pool_service = _Pool()
            self.on_progress = None

        async def transcribe_batch(self, paths, resume=False):  # noqa: ANN001, ARG002
            return SimpleNamespace(
                results=[
                    {
                        "video_path": str(paths[0]),
                        "success": True,
                        "transcript_path": transcript_rel,
                        "error": None,
                        "error_type": "unknown",
                        "attempts": 1,
                    }
                ],
                success=1,
                failed=0,
            )

    with (
        patch(
            "media_tools.core.config.load_pipeline_config",
            return_value=SimpleNamespace(output_dir=str(output_dir), concurrency=1),
        ),
        patch("media_tools.transcribe.service.create_orchestrator", return_value=FakeOrchestrator()),
        patch("media_tools.transcribe.worker.get_db_connection", return_value=conn),
        patch("media_tools.assets.service.get_db_connection", return_value=conn),
    ):
        result = await run_local_transcribe([str(video_path)], update_progress_fn=None, delete_after=True)

    row = conn.execute(
        "SELECT video_status, transcript_preview FROM media_assets WHERE asset_id = ?",
        (asset_id,),
    ).fetchone()
    assert result["success_count"] == 1
    assert row["video_status"] == "archived"
    assert row["transcript_preview"] == "transcribed body"
    assert not video_path.exists()


@pytest.mark.asyncio
async def test_delete_after_removes_original_split_source_when_all_parts_succeed(tmp_path: Path) -> None:
    from media_tools.transcribe.worker import run_local_transcribe

    output_dir = tmp_path / "transcripts"
    video_path = tmp_path / "large.mp4"
    video_path.write_bytes(b"v" * 10240)

    part_dir = tmp_path / "split"
    part_dir.mkdir()
    part1 = part_dir / "large__part1of2.mp4"
    part2 = part_dir / "large__part2of2.mp4"
    part1.write_bytes(b"p" * 10240)
    part2.write_bytes(b"p" * 10240)

    transcript1 = "parts/large__part1of2.md"
    transcript2 = "parts/large__part2of2.md"
    (output_dir / "parts").mkdir(parents=True)
    (output_dir / transcript1).write_text("part one", encoding="utf-8")
    (output_dir / transcript2).write_text("part two", encoding="utf-8")

    conn = _build_db()
    asset_id = _insert_local_asset(conn, video_path=video_path, transcript_path=None, transcript_status="pending")

    async def fake_prepare(paths, update_progress_fn):  # noqa: ANN001, ARG001
        return [part1, part2], {Path(paths[0]): [part1, part2]}

    class FakeOrchestrator:
        def __init__(self) -> None:
            self._account_pool_service = _Pool()
            self.on_progress = None

        async def transcribe_batch(self, paths, resume=False):  # noqa: ANN001, ARG002
            return SimpleNamespace(
                results=[
                    {
                        "video_path": str(part1),
                        "success": True,
                        "transcript_path": transcript1,
                        "error": None,
                        "error_type": "unknown",
                    },
                    {
                        "video_path": str(part2),
                        "success": True,
                        "transcript_path": transcript2,
                        "error": None,
                        "error_type": "unknown",
                    },
                ],
                success=2,
                failed=0,
            )

    with (
        patch(
            "media_tools.core.config.load_pipeline_config",
            return_value=SimpleNamespace(output_dir=str(output_dir), concurrency=1),
        ),
        patch("media_tools.transcribe.service.create_orchestrator", return_value=FakeOrchestrator()),
        patch("media_tools.transcribe.worker._prepare_split_paths", new=fake_prepare),
        patch("media_tools.transcribe.worker.get_db_connection", return_value=conn),
        patch("media_tools.assets.service.get_db_connection", return_value=conn),
    ):
        result = await run_local_transcribe([str(video_path)], update_progress_fn=None, delete_after=True)

    row = conn.execute("SELECT video_status FROM media_assets WHERE asset_id = ?", (asset_id,)).fetchone()
    assert result["success_count"] == 2
    assert row["video_status"] == "archived"
    assert not video_path.exists()

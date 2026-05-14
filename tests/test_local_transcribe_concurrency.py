from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
import asyncio


@dataclass(frozen=True)
class _Result:
    success: bool
    transcript_path: Optional[str] = None


class _FakeOrchestrator:
    def __init__(self) -> None:
        self.transcribe_batch_calls: list[list[Path]] = []
        self.transcribe_with_retry_calls: list[Path] = []

    async def transcribe_batch(self, video_paths: list[Path], resume: bool = True) -> Any:
        self.transcribe_batch_calls.append(video_paths)
        return type(
            "BatchReport",
            (),
            {
                "total": len(video_paths),
                "success": len(video_paths),
                "failed": 0,
                "skipped": 0,
                "results": [
                    {"video_path": str(p), "success": True, "transcript_path": None} for p in video_paths
                ],
            },
        )()

    async def transcribe_with_retry(self, video_path: Path) -> _Result:
        self.transcribe_with_retry_calls.append(video_path)
        return _Result(success=True)


def test_pipeline_config_default_concurrency_is_10(monkeypatch, tmp_path) -> None:
    import sqlite3
    from contextlib import contextmanager

    from media_tools.pipeline.config import load_pipeline_config
    from media_tools.core.config import _invalidate_settings_cache

    _invalidate_settings_cache()

    db_path = tmp_path / "settings.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE SystemSettings (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()

    @contextmanager
    def _get_conn():  # noqa: ANN001
        yield conn

    monkeypatch.setattr("media_tools.core.config.get_db_connection", _get_conn)
    monkeypatch.delenv("PIPELINE_CONCURRENCY", raising=False)

    config = load_pipeline_config()
    assert config.concurrency == 10
    conn.close()


def test_pipeline_config_concurrency_uses_system_settings(monkeypatch, tmp_path) -> None:
    import sqlite3
    from contextlib import contextmanager

    from media_tools.pipeline.config import load_pipeline_config
    from media_tools.core.config import _invalidate_settings_cache

    _invalidate_settings_cache()

    db_path = tmp_path / "settings.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE SystemSettings (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO SystemSettings (key, value) VALUES ('concurrency', '3')")
    conn.commit()

    @contextmanager
    def _get_conn():  # noqa: ANN001
        yield conn

    monkeypatch.setattr("media_tools.core.config.get_db_connection", _get_conn)
    monkeypatch.delenv("PIPELINE_CONCURRENCY", raising=False)

    config = load_pipeline_config()
    assert config.concurrency == 3
    conn.close()


def test_pipeline_config_concurrency_env_overrides_system_settings(monkeypatch, tmp_path) -> None:
    import sqlite3
    from contextlib import contextmanager

    from media_tools.pipeline.config import load_pipeline_config
    from media_tools.core.config import _invalidate_settings_cache

    _invalidate_settings_cache()

    db_path = tmp_path / "settings.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE SystemSettings (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO SystemSettings (key, value) VALUES ('concurrency', '3')")
    conn.commit()

    @contextmanager
    def _get_conn():  # noqa: ANN001
        yield conn

    monkeypatch.setattr("media_tools.core.config.get_db_connection", _get_conn)
    monkeypatch.setenv("PIPELINE_CONCURRENCY", "7")

    config = load_pipeline_config()
    assert config.concurrency == 7
    conn.close()


def test_local_transcribe_uses_batch_transcribe(monkeypatch) -> None:
    from media_tools.pipeline.worker import run_local_transcribe

    fake = _FakeOrchestrator()

    def _fake_create_orchestrator(*args, **kwargs):  # noqa: ANN001
        return fake

    monkeypatch.setattr("media_tools.pipeline.orchestrator.create_orchestrator", _fake_create_orchestrator)

    mp3_path = Path("/tmp/local_concurrency_test.mp3")
    mp3_path.write_bytes(b"ok" * 6000)  # 12KB, above MIN_VIDEO_BYTES

    result = asyncio.run(run_local_transcribe([str(mp3_path)], update_progress_fn=None, delete_after=False))
    assert result["total"] == 1
    assert len(fake.transcribe_batch_calls) == 1
    assert fake.transcribe_with_retry_calls == []

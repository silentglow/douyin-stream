from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_run_local_transcribe_subtasks_include_error_type(tmp_path: Path) -> None:
    from media_tools.transcribe.errors import ErrorType
    from media_tools.transcribe.models import PipelineResultV2
    from media_tools.transcribe.worker import run_local_transcribe

    video_path = tmp_path / "a.mp4"
    video_path.write_bytes(b"\x00" * 11000)

    class FakeOrchestrator:
        async def transcribe_batch(self, video_paths: list[Path], resume: bool = True):
            from media_tools.transcribe.models import BatchReport
            results = []
            for p in video_paths:
                results.append({
                    "video_path": str(p),
                    "success": False,
                    "error": "request timed out",
                    "error_type": ErrorType.TIMEOUT.value,
                    "attempts": 2,
                    "transcript_path": None,
                })
            return BatchReport(
                total=len(video_paths),
                success=0,
                failed=len(video_paths),
                results=results,
            )

    async def noop_progress(*_args, **_kwargs):
        return None

    with patch("media_tools.transcribe.service.create_orchestrator", return_value=FakeOrchestrator()), patch(
        "media_tools.core.config.load_pipeline_config",
        return_value=SimpleNamespace(output_dir=str(tmp_path), concurrency=1),
    ):
        result = await run_local_transcribe([str(video_path)], update_progress_fn=noop_progress, delete_after=False)

    subtasks = result.get("subtasks") or []
    assert len(subtasks) == 1
    assert subtasks[0]["status"] == "failed"
    assert "timeout" in str(subtasks[0].get("error", "")).lower()
    assert "attempts=2" in str(subtasks[0].get("error", ""))
    assert subtasks[0].get("video_path") == str(video_path)

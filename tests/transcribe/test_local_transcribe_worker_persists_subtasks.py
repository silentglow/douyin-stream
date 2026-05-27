import asyncio
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_local_transcribe_worker_passes_subtasks_to_complete_task() -> None:
    from media_tools.api.schemas import LocalTranscribeRequest
    from media_tools.workers.local_transcribe_worker import LocalTranscribeWorker

    run_local_transcribe = AsyncMock(
        return_value={
            "success_count": 1,
            "failed_count": 1,
            "total": 2,
            "subtasks": [
                {"title": "ok", "status": "completed"},
                {"title": "bad", "status": "failed", "error": "timeout: request"},
            ],
        }
    )
    update_task_progress = AsyncMock()
    complete_task = AsyncMock()

    with (
        patch(
            "media_tools.workers.local_transcribe_worker.run_local_transcribe",
            new=run_local_transcribe,
        ),
        patch(
            "media_tools.scheduler.base.update_task_progress",
            new=update_task_progress,
        ),
        patch(
            "media_tools.scheduler.base._complete_task",
            new=complete_task,
        ),
        patch(
            "media_tools.scheduler.base._task_heartbeat",
            new=lambda _task_id: asyncio.sleep(3600),
        ),
    ):
        req = LocalTranscribeRequest(file_paths=["/tmp/a.mp4", "/tmp/b.mp4"], delete_after=False)
        await LocalTranscribeWorker().execute("t1", req=req)

    assert complete_task.await_count == 1
    assert complete_task.await_args.kwargs.get("result_summary") == {"success": 1, "failed": 1, "total": 2}
    subtasks = complete_task.await_args.kwargs.get("subtasks")
    assert isinstance(subtasks, list)
    assert any(s.get("status") == "failed" and "timeout" in str(s.get("error", "")) for s in subtasks)

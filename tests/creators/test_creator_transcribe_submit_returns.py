from __future__ import annotations

import asyncio


def test_creator_transcribe_submits_background_task(monkeypatch) -> None:
    from media_tools.api.routers import tasks as tasks_router

    created: dict[str, object] = {}

    async def _fake_create_task(task_id: str, task_type: str, request_params: dict):  # noqa: ANN001
        created["task_id"] = task_id
        created["task_type"] = task_type
        created["payload"] = request_params

    def _fake_register(task_id: str, coro):  # noqa: ANN001
        created["registered_task_id"] = task_id
        created["registered_coro"] = coro
        # 关闭未调度的协程，消除 RuntimeWarning
        if hasattr(coro, "close"):
            coro.close()

    monkeypatch.setattr("media_tools.scheduler.dispatcher._create_task", _fake_create_task)
    monkeypatch.setattr("media_tools.scheduler.dispatcher._register_background_task", _fake_register)

    req = tasks_router.CreatorTranscribeRequest(uid="u1")
    result = asyncio.run(tasks_router.trigger_creator_transcribe(req))

    assert result["status"] == "started"
    assert "task_id" in result
    assert "file_count" in result
    assert created["task_type"] == "creator_transcribe"
    assert created["registered_task_id"] == result["task_id"]
    assert created["registered_coro"] is not None

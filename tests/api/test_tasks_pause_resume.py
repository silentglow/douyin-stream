from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from media_tools.api.app import app


def test_pause_running_task_marks_it_paused(monkeypatch) -> None:
    from media_tools.api.routers import tasks as tasks_router

    pause_marker = AsyncMock(return_value=True)
    monkeypatch.setattr(tasks_router.TaskRepository, "get_status", staticmethod(lambda _task_id: ("RUNNING", "pipeline")))
    monkeypatch.setattr(tasks_router, "_mark_task_paused", pause_marker)
    monkeypatch.setattr(tasks_router, "_active_tasks", {})

    response = TestClient(app).post("/api/v1/tasks/task-1/pause")

    assert response.status_code == 200
    assert response.json()["message"] == "任务已暂停"
    pause_marker.assert_awaited_once_with("task-1", "pipeline")


def test_resume_paused_task_dispatches_saved_request(monkeypatch) -> None:
    from media_tools.api.routers import tasks as tasks_router

    resume_worker = AsyncMock(return_value={"task_id": "task-1", "status": "started", "message": "Task resumed"})
    monkeypatch.setattr(
        tasks_router.TaskRepository,
        "get_task_type_payload_status",
        staticmethod(lambda _task_id: ("pipeline", '{"url":"https://example.com","msg":"任务已暂停"}', "PAUSED")),
    )
    monkeypatch.setattr(tasks_router, "resume_paused_task", resume_worker)
    monkeypatch.setattr(tasks_router, "_active_tasks", {})

    response = TestClient(app).post("/api/v1/tasks/task-1/resume")

    assert response.status_code == 200
    resume_worker.assert_awaited_once_with("task-1", "pipeline", {"url": "https://example.com"})


def test_cancel_paused_task_is_allowed(monkeypatch) -> None:
    from media_tools.api.routers import tasks as tasks_router
    from media_tools.douyin.core.cancel_registry import clear_cancel_event

    cancel_marker = AsyncMock()
    monkeypatch.setattr(tasks_router.TaskRepository, "get_status", staticmethod(lambda _task_id: ("PAUSED", "pipeline")))
    monkeypatch.setattr(tasks_router, "_mark_task_cancelled", cancel_marker)
    monkeypatch.setattr(tasks_router, "_active_tasks", {})
    try:
        response = TestClient(app).post("/api/v1/tasks/task-1/cancel")
    finally:
        clear_cancel_event("task-1")

    assert response.status_code == 200
    cancel_marker.assert_awaited_once_with("task-1", "pipeline")

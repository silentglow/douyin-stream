from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from media_tools.api.app import app


def _skip_background_task(_task_id, coro):
    try:
        coro.close()
    except Exception:
        pass
    return None


def test_trigger_recover_aweme_creates_new_task() -> None:
    client = TestClient(app)
    with patch("media_tools.workers.task_dispatcher._register_background_task", side_effect=_skip_background_task) as reg, patch(
        "media_tools.workers.task_dispatcher._create_task",
        new=AsyncMock(),
    ):
        resp = client.post(
            "/api/v1/tasks/recover/aweme",
            json={"creator_uid": "douyin:1", "aweme_id": "123", "title": "t"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert data["status"] == "started"
    assert reg.called


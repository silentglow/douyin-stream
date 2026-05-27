import contextlib
from unittest.mock import patch

from fastapi.testclient import TestClient

from media_tools.api.app import app

client = TestClient(app)


def _skip_background_task(_task_id, coro):
    with contextlib.suppress(Exception):
        coro.close()
    return None


def test_get_active_tasks():
    response = client.get("/api/v1/tasks/active")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_trigger_pipeline():
    with patch("media_tools.scheduler.dispatcher._register_background_task", side_effect=_skip_background_task):
        response = client.post("/api/v1/tasks/pipeline", json={"url": "https://douyin.com/user/123", "max_counts": 2})
    assert response.status_code == 200
    assert "task_id" in response.json()


def test_batch_pipeline():
    payload = {
        "video_urls": ["https://www.douyin.com/video/123", "https://www.douyin.com/video/456"],
        "auto_delete": True,
    }
    with patch("media_tools.scheduler.dispatcher._register_background_task", side_effect=_skip_background_task):
        response = client.post("/api/v1/tasks/pipeline/batch", json=payload)
    assert response.status_code == 200
    assert "task_id" in response.json()

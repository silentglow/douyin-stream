from fastapi.testclient import TestClient

from media_tools.api.app import app

client = TestClient(app)


def test_metrics_endpoint_returns_expected_shape() -> None:
    resp = client.get("/api/v1/metrics")
    assert resp.status_code == 200
    body = resp.json()

    assert "uptime_seconds" in body
    assert isinstance(body["uptime_seconds"], int)
    assert body["uptime_seconds"] >= 0

    tasks = body["tasks"]
    for key in ("PENDING", "RUNNING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED", "active", "total"):
        assert key in tasks, f"missing task metric: {key}"
        assert isinstance(tasks[key], int)

    ws = body["websocket"]
    assert "active_connections" in ws
    assert "broadcast_success" in ws
    assert "broadcast_failed" in ws

    bg = body["background_tasks"]
    assert "active" in bg and "total" in bg

    db = body["db_connections"]
    assert "open_connections" in db


def test_health_returns_200() -> None:
    """验证 /api/health 正常响应（覆盖中间件不干扰正常路由）。"""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("ok", "degraded")

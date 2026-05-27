from fastapi.testclient import TestClient

from media_tools.api.app import app

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"
    assert "disk" in data
    assert "active_tasks" in data

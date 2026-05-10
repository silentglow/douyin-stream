import pytest
from fastapi.testclient import TestClient
from media_tools.api.app import app

client = TestClient(app)

def test_get_settings():
    response = client.get("/api/v1/settings")
    assert response.status_code == 200
    assert "qwen_configured" in response.json()
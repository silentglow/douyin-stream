import pytest
from fastapi.testclient import TestClient
from media_tools.api.app import app

client = TestClient(app)

def test_get_creators():
    # Since we don't have a mock DB setup here easily without DI, 
    # we just test the endpoint exists and returns a list.
    response = client.get("/api/v1/creators")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
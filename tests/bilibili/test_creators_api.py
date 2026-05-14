from fastapi.testclient import TestClient

from media_tools.api.app import app


client = TestClient(app)


def test_add_bilibili_creator_space_url() -> None:
    response = client.post(
        "/api/v1/creators",
        json={"url": "https://space.bilibili.com/596133959?spm_id_from=333.1007.tianma.1-1-1.click"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"created", "exists"}
    assert payload["creator"]["uid"].startswith("bilibili:")


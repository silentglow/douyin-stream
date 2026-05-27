from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from media_tools.api.app import app


def test_add_and_delete_bilibili_account() -> None:
    client = TestClient(app)
    account_id = "test-account-id"

    with (
        patch("media_tools.api.routers.settings.AccountRepository.create"),
        patch("media_tools.api.routers.settings.AccountRepository.delete", return_value=1),
        patch(
            "media_tools.api.routers.settings.AccountRepository.list_by_platform",
            return_value=[{"id": account_id, "platform": "bilibili", "remark": "test", "status": "active"}],
        ),
    ):
        add_resp = client.post(
            "/api/v1/settings/bilibili/accounts",
            json={"cookie_string": "SESSDATA=abcdefghijklmnopqrstuvwxyz1234567890", "remark": "test"},
        )
        assert add_resp.status_code == 200
        account_id = add_resp.json()["account_id"]

        del_resp = client.delete(f"/api/v1/settings/bilibili/accounts/{account_id}")
        assert del_resp.status_code == 200


def test_delete_bilibili_account_404_when_missing() -> None:
    client = TestClient(app)
    with patch("media_tools.api.routers.settings.AccountRepository.delete", return_value=0):
        resp = client.delete("/api/v1/settings/bilibili/accounts/does-not-exist")
        assert resp.status_code == 404

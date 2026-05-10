from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from media_tools.api.app import app


client = TestClient(app)


def test_update_global_settings_supports_patch_semantics() -> None:
    calls: list[tuple[str, object]] = []

    def _set(key: str, value: object) -> None:
        calls.append((key, value))

    with patch("media_tools.api.routers.settings.set_runtime_setting", side_effect=_set):
        resp = client.post("/api/v1/settings/global", json={"auto_transcribe": True})

    assert resp.status_code == 200
    assert calls == [("auto_transcribe", True)]


def test_update_global_settings_rejects_empty_patch() -> None:
    resp = client.post("/api/v1/settings/global", json={})
    assert resp.status_code == 400


def test_update_global_settings_rejects_concurrency_below_1() -> None:
    with patch("media_tools.api.routers.settings.set_runtime_setting"):
        resp = client.post("/api/v1/settings/global", json={"concurrency": 0})
    assert resp.status_code == 400
    assert "1-100" in resp.json()["message"]


def test_update_global_settings_rejects_concurrency_above_100() -> None:
    with patch("media_tools.api.routers.settings.set_runtime_setting"):
        resp = client.post("/api/v1/settings/global", json={"concurrency": 101})
    assert resp.status_code == 400
    assert "1-100" in resp.json()["message"]


def test_update_global_settings_accepts_concurrency_in_range() -> None:
    calls: list[tuple[str, object]] = []

    def _set(key: str, value: object) -> None:
        calls.append((key, value))

    with patch("media_tools.api.routers.settings.set_runtime_setting", side_effect=_set):
        resp = client.post("/api/v1/settings/global", json={"concurrency": 20})
    assert resp.status_code == 200
    assert ("concurrency", 20) in calls


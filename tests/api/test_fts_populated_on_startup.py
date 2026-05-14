from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from media_tools.api.app import app


def test_ensure_fts_populated_runs_on_startup() -> None:
    called = {"value": False}

    def _fake() -> bool:
        called["value"] = True
        return True

    with patch("media_tools.store.db.ensure_fts_populated", side_effect=_fake):
        with TestClient(app):
            pass

    assert called["value"] is True


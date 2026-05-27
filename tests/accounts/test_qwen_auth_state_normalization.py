from __future__ import annotations

import json


def test_normalize_qwen_storage_state_fills_domain_and_path() -> None:
    from media_tools.transcribe.auth_state import QWEN_COOKIE_DOMAIN, normalize_qwen_storage_state

    state = {
        "cookies": [
            {"name": "a", "value": "b", "domain": None},
            {"name": "c", "value": "d", "path": ""},
        ],
        "origins": None,
    }

    normalized = normalize_qwen_storage_state(state)
    assert normalized is not None

    cookies = {item["name"]: item for item in normalized["cookies"]}
    assert cookies["a"]["domain"] == QWEN_COOKIE_DOMAIN
    assert cookies["a"]["path"] == "/"
    assert cookies["c"]["domain"] == QWEN_COOKIE_DOMAIN
    assert cookies["c"]["path"] == "/"
    assert normalized["origins"] == []


def test_read_qwen_storage_state_file_normalizes(tmp_path) -> None:
    from media_tools.transcribe.auth_state import QWEN_COOKIE_DOMAIN, read_qwen_storage_state_file

    p = tmp_path / "storage.json"
    p.write_text(json.dumps({"cookies": [{"name": "x", "value": "y"}]}), encoding="utf-8")

    loaded = read_qwen_storage_state_file(p)
    assert loaded is not None
    assert loaded["cookies"][0]["domain"] == QWEN_COOKIE_DOMAIN
    assert loaded["cookies"][0]["path"] == "/"


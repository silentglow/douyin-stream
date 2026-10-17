from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from media_tools.douyin.core import cookie_check
from media_tools.douyin.core.cookie_check import (
    STATUS_BLOCKED,
    STATUS_ERROR,
    STATUS_EXPIRED,
    STATUS_MISSING,
    STATUS_VALID,
    check_douyin_cookie,
    inspect_cookie_structure,
    parse_cookie_keys,
)

VALID_COOKIE = "sessionid=abc; UIFID=def; ttwid=ghi; msToken=jkl; passport_csrf_token=mno"


def test_parse_cookie_keys_is_case_insensitive() -> None:
    keys = parse_cookie_keys("UIFID=1; msToken=2; sessionid=3")
    assert keys["uifid"] == "1"
    assert keys["mstoken"] == "2"
    assert keys["sessionid"] == "3"


def test_inspect_cookie_structure_reports_missing_keys() -> None:
    assert inspect_cookie_structure(VALID_COOKIE) == []
    missing = inspect_cookie_structure("sessionid=abc; UIFID=def; ttwid=ghi")
    assert "msToken" in missing
    assert "passport_csrf_token" in missing
    assert "sessionid" not in missing


def test_inspect_cookie_structure_flags_login_and_device_keys() -> None:
    missing = inspect_cookie_structure("foo=bar; msToken=x")
    assert "sessionid" in missing
    assert "UIFID" in missing


def test_interpret_response_valid_login() -> None:
    result = cookie_check._interpret_response(200, '{"status_code": 0, "user": {"nickname": "小明"}}')
    assert result.valid is True
    assert result.status == STATUS_VALID
    assert result.nickname == "小明"


def test_interpret_response_not_logged_in() -> None:
    result = cookie_check._interpret_response(200, '{"status_code": 8, "status_msg": "用户未登录", "user": null}')
    assert result.valid is False
    assert result.status == STATUS_EXPIRED


def test_interpret_response_argus_block() -> None:
    result = cookie_check._interpret_response(403, "Blocked by ArgusSecurityPlugin Uifid Not Found")
    assert result.valid is False
    assert result.status == STATUS_BLOCKED
    assert result.http_status == 403


def test_interpret_response_non_json() -> None:
    result = cookie_check._interpret_response(200, "<html>oops</html>")
    assert result.valid is False
    assert result.status == STATUS_ERROR


@pytest.mark.asyncio
async def test_check_empty_cookie_is_missing() -> None:
    result = await check_douyin_cookie("")
    assert result.valid is False
    assert result.status == STATUS_MISSING


@pytest.mark.asyncio
async def test_check_without_login_state_skips_network() -> None:
    with patch.object(cookie_check, "_probe_login_state", new_callable=AsyncMock) as probe:
        result = await check_douyin_cookie("foo=bar")
    probe.assert_not_called()
    assert result.status == STATUS_EXPIRED


@pytest.mark.asyncio
async def test_check_valid_cookie_probes_network() -> None:
    with patch.object(cookie_check, "_probe_login_state", new_callable=AsyncMock) as probe:
        probe.return_value = (200, '{"status_code": 0, "user": {"nickname": "测试"}}')
        result = await check_douyin_cookie(VALID_COOKIE)
    probe.assert_awaited_once()
    assert result.valid is True
    assert result.status == STATUS_VALID
    assert result.missing_keys == []


@pytest.mark.asyncio
async def test_probe_login_state_uses_required_params_and_checked_cookie(monkeypatch) -> None:
    checked_cookie = "sessionid=new; UIFID=new-uifid"
    captured: dict = {}

    class FakeBogusManager:
        @staticmethod
        def model_2_endpoint(user_agent: str, endpoint: str, params: dict) -> str:
            captured["endpoint"] = endpoint
            captured["params"] = params
            return endpoint

    class FakeClient:
        async def get(self, endpoint: str):
            captured["requested_endpoint"] = endpoint
            return type("Response", (), {"status_code": 200, "text": "{}"})()

    class FakeCrawler:
        def __init__(self, kwargs: dict) -> None:
            captured["kwargs"] = kwargs
            self.headers = kwargs["headers"]
            self.bogus_manager = FakeBogusManager
            self.aclient = FakeClient()

        async def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(
        "f2.apps.douyin.crawler.DouyinCrawler",
        lambda kwargs: FakeCrawler(kwargs),
    )
    monkeypatch.setattr(
        "media_tools.douyin.core.f2_helper.get_f2_kwargs",
        lambda: {
            "timeout": 10,
            "cookie": "sessionid=old; UIFID=old-uifid",
            "headers": {"User-Agent": "ua", "uifid": "old-uifid", "x-tt-argus": "1"},
        },
    )

    status, body = await cookie_check._probe_login_state(checked_cookie, 10)

    assert (status, body) == (200, "{}")
    assert captured["params"] == {"aid": "6383", "cookie_enabled": "true"}
    assert captured["kwargs"]["headers"]["uifid"] == "new-uifid"
    assert captured["closed"] is True


@pytest.mark.asyncio
async def test_check_surfaces_network_errors() -> None:
    with patch.object(cookie_check, "_probe_login_state", new_callable=AsyncMock) as probe:
        probe.side_effect = RuntimeError("boom")
        result = await check_douyin_cookie(VALID_COOKIE)
    assert result.valid is False
    assert result.status == STATUS_ERROR
    assert "boom" in result.message

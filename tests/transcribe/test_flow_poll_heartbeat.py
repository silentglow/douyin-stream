"""poll_until_done 轮询心跳节流单测。

验证：轮询循环每圈都跑，但 on_progress「已等待多久」心跳被节流上报，
不会每圈都推（否则会造成 DB 写入 / WebSocket 广播风暴）。
"""

import asyncio
from unittest.mock import patch

import pytest

from media_tools.transcribe import flow
from media_tools.transcribe.errors import TranscribeError


def test_poll_until_done_heartbeat_is_throttled():
    call_count = {"n": 0}

    async def fake_api_json(_context, _url, _payload):
        # 前 5 圈返回「处理中」(status=10)，第 6 圈返回「完成」(status=30) 让循环退出
        call_count["n"] += 1
        status = 30 if call_count["n"] >= 6 else 10
        return {"data": {"batchRecord": [{"recordList": [{"genRecordId": "g1", "recordStatus": status}]}]}}

    # 模拟单调时钟：每次调用 +20s。loop_start=0，之后每圈 elapsed=20,40,60,80,100…
    clock = {"t": -20.0}

    def fake_monotonic():
        clock["t"] += 20.0
        return clock["t"]

    async def noop_sleep(*_a, **_k):
        return None

    reports: list[str] = []

    with (
        patch.object(flow, "api_json", fake_api_json),
        patch.object(flow.time, "monotonic", fake_monotonic),
        patch.object(flow.asyncio, "sleep", noop_sleep),
    ):
        record = asyncio.run(flow.poll_until_done("ctx", "g1", timeout_seconds=10_000, on_progress=reports.append))

    assert record["recordStatus"] == 30
    # 5 圈「处理中」跨 0→100s，节流间隔 45s，只应在 ~60s 触发 1 次心跳
    assert len(reports) == 1, f"心跳未被节流，实际上报 {len(reports)} 次: {reports}"
    assert "云端转写中" in reports[0]
    assert "已等待 1 分钟" in reports[0]


def test_poll_until_done_no_callback_is_safe():
    """不传 on_progress 时不应报错（向后兼容）。"""
    call_count = {"n": 0}

    async def fake_api_json(_context, _url, _payload):
        call_count["n"] += 1
        status = 30 if call_count["n"] >= 2 else 10
        return {"data": {"batchRecord": [{"recordList": [{"genRecordId": "g1", "recordStatus": status}]}]}}

    async def noop_sleep(*_a, **_k):
        return None

    with (
        patch.object(flow, "api_json", fake_api_json),
        patch.object(flow.asyncio, "sleep", noop_sleep),
    ):
        record = asyncio.run(flow.poll_until_done("ctx", "g1", timeout_seconds=10_000))

    assert record["recordStatus"] == 30


def test_poll_until_done_missing_record_can_fail_fast():
    async def fake_api_json(_context, _url, _payload):
        return {"data": {"batchRecord": [{"recordList": [{"genRecordId": "other", "recordStatus": 10}]}]}}

    async def noop_sleep(*_a, **_k):
        raise AssertionError("missing record should fail before sleeping")

    with (
        patch.object(flow, "api_json", fake_api_json),
        patch.object(flow.asyncio, "sleep", noop_sleep),
        pytest.raises(TranscribeError, match="gen_record_id=g1"),
    ):
        asyncio.run(flow.poll_until_done("ctx", "g1", timeout_seconds=10_000, missing_timeout_seconds=0))

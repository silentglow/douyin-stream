"""oss2.resumable_upload 集成回归测试 (v2026-05-26)。

历史 bug:手写 multipart 上传 + 单 part 30s 写超时 → 任一 part 抖动整次上传 fail。
修复:换 oss2.resumable_upload,内置 part 级重试 + checkpoint 断点续传。

本测试用 mock 锁定:
1. upload_file_to_oss multipart 模式调用 oss2.resumable_upload
2. 进度事件保持 part-uploaded / multipart-started / multipart-complete 三段式
3. direct 模式 (小文件) 走 presigned URL,不碰 oss2
4. part_size 决策逻辑未变(<1G→5MB / <5G→16MB / ≥5G→32MB)
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from media_tools.transcribe import oss_upload
from media_tools.transcribe.oss_upload import (
    _resolve_part_size,
    upload_file_to_oss,
)


def _make_token() -> dict:
    return {
        "getLink": "https://presigned/",
        "sts": {
            "bucket": "qwen-bucket",
            "endpoint": "oss-cn-shanghai-cnyz.oss-data-acc.aliyuncs.com",
            "fileKey": "user/abc/some-file-12345.mp4",
            "accessKeyId": "STS-AK",
            "accessKeySecret": "STS-SK",
            "securityToken": "STS-TOKEN",
        },
    }


@pytest.fixture
def big_file(tmp_path: Path) -> Path:
    """造 6 MB 假文件,够触发 multipart(默认 part_size 5 MB → 2 parts)。"""
    fp = tmp_path / "big.mp4"
    fp.write_bytes(b"x" * (6 * 1024 * 1024))
    return fp


def test_resolve_part_size_unchanged() -> None:
    """切片大小决策没动:不受 oss2 切换影响。"""
    assert _resolve_part_size(500 * 1024 * 1024, 0) == 5 * 1024 * 1024  # 500MB → 5MB
    assert _resolve_part_size(3 * 1024 * 1024 * 1024, 0) == 16 * 1024 * 1024  # 3GB → 16MB
    assert _resolve_part_size(8 * 1024 * 1024 * 1024, 0) == 32 * 1024 * 1024  # 8GB → 32MB
    assert _resolve_part_size(500 * 1024 * 1024, 8) == 8 * 1024 * 1024  # override 优先


@pytest.mark.asyncio
async def test_multipart_mode_uses_oss2_resumable_upload(big_file: Path) -> None:
    """multipart 模式必须走 oss2.resumable_upload(替代旧手写 producer/consumer)。"""
    events: list[dict] = []

    def callback(event: dict) -> None:
        events.append(event)

    called_with = {}

    def _fake_resumable_upload(bucket, key, file_path_str, **kwargs):
        called_with["bucket"] = bucket
        called_with["key"] = key
        called_with["file_path"] = file_path_str
        called_with["part_size"] = kwargs.get("part_size")
        called_with["num_threads"] = kwargs.get("num_threads")
        # 模拟 oss2 调 progress_callback 推进
        progress_cb = kwargs.get("progress_callback")
        if progress_cb:
            total = big_file.stat().st_size
            progress_cb(total // 2, total)
            progress_cb(total, total)

    with patch.object(oss_upload, "oss2") as mock_oss2:
        mock_oss2.resumable_upload = _fake_resumable_upload
        mock_oss2.StsAuth.return_value = object()
        mock_oss2.Bucket.return_value = object()
        mock_oss2.ResumableStore.return_value = object()

        await upload_file_to_oss(
            token=_make_token(),
            file_path=big_file,
            mime_type="video/mp4",
            part_size=5 * 1024 * 1024,
            on_progress=callback,
            upload_mode="multipart",
        )

    # oss2.resumable_upload 必须被调
    assert called_with.get("key") == "user/abc/some-file-12345.mp4"
    assert called_with.get("part_size") == 5 * 1024 * 1024

    # 事件契约:multipart-started 在前,multipart-complete 在后,中间有 part-uploaded
    event_types = [e["type"] for e in events]
    assert event_types[0] == "multipart-started", f"首事件应是 multipart-started, 实际 {event_types}"
    assert event_types[-1] == "multipart-complete", f"末事件应是 multipart-complete, 实际 {event_types}"
    assert "part-uploaded" in event_types, "中间必须有至少一次 part-uploaded"


@pytest.mark.asyncio
async def test_part_uploaded_events_carry_completed_and_total(big_file: Path) -> None:
    """progress_callback 桥接必须填 completed/totalParts 给 flow.py 的进度日志器。"""
    events: list[dict] = []

    def _fake_resumable_upload(bucket, key, file_path_str, **kwargs):
        progress_cb = kwargs.get("progress_callback")
        total = big_file.stat().st_size
        # 模拟 4 次进度推进 (25% / 50% / 75% / 100%)
        for fraction in (0.25, 0.5, 0.75, 1.0):
            progress_cb(int(total * fraction), total)

    with patch.object(oss_upload, "oss2") as mock_oss2:
        mock_oss2.resumable_upload = _fake_resumable_upload
        mock_oss2.StsAuth.return_value = object()
        mock_oss2.Bucket.return_value = object()
        mock_oss2.ResumableStore.return_value = object()

        await upload_file_to_oss(
            token=_make_token(),
            file_path=big_file,
            mime_type="video/mp4",
            part_size=2 * 1024 * 1024,  # 6MB / 2MB = 3 parts
            on_progress=lambda e: events.append(e),
            upload_mode="multipart",
        )

    part_events = [e for e in events if e["type"] == "part-uploaded"]
    assert len(part_events) >= 1
    for e in part_events:
        assert e.get("completed") is not None, f"part-uploaded 必须带 completed, 实际 {e}"
        assert e.get("totalParts") is not None, f"part-uploaded 必须带 totalParts, 实际 {e}"
        assert e["completed"] <= e["totalParts"]

    # 最后一个 part-uploaded 必须达到 totalParts(给 flow 的进度日志器拉到 100%)
    final_part = part_events[-1]
    assert final_part["completed"] == final_part["totalParts"]


@pytest.mark.asyncio
async def test_direct_mode_does_not_touch_oss2(big_file: Path) -> None:
    """direct (小文件预签名 URL) 模式不应该碰 oss2。"""
    events: list[dict] = []

    def _fake_direct(url, file_path, mime_type):
        return None

    with patch.object(oss_upload, "oss2") as mock_oss2, \
         patch.object(oss_upload, "_direct_upload_with_presigned_url_from_path", side_effect=_fake_direct):
        mock_oss2.resumable_upload.side_effect = AssertionError("direct 模式不该调 oss2")

        await upload_file_to_oss(
            token=_make_token(),
            file_path=big_file,
            mime_type="video/mp4",
            on_progress=lambda e: events.append(e),
            upload_mode="direct",
        )

    assert any(e["type"] == "direct-upload-complete" for e in events)


@pytest.mark.asyncio
async def test_buffer_mode_in_multipart_raises_clearly() -> None:
    """老的 buffer 模式(整文件读内存)不再支持 multipart;明确报错而不是静默退化。"""
    with pytest.raises(ValueError, match="multipart upload via oss2 requires file_path"):
        await upload_file_to_oss(
            token=_make_token(),
            file_buffer=b"x" * 100,
            mime_type="application/octet-stream",
            upload_mode="multipart",
        )

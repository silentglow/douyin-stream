"""回归测试：_do_flow 失败时必须清理云端孤儿 recordId。

历史教训 v2026-05-26：5 个文件 OSS 上传超时,日志显示 21 个 recordId 被分配,
delete_record 只在成功路径触发 → 20 个 recordId 全部留在千问账号"记录"列表里变孤儿。

本测试锁定：拿到 token 之后任何步骤抛异常,必须调 delete_record 兜底清理。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from media_tools.transcribe.flow import run_real_flow
from media_tools.transcribe.runtime import ExportConfig


def _make_export_config() -> ExportConfig:
    return ExportConfig(file_type=3, extension=".md", label="md")


def _make_quota_snapshot():
    return type(
        "Q",
        (),
        {
            "remaining_upload": 100,
            "total_upload": 100,
            "remaining_equity": 100,
            "total_equity": 100,
        },
    )()


@pytest.fixture
def video_file(tmp_path: Path) -> Path:
    fp = tmp_path / "demo.mp4"
    fp.write_bytes(b"fake-mp4-content")
    return fp


@pytest.mark.asyncio
async def test_upload_failure_triggers_orphan_record_cleanup(video_file: Path, tmp_path: Path) -> None:
    """上传超时（OSS write timeout）→ 兜底 delete_record 被调用,清理孤儿 recordId。"""
    from media_tools.transcribe import flow as flow_mod

    fake_token = {
        "recordId": "orphan-record-id-12345",
        "genRecordId": "gen-orphan-id",
        "getLink": "https://oss-link/",
        "sts": {},
    }
    api_json = AsyncMock(return_value={"data": fake_token})
    upload = AsyncMock(
        side_effect=RuntimeError(
            "请求失败 (重试3次): ('Connection aborted.', TimeoutError('The write operation timed out'))"
        )
    )
    delete_record = AsyncMock(return_value=True)
    quota = AsyncMock(return_value=_make_quota_snapshot())

    with (
        patch.object(flow_mod, "api_json", api_json),
        patch.object(flow_mod, "upload_file_to_oss", upload),
        patch.object(flow_mod, "delete_record", delete_record),
        patch.object(flow_mod, "get_quota_snapshot", quota),
        patch.object(flow_mod, "record_flow_quota_usage", lambda **kw: None),
        patch.object(flow_mod, "load_config", return_value=type("C", (), {"save_debug_json": False})()),
        pytest.raises(RuntimeError, match="write operation timed out"),
    ):
        await run_real_flow(
            file_path=video_file,
            auth_state_path=tmp_path / "auth.json",
            download_dir=tmp_path / "out",
            export_config=_make_export_config(),
            account_id="test-account",
            shared_api=object(),
        )

    delete_record.assert_called_once()
    args, _ = delete_record.call_args
    assert args[1] == ["orphan-record-id-12345"], f"delete_record 必须被调用以清理孤儿 recordId,实际参数 {args}"


@pytest.mark.asyncio
async def test_export_failure_also_triggers_cleanup(video_file: Path, tmp_path: Path) -> None:
    """上传成功但 export_file 失败也必须清理 recordId（中间任何步骤失败都不能留孤儿）。"""
    from media_tools.transcribe import flow as flow_mod

    fake_token = {
        "recordId": "orphan-after-upload-id",
        "genRecordId": "gen-after-upload",
        "getLink": "https://oss-link/",
        "sts": {},
    }
    api_json_results = [
        {"data": fake_token},  # token/get
        {"data": {}},  # upload_heartbeat
        {"data": {"batchId": "batch-1"}},  # record/start
        {"data": {}},  # record/read
    ]
    api_json = AsyncMock(side_effect=api_json_results)
    upload = AsyncMock(return_value=None)
    poll = AsyncMock(return_value={"recordStatus": 30})
    export_fn = AsyncMock(side_effect=RuntimeError("export failed at qwen side"))
    delete_record = AsyncMock(return_value=True)

    with (
        patch.object(flow_mod, "api_json", api_json),
        patch.object(flow_mod, "upload_file_to_oss", upload),
        patch.object(flow_mod, "poll_until_done", poll),
        patch.object(flow_mod, "export_file", export_fn),
        patch.object(flow_mod, "delete_record", delete_record),
        patch.object(flow_mod, "get_quota_snapshot", AsyncMock(return_value=_make_quota_snapshot())),
        patch.object(flow_mod, "record_flow_quota_usage", lambda **kw: None),
        patch.object(flow_mod, "load_config", return_value=type("C", (), {"save_debug_json": False})()),
        pytest.raises(RuntimeError, match="export failed at qwen side"),
    ):
        await run_real_flow(
            file_path=video_file,
            auth_state_path=tmp_path / "auth.json",
            download_dir=tmp_path / "out",
            export_config=_make_export_config(),
            account_id="test-account",
            shared_api=object(),
        )

    delete_record.assert_called_once()
    args, _ = delete_record.call_args
    assert args[1] == ["orphan-after-upload-id"]


@pytest.mark.asyncio
async def test_cleanup_swallows_its_own_failure_to_preserve_original_exception(
    video_file: Path, tmp_path: Path
) -> None:
    """cleanup 自己失败时不能掩盖原始异常,原异常必须穿透。"""
    from media_tools.transcribe import flow as flow_mod

    fake_token = {
        "recordId": "orphan-id",
        "genRecordId": "gen-id",
        "getLink": "https://oss-link/",
        "sts": {},
    }
    api_json = AsyncMock(return_value={"data": fake_token})
    upload = AsyncMock(side_effect=RuntimeError("ORIGINAL_UPLOAD_ERROR"))
    # cleanup 也炸：模拟千问 API 同时挂了
    delete_record = AsyncMock(side_effect=RuntimeError("CLEANUP_ALSO_FAILED"))

    with (
        patch.object(flow_mod, "api_json", api_json),
        patch.object(flow_mod, "upload_file_to_oss", upload),
        patch.object(flow_mod, "delete_record", delete_record),
        patch.object(flow_mod, "get_quota_snapshot", AsyncMock(return_value=_make_quota_snapshot())),
        patch.object(flow_mod, "record_flow_quota_usage", lambda **kw: None),
        patch.object(flow_mod, "load_config", return_value=type("C", (), {"save_debug_json": False})()),
        pytest.raises(RuntimeError, match="ORIGINAL_UPLOAD_ERROR"),
    ):
        await run_real_flow(
            file_path=video_file,
            auth_state_path=tmp_path / "auth.json",
            download_dir=tmp_path / "out",
            export_config=_make_export_config(),
            account_id="test-account",
            shared_api=object(),
        )

    delete_record.assert_called_once()

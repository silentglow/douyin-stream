"""run_real_flow 在 run_id 模式下的打卡集成测试。

mock 掉所有 Qwen API 与 OSS 调用，重点验证：
1. 成功路径：stage 推进序列 queued -> uploaded -> transcribing -> exporting -> downloading
   且 record_id / gen_record_id / batch_id / export_url 都被正确写入
2. 失败路径：在某一步 raise 后，stage 停留在最近一次打卡，调用方可据此 mark_failed
3. run_id=None 时不写表（向后兼容）
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from media_tools.store.db import init_db
from media_tools.transcribe.flow import run_real_flow
from media_tools.transcribe.repository import TranscribeRunRepository
from media_tools.transcribe.runtime import ExportConfig


def _make_export_config() -> ExportConfig:
    return ExportConfig(
        file_type=1,
        extension=".docx",
        label="WORD",
    )


@pytest.fixture
def db_with_repo(tmp_path: Path):
    """初始化 transcribe_runs 表 + patch repo 的连接。"""
    db_file = tmp_path / "runs.db"
    init_db(str(db_file))
    conn = sqlite3.connect(db_file, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    with patch(
        "media_tools.transcribe.repository.get_db_connection",
        return_value=conn,
    ):
        yield conn
    conn.close()


@pytest.fixture
def video_file(tmp_path: Path) -> Path:
    fp = tmp_path / "demo.mp4"
    fp.write_bytes(b"fake mp4 bytes")
    return fp


def _patches_for_qwen(api_json_side_effect, *, raise_on_export: Exception | None = None):
    """通用 mock 套件：跳过 Playwright、mock 所有 Qwen 调用与文件下载。"""
    from media_tools.transcribe import flow as flow_mod

    upload_file_to_oss = AsyncMock(return_value=None)
    download_file = AsyncMock(return_value=None)
    quota = AsyncMock(
        return_value=type(
            "Q",
            (),
            {
                "remaining_upload": 100,
                "total_upload": 100,
                "remaining_equity": 100,
                "total_equity": 100,
            },
        )()
    )

    if raise_on_export is None:

        async def export_file(api, gen_record_id, export_config):
            return f"https://example.com/export/{gen_record_id}.docx"
    else:

        async def export_file(api, gen_record_id, export_config):
            raise raise_on_export

    return [
        patch.object(flow_mod, "api_json", side_effect=api_json_side_effect),
        patch.object(flow_mod, "upload_file_to_oss", upload_file_to_oss),
        patch.object(flow_mod, "download_file", download_file),
        patch.object(flow_mod, "get_quota_snapshot", quota),
        patch.object(flow_mod, "record_flow_quota_usage", lambda **kwargs: None),
        patch.object(flow_mod, "export_file", side_effect=export_file),
        patch.object(flow_mod, "delete_record", AsyncMock(return_value=True)),
        patch("media_tools.transcribe.flow.load_config", return_value=type("C", (), {"save_debug_json": False})()),
    ]


def _make_api_json_router(token_data: dict, batch_id: str = "batch-1"):
    """模拟 api_json：根据 URL 路径返回对应桩数据。"""

    async def router(api, url, body, headers=None):
        if "oss/token/get" in url:
            return {"data": token_data}
        if "upload_heartbeat" in url:
            return {"success": True}
        if "record/start" in url:
            return {"data": {"batchId": batch_id}}
        if "record/read" in url:
            return {"success": True}
        # poll_until_done 走的是 api_json 接口；返回已完成的 record
        if "record/get" in url or "record/list" in url or "batch/get" in url:
            return {"data": {"recordStatus": 30, "records": [{"recordStatus": 30}]}}
        return {"data": {"recordStatus": 30}}

    return router


@pytest.mark.asyncio
async def test_run_real_flow_records_all_checkpoints_on_success(
    db_with_repo: sqlite3.Connection, video_file: Path, tmp_path: Path
) -> None:
    run_id = TranscribeRunRepository.create(
        asset_id="asset-A",
        video_path=str(video_file),
        account_id="acc-1",
    )

    token_data = {
        "genRecordId": "gen-A",
        "recordId": "rec-A",
        "getLink": "https://oss/x",
        "ossAccessKeyId": "k",
        "policy": "p",
        "signature": "s",
        "host": "https://oss",
        "key": "k",
    }
    api_router = _make_api_json_router(token_data, batch_id="batch-A")

    # 跳过 poll_until_done 的真实轮询（不依赖 Qwen）
    with patch("media_tools.transcribe.flow.poll_until_done", AsyncMock(return_value={"recordStatus": 30})):
        for p in _patches_for_qwen(api_router):
            p.start()
        try:
            shared_api = object()  # 任意非 None 值即可跳过 Playwright 启动
            result = await run_real_flow(
                file_path=video_file,
                auth_state_path=tmp_path / "auth.json",
                download_dir=tmp_path / "out",
                export_config=_make_export_config(),
                account_id="acc-1",
                shared_api=shared_api,
                run_id=run_id,
            )
        finally:
            patch.stopall()

    assert result.gen_record_id == "gen-A"

    final = TranscribeRunRepository.get(run_id)
    assert final["stage"] == "downloading"  # mark_saved 由 orchestrator 调，不在 flow 里
    assert final["record_id"] == "rec-A"
    assert final["gen_record_id"] == "gen-A"
    assert final["batch_id"] == "batch-A"
    assert final["export_url"].startswith("https://example.com/export/gen-A")


@pytest.mark.asyncio
async def test_run_real_flow_stops_at_last_checkpoint_on_failure(
    db_with_repo: sqlite3.Connection, video_file: Path, tmp_path: Path
) -> None:
    """export 阶段失败 -> stage 应停在 transcribing（最近一次成功打卡）。"""
    run_id = TranscribeRunRepository.create(
        asset_id="asset-B",
        video_path=str(video_file),
        account_id="acc-1",
    )

    token_data = {
        "genRecordId": "gen-B",
        "recordId": "rec-B",
        "getLink": "x",
        "ossAccessKeyId": "k",
        "policy": "p",
        "signature": "s",
        "host": "x",
        "key": "k",
    }
    api_router = _make_api_json_router(token_data, batch_id="batch-B")

    with patch("media_tools.transcribe.flow.poll_until_done", AsyncMock(return_value={"recordStatus": 30})):
        for p in _patches_for_qwen(api_router, raise_on_export=RuntimeError("export blew up")):
            p.start()
        try:
            with pytest.raises(RuntimeError, match="export blew up"):
                await run_real_flow(
                    file_path=video_file,
                    auth_state_path=tmp_path / "auth.json",
                    download_dir=tmp_path / "out",
                    export_config=_make_export_config(),
                    account_id="acc-1",
                    shared_api=object(),
                    run_id=run_id,
                )
        finally:
            patch.stopall()

    final = TranscribeRunRepository.get(run_id)
    # 打卡序：queued -> uploaded -> transcribing -> exporting (raise 之前刚打) -> 失败
    # exporting 打卡发生在 export_file 调用之前，所以失败时 stage 已经是 exporting
    assert final["stage"] == "exporting"
    assert final["gen_record_id"] == "gen-B"
    assert final["batch_id"] == "batch-B"
    # export_url 不应该被写入（没拿到）
    assert final["export_url"] is None


@pytest.mark.asyncio
async def test_run_real_flow_without_run_id_does_not_write_table(
    db_with_repo: sqlite3.Connection, video_file: Path, tmp_path: Path
) -> None:
    """向后兼容：不传 run_id 时 transcribe_runs 表零写入。"""
    token_data = {
        "genRecordId": "gen-C",
        "recordId": "rec-C",
        "getLink": "x",
        "ossAccessKeyId": "k",
        "policy": "p",
        "signature": "s",
        "host": "x",
        "key": "k",
    }
    api_router = _make_api_json_router(token_data)

    with patch("media_tools.transcribe.flow.poll_until_done", AsyncMock(return_value={"recordStatus": 30})):
        for p in _patches_for_qwen(api_router):
            p.start()
        try:
            await run_real_flow(
                file_path=video_file,
                auth_state_path=tmp_path / "auth.json",
                download_dir=tmp_path / "out",
                export_config=_make_export_config(),
                account_id="acc-1",
                shared_api=object(),
                # run_id 故意不传
            )
        finally:
            patch.stopall()

    count = db_with_repo.execute("SELECT COUNT(*) FROM transcribe_runs").fetchone()[0]
    assert count == 0

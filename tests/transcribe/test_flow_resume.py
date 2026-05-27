"""run_real_flow 的续传分支测试（Step 13a/13b）。

13a：resume_state 有 export_url 时，零 Qwen API 调用，只 download。
13a fallback：download 失败时回退到完整 flow，stage 重置为 queued。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from media_tools.common.runtime import ExportConfig
from media_tools.store.db import init_db
from media_tools.transcribe.flow import ResumeState, run_real_flow
from media_tools.transcribe.repository import TranscribeRunRepository


def _make_export_config() -> ExportConfig:
    return ExportConfig(file_type=1, extension=".docx", label="WORD")


@pytest.fixture
def db(tmp_path: Path):
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
    fp.write_bytes(b"fake")
    return fp


@pytest.mark.asyncio
async def test_resume_with_export_url_skips_all_qwen_apis(
    db: sqlite3.Connection, video_file: Path, tmp_path: Path
) -> None:
    """有 export_url 时，零调用 Qwen，仅 download_file 被调一次。"""
    run_id = TranscribeRunRepository.create(
        asset_id="asset-RES",
        video_path=str(video_file),
        account_id="acc-1",
    )
    TranscribeRunRepository.update_stage(
        run_id,
        "downloading",
        {"gen_record_id": "gen-X", "record_id": "rec-X", "export_url": "https://x/out.docx"},
    )

    from media_tools.transcribe import flow as flow_mod

    download_file = AsyncMock(return_value=None)
    api_json = AsyncMock(side_effect=AssertionError("api_json 不应被调用"))
    upload = AsyncMock(side_effect=AssertionError("upload 不应被调用"))
    export_fn = AsyncMock(side_effect=AssertionError("export_file 不应被调用"))
    poll = AsyncMock(side_effect=AssertionError("poll_until_done 不应被调用"))
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

    with (
        patch.object(flow_mod, "download_file", download_file),
        patch.object(flow_mod, "api_json", api_json),
        patch.object(flow_mod, "upload_file_to_oss", upload),
        patch.object(flow_mod, "export_file", export_fn),
        patch.object(flow_mod, "poll_until_done", poll),
        patch.object(flow_mod, "delete_record", AsyncMock(return_value=True)),
        patch.object(flow_mod, "get_quota_snapshot", quota),
        patch.object(flow_mod, "record_flow_quota_usage", lambda **kw: None),
        patch.object(flow_mod, "load_config", return_value=type("C", (), {"save_debug_json": False})()),
    ):
        result = await run_real_flow(
            file_path=video_file,
            auth_state_path=tmp_path / "auth.json",
            download_dir=tmp_path / "out",
            export_config=_make_export_config(),
            account_id="acc-1",
            shared_api=object(),
            run_id=run_id,
            resume_state=ResumeState(
                stage="downloading",
                record_id="rec-X",
                gen_record_id="gen-X",
                export_url="https://x/out.docx",
            ),
        )

    assert result.gen_record_id == "gen-X"
    assert result.record_id == "rec-X"
    download_file.assert_called_once()
    # 所有 Qwen API 必须 0 调用（mock 的 side_effect 会触发 AssertionError 如果被调）
    api_json.assert_not_called()
    upload.assert_not_called()
    export_fn.assert_not_called()
    poll.assert_not_called()


@pytest.mark.asyncio
async def test_resume_with_export_url_fallbacks_when_download_fails(
    db: sqlite3.Connection, video_file: Path, tmp_path: Path
) -> None:
    """download 失败 -> stage 回退到 queued -> 完整 flow 接管完成转写。"""
    run_id = TranscribeRunRepository.create(
        asset_id="asset-RES",
        video_path=str(video_file),
        account_id="acc-1",
    )
    TranscribeRunRepository.update_stage(
        run_id,
        "downloading",
        {"gen_record_id": "gen-Y", "record_id": "rec-Y", "export_url": "https://expired.example/out"},
    )

    from media_tools.transcribe import flow as flow_mod

    download_calls: list[str] = []

    async def fake_download(url, target):
        download_calls.append(str(url))
        if url == "https://expired.example/out":
            raise RuntimeError("download timeout")
        # 第二次（完整 flow 出来的新 url）必须能成功
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("ok")

    token_data = {
        "genRecordId": "gen-NEW",
        "recordId": "rec-NEW",
        "getLink": "x",
        "ossAccessKeyId": "k",
        "policy": "p",
        "signature": "s",
        "host": "x",
        "key": "k",
    }

    async def api_router(api, url, body, headers=None):
        if "oss/token/get" in url:
            return {"data": token_data}
        if "record/start" in url:
            return {"data": {"batchId": "batch-NEW"}}
        return {"success": True}

    async def export_url_router(api, gen_record_id, export_config):
        return f"https://example.com/export/{gen_record_id}.docx"

    upload = AsyncMock(return_value=None)
    quota = AsyncMock(
        return_value=type(
            "Q",
            (),
            {
                "remaining_upload": 1,
                "total_upload": 1,
                "remaining_equity": 1,
                "total_equity": 1,
            },
        )()
    )

    with (
        patch.object(flow_mod, "download_file", side_effect=fake_download),
        patch.object(flow_mod, "api_json", side_effect=api_router),
        patch.object(flow_mod, "upload_file_to_oss", upload),
        patch.object(flow_mod, "export_file", side_effect=export_url_router),
        patch.object(flow_mod, "poll_until_done", AsyncMock(return_value={"recordStatus": 30})),
        patch.object(flow_mod, "delete_record", AsyncMock(return_value=True)),
        patch.object(flow_mod, "get_quota_snapshot", quota),
        patch.object(flow_mod, "record_flow_quota_usage", lambda **kw: None),
        patch.object(flow_mod, "load_config", return_value=type("C", (), {"save_debug_json": False})()),
    ):
        result = await run_real_flow(
            file_path=video_file,
            auth_state_path=tmp_path / "auth.json",
            download_dir=tmp_path / "out",
            export_config=_make_export_config(),
            account_id="acc-1",
            shared_api=object(),
            run_id=run_id,
            resume_state=ResumeState(
                stage="downloading",
                record_id="rec-Y",
                gen_record_id="gen-Y",
                export_url="https://expired.example/out",
            ),
        )

    # 续传 download 失败一次，完整 flow 重新拿到 gen-NEW 成功 download 一次
    assert len(download_calls) == 2
    assert download_calls[0] == "https://expired.example/out"
    assert "gen-NEW.docx" in download_calls[1]
    assert result.gen_record_id == "gen-NEW"

    # transcribe_runs 已被完整 flow 重新打卡到 downloading + 新 export_url
    final = TranscribeRunRepository.get(run_id)
    assert final["stage"] == "downloading"
    assert final["gen_record_id"] == "gen-NEW"
    assert "gen-NEW" in (final["export_url"] or "")


@pytest.mark.asyncio
async def test_no_resume_state_runs_full_flow(db: sqlite3.Connection, video_file: Path, tmp_path: Path) -> None:
    """resume_state=None 时行为与 Step 11 完全一致（向后兼容）。"""
    run_id = TranscribeRunRepository.create(
        asset_id="asset-FULL",
        video_path=str(video_file),
        account_id="acc-1",
    )

    from media_tools.transcribe import flow as flow_mod

    token_data = {
        "genRecordId": "gen-F",
        "recordId": "rec-F",
        "getLink": "x",
        "ossAccessKeyId": "k",
        "policy": "p",
        "signature": "s",
        "host": "x",
        "key": "k",
    }

    async def api_router(api, url, body, headers=None):
        if "oss/token/get" in url:
            return {"data": token_data}
        if "record/start" in url:
            return {"data": {"batchId": "batch-F"}}
        return {"success": True}

    async def export_url(api, gen_record_id, export_config):
        return f"https://export/{gen_record_id}.docx"

    with (
        patch.object(flow_mod, "api_json", side_effect=api_router),
        patch.object(flow_mod, "upload_file_to_oss", AsyncMock()),
        patch.object(flow_mod, "export_file", side_effect=export_url),
        patch.object(flow_mod, "poll_until_done", AsyncMock(return_value={"recordStatus": 30})),
        patch.object(flow_mod, "delete_record", AsyncMock(return_value=True)),
        patch.object(flow_mod, "download_file", AsyncMock()),
        patch.object(
            flow_mod,
            "get_quota_snapshot",
            AsyncMock(
                return_value=type(
                    "Q",
                    (),
                    {
                        "remaining_upload": 1,
                        "total_upload": 1,
                        "remaining_equity": 1,
                        "total_equity": 1,
                    },
                )()
            ),
        ),
        patch.object(flow_mod, "record_flow_quota_usage", lambda **kw: None),
        patch.object(flow_mod, "load_config", return_value=type("C", (), {"save_debug_json": False})()),
    ):
        result = await run_real_flow(
            file_path=video_file,
            auth_state_path=tmp_path / "auth.json",
            download_dir=tmp_path / "out",
            export_config=_make_export_config(),
            account_id="acc-1",
            shared_api=object(),
            run_id=run_id,
            resume_state=None,
        )

    assert result.gen_record_id == "gen-F"
    final = TranscribeRunRepository.get(run_id)
    assert final["stage"] == "downloading"


@pytest.mark.asyncio
async def test_resume_with_gen_record_id_skips_upload(db: sqlite3.Connection, video_file: Path, tmp_path: Path) -> None:
    """Step 13b：有 gen_record_id 但无 export_url 时，跳过 token/upload/heartbeat/start，
    仅调 poll/read/export/download。"""
    run_id = TranscribeRunRepository.create(
        asset_id="asset-G",
        video_path=str(video_file),
        account_id="acc-1",
    )
    TranscribeRunRepository.update_stage(
        run_id,
        "transcribing",
        {"gen_record_id": "gen-G", "record_id": "rec-G", "batch_id": "batch-G"},
    )

    from media_tools.transcribe import flow as flow_mod

    upload = AsyncMock(side_effect=AssertionError("upload 不应被调用"))
    api_calls: list[str] = []

    async def api_router(api, url, body, headers=None):
        api_calls.append(url)
        if "oss/token/get" in url:
            raise AssertionError("token/get 不应被调用")
        if "upload_heartbeat" in url:
            raise AssertionError("upload_heartbeat 不应被调用")
        if "record/start" in url:
            raise AssertionError("record/start 不应被调用")
        # record/read 应当被调（虽然失败也容忍）
        return {"success": True}

    async def export_url_fn(api, gen_record_id, export_config):
        assert gen_record_id == "gen-G", "应当复用历史 gen_record_id"
        return f"https://export/{gen_record_id}.docx"

    download = AsyncMock(return_value=None)

    with (
        patch.object(flow_mod, "api_json", side_effect=api_router),
        patch.object(flow_mod, "upload_file_to_oss", upload),
        patch.object(flow_mod, "export_file", side_effect=export_url_fn),
        patch.object(flow_mod, "poll_until_done", AsyncMock(return_value={"recordStatus": 30})),
        patch.object(flow_mod, "delete_record", AsyncMock(return_value=True)),
        patch.object(flow_mod, "download_file", download),
        patch.object(
            flow_mod,
            "get_quota_snapshot",
            AsyncMock(
                return_value=type(
                    "Q",
                    (),
                    {
                        "remaining_upload": 1,
                        "total_upload": 1,
                        "remaining_equity": 1,
                        "total_equity": 1,
                    },
                )()
            ),
        ),
        patch.object(flow_mod, "record_flow_quota_usage", lambda **kw: None),
        patch.object(flow_mod, "load_config", return_value=type("C", (), {"save_debug_json": False})()),
    ):
        result = await run_real_flow(
            file_path=video_file,
            auth_state_path=tmp_path / "auth.json",
            download_dir=tmp_path / "out",
            export_config=_make_export_config(),
            account_id="acc-1",
            shared_api=object(),
            run_id=run_id,
            resume_state=ResumeState(
                stage="transcribing",
                record_id="rec-G",
                gen_record_id="gen-G",
                batch_id="batch-G",
            ),
        )

    assert result.gen_record_id == "gen-G"
    assert result.record_id == "rec-G"
    upload.assert_not_called()
    download.assert_called_once()
    # 唯一允许的 api_json 调用是 record/read，其它都是 AssertionError 桩
    assert all("record/read" in u for u in api_calls)

    # transcribe_runs 应被推进到 downloading + 写入新的 export_url
    final = TranscribeRunRepository.get(run_id)
    assert final["stage"] == "downloading"
    assert final["export_url"] == "https://export/gen-G.docx"


@pytest.mark.asyncio
async def test_resume_gen_record_id_fallback_when_poll_fails(
    db: sqlite3.Connection, video_file: Path, tmp_path: Path
) -> None:
    """关键安全网：续传分支 poll 抛错（如 gen_record_id 已失效）时，
    必须 fallback 到完整 flow（哪怕代价是重新上传），保证业务永远跑通。"""
    run_id = TranscribeRunRepository.create(
        asset_id="asset-FB",
        video_path=str(video_file),
        account_id="acc-1",
    )
    TranscribeRunRepository.update_stage(
        run_id,
        "transcribing",
        {"gen_record_id": "gen-STALE", "record_id": "rec-STALE"},
    )

    from media_tools.transcribe import flow as flow_mod

    # poll 第一次抛错（续传分支），第二次成功（完整 flow 接管）
    poll_calls = {"n": 0}

    async def poll_side_effect(api, gen_record_id, timeout_seconds=15 * 60):
        poll_calls["n"] += 1
        if poll_calls["n"] == 1:
            assert gen_record_id == "gen-STALE", "续传应先用历史 gen_record_id"
            raise RuntimeError("record not found")
        # 完整 flow 用新 gen_record_id
        assert gen_record_id == "gen-NEW"
        return {"recordStatus": 30}

    token_data = {
        "genRecordId": "gen-NEW",
        "recordId": "rec-NEW",
        "getLink": "x",
        "ossAccessKeyId": "k",
        "policy": "p",
        "signature": "s",
        "host": "x",
        "key": "k",
    }

    async def api_router(api, url, body, headers=None):
        if "oss/token/get" in url:
            return {"data": token_data}
        if "record/start" in url:
            return {"data": {"batchId": "batch-NEW"}}
        return {"success": True}

    async def export_url(api, gen_record_id, export_config):
        return f"https://export/{gen_record_id}.docx"

    with (
        patch.object(flow_mod, "api_json", side_effect=api_router),
        patch.object(flow_mod, "upload_file_to_oss", AsyncMock()),
        patch.object(flow_mod, "export_file", side_effect=export_url),
        patch.object(flow_mod, "poll_until_done", side_effect=poll_side_effect),
        patch.object(flow_mod, "delete_record", AsyncMock(return_value=True)),
        patch.object(flow_mod, "download_file", AsyncMock()),
        patch.object(
            flow_mod,
            "get_quota_snapshot",
            AsyncMock(
                return_value=type(
                    "Q",
                    (),
                    {
                        "remaining_upload": 1,
                        "total_upload": 1,
                        "remaining_equity": 1,
                        "total_equity": 1,
                    },
                )()
            ),
        ),
        patch.object(flow_mod, "record_flow_quota_usage", lambda **kw: None),
        patch.object(flow_mod, "load_config", return_value=type("C", (), {"save_debug_json": False})()),
    ):
        result = await run_real_flow(
            file_path=video_file,
            auth_state_path=tmp_path / "auth.json",
            download_dir=tmp_path / "out",
            export_config=_make_export_config(),
            account_id="acc-1",
            shared_api=object(),
            run_id=run_id,
            resume_state=ResumeState(
                stage="transcribing",
                record_id="rec-STALE",
                gen_record_id="gen-STALE",
            ),
        )

    # 续传失败一次，完整 flow 跑出新 gen_record_id 成功
    assert result.gen_record_id == "gen-NEW"
    assert poll_calls["n"] == 2

    final = TranscribeRunRepository.get(run_id)
    assert final["stage"] == "downloading"
    assert final["gen_record_id"] == "gen-NEW"

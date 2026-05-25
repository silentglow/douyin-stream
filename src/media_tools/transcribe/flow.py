from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

from media_tools.logger import get_logger
from .errors import TranscribeErrorClassifier, TranscribeError
logger = get_logger(__name__)

from .auth_state import resolve_qwen_cookie_string
from .config import load_config
from .export_utils import FlowDebugArtifacts, _get_video_title_from_db, build_export_output_path, save_debug_artifacts
from .http import RequestsApiContext, api_json, download_file
from .oss_upload import upload_file_to_oss
from .quota import get_quota_snapshot, record_quota_consumption
from .runtime import ExportConfig, ensure_dir, guess_mime_type, now_stamp


@dataclass(frozen=True)
class FlowResult:
    record_id: str
    gen_record_id: str
    export_path: Path
    remote_deleted: bool


@dataclass(frozen=True)
class ResumeState:
    stage: str = "queued"
    record_id: Optional[str] = None
    gen_record_id: Optional[str] = None
    batch_id: Optional[str] = None
    export_url: Optional[str] = None


def build_upload_tag(file_path: Union[str, Path], mime_type: str) -> dict[str, Any]:
    parsed = Path(file_path)
    is_video = 1 if mime_type.startswith("video/") else 0
    return {
        "showName": parsed.stem,
        "fileFormat": parsed.suffix.removeprefix("."),
        "fileType": "local",
        "lang": "cn",
        "roleSplitNum": -1,
        "translateSwitch": 0,
        "transTargetValue": 0,
        "originalTag": json.dumps({"isVideo": is_video}),
        "client": "web",
    }


def transcript_headers(gen_record_id: str) -> dict[str, str]:
    return {
        "referer": f"https://www.qianwen.com/efficiency/doc/transcripts/{gen_record_id}?source=2",
        "x-tw-from": "tongyi",
    }


async def poll_until_done(context: Any, gen_record_id: str, timeout_seconds: float = 15 * 60) -> dict[str, Any]:
    url = "https://api.qianwen.com/assistant/api/record/list/poll?c=tongyi-web"
    payload = {
        "status": [10, 20, 30, 40, 41],
        "fileTypes": [],
        "beginTime": "",
        "mediaType": "",
        "endTime": "",
        "showName": "",
        "read": "",
        "lang": "",
        "shareUserId": "",
        "pageNo": 1,
        "pageSize": 1000,
        "recordSources": ["chat", "zhiwen", "tingwu"],
        "taskTypes": ["local", "net_source", "doc_read", "url_read", "paper_read", "book_read"],
        "terminal": "web",
        "module": "uploadhistory",
    }

    async def _poll_loop() -> dict[str, Any]:
        while True:
            response = await api_json(context, url, payload)
            data = response.get("data") or {}
            for batch in data.get("batchRecord", []):
                for record in batch.get("recordList", []):
                    if record.get("genRecordId") == gen_record_id:
                        status = record.get("recordStatus")
                        if status == 30:
                            return record
                        if status in (40, 41):
                            fail_reason = record.get("failReason") or record.get("errorMessage") or f"recordStatus={status}"
                            error_info = TranscribeErrorClassifier.classify(fail_reason)
                            logger.error(f"转写错误 [{error_info.error_code}]: {error_info.message} - {error_info.suggestion}")
                            raise TranscribeError(error_info, detail=fail_reason)
            import random
            await asyncio.sleep(5 + random.uniform(0, 2))

    try:
        return await asyncio.wait_for(_poll_loop(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        error_info = TranscribeErrorClassifier.classify("timeout")
        raise TranscribeError(error_info, detail=f"转写轮询超时 ({timeout_seconds}s)")


async def delete_record(context: Any, record_ids: list[str]) -> bool:
    if not record_ids:
        return False
    response = await api_json(
        context,
        "https://api.qianwen.com/assistant/api/record/task/delete?c=tongyi-web",
        {"recordIds": record_ids},
    )
    return response.get("data") is True


async def export_file(context: Any, gen_record_id: str, export_config: ExportConfig) -> str:
    headers = transcript_headers(gen_record_id)
    app_config = load_config()
    max_attempts = app_config.export_max_retries
    initial_backoff = app_config.export_initial_backoff_seconds
    export_task_id = ""
    export_start_json: Any = {}
    for attempt in range(max_attempts):
        export_start_json = await api_json(
            context,
            "https://audio-api.qianwen.com/api/export/request?c=tongyi-web",
            {
                "action": "exportTrans",
                "transIds": [gen_record_id],
                "exportDetails": [
                    {
                        "docType": 1,
                        "fileType": export_config.file_type,
                        "withSpeaker": True,
                        "withTimeStamp": True,
                    }
                ],
            },
            headers,
        )
        export_task_id = str((export_start_json.get("data") or {}).get("exportTaskId", "")).strip()
        if export_task_id:
            break
        code = str(export_start_json.get("code", ""))
        message = str(export_start_json.get("message", "")).lower()
        request_too_fast = code == "EPO.RequestTooFast" or "request too fast" in message
        if not request_too_fast or attempt == max_attempts - 1:
            error_info = TranscribeErrorClassifier.classify(f"export error: {message}")
            raise TranscribeError(error_info, detail=f"code={code} message={message}")
        await asyncio.sleep(initial_backoff * (2**attempt))

    if not export_task_id:
        error_info = TranscribeErrorClassifier.classify("export failed")
        raise TranscribeError(error_info, detail="无法获取导出任务ID")

    for _ in range(60):
        export_poll_json = await api_json(
            context,
            "https://audio-api.qianwen.com/api/export/request?c=tongyi-web",
            {
                "action": "getExportStatus",
                "exportTaskId": export_task_id,
            },
            headers,
        )
        export_data = export_poll_json.get("data") or {}
        if export_data.get("exportStatus") == 1:
            export_urls = export_data.get("exportUrls", [])
            export_url = export_urls[0].get("url", "") if export_urls else ""
            if export_url:
                return export_url
        await asyncio.sleep(5)

    error_info = TranscribeErrorClassifier.classify("export timeout")
    raise TranscribeError(error_info, detail=f"导出轮询超时 exportTaskId={export_task_id}")


def record_flow_quota_usage(
    *,
    account_id: str,
    before_snapshot,
    after_snapshot,
    log,
) -> int:
    consumed_minutes = max(0, before_snapshot.remaining_upload - after_snapshot.remaining_upload)
    record_quota_consumption(
        account_id=account_id,
        consumed_minutes=consumed_minutes,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
    )
    log(f"quota upload remaining after run: {after_snapshot.remaining_upload}/{after_snapshot.total_upload}")
    log(f"tracked quota consumption for this run: {consumed_minutes} minutes")
    return consumed_minutes


async def run_real_flow(
    *,
    file_path: Union[str, Path],
    auth_state_path: Union[str, Path],
    download_dir: Union[str, Path],
    export_config: ExportConfig,
    should_delete: bool = False,
    account_id: str = "",
    cookie_string: str = "",
    account_upload_lock: asyncio.Lock | None = None,
    title: Optional[str] = None,
    shared_api: Optional[Any] = None,
    run_id: Optional[str] = None,
    resume_state: ResumeState | None = None,
) -> FlowResult:
    input_path = Path(file_path).resolve()
    output_dir = Path(download_dir).resolve()
    mime_type = guess_mime_type(input_path)
    stats = input_path.stat()
    quota_before = await get_quota_snapshot(
        auth_state_path=auth_state_path,
        account_id=account_id,
        cookie_string=cookie_string,
    )
    log = _make_flow_logger(input_path.name)

    def _checkpoint(stage: str, extra: Optional[dict[str, Any]] = None) -> None:
        if not run_id:
            return
        try:
            from media_tools.transcribe.repository import TranscribeRunRepository
            TranscribeRunRepository.update_stage(run_id, stage, extra)
        except (sqlite3.Error, OSError) as exc:
            logger.warning(f"transcribe_runs 打卡失败 (run_id={run_id}, stage={stage}): {exc}")

    async def _safe_cleanup_old_record(api: Any, old_record_id: Optional[str]) -> None:
        """resume 失败回退时清理云端旧记录，避免后续 _do_flow 覆盖 gen_record_id 后变成孤儿。
        清理失败只记录日志，不让主流程崩溃。"""
        if not old_record_id:
            return
        try:
            ok = await delete_record(api, [old_record_id])
            if ok:
                log(f"resume 回退：已清理云端旧记录 record_id={old_record_id}")
            else:
                logger.warning(f"resume 回退清理云端记录返回失败 record_id={old_record_id}")
        except (RuntimeError, OSError, ValueError) as exc:
            logger.warning(f"resume 回退清理云端记录异常 record_id={old_record_id}: {exc}")

    async def _do_flow(api: Any) -> FlowResult:
        log(f"Using file: {input_path}")
        log(f"File size: {stats.st_size}")
        log(f"quota upload remaining: {quota_before.remaining_upload}/{quota_before.total_upload}")

        token_json = await api_json(
            api,
            "https://api.qianwen.com/assistant/api/record/oss/token/get?c=tongyi-web",
            {
                "taskType": "local",
                "useSts": 1,
                "fileSize": stats.st_size,
                "dirIdStr": "",
                "fileContentType": mime_type,
                "bizTerminal": "web",
                "tag": build_upload_tag(input_path, mime_type),
            },
        )
        if not isinstance(token_json, dict) or not isinstance(token_json.get("data"), dict):
            error_info = TranscribeErrorClassifier.classify("auth error")
            raise RuntimeError(f"{error_info.message}")
        token = token_json["data"]
        log(f"genRecordId: {token['genRecordId']}")
        log(f"recordId: {token['recordId']}")

        if account_upload_lock is None:
            await upload_file_to_oss(
                token=token,
                file_path=input_path,
                mime_type=mime_type,
                on_progress=_make_upload_progress_logger(log),
            )
        else:
            async with account_upload_lock:
                await upload_file_to_oss(
                    token=token,
                    file_path=input_path,
                    mime_type=mime_type,
                    on_progress=_make_upload_progress_logger(log),
                )

        await api_json(
            api,
            "https://api.qianwen.com/assistant/api/record/upload_heartbeat?c=tongyi-web",
            {"genRecordId": token["genRecordId"]},
        )
        log("upload heartbeat sent")

        _checkpoint("uploaded", {
            "record_id": token["recordId"],
            "gen_record_id": token["genRecordId"],
        })

        start_json = await api_json(
            api,
            "https://api.qianwen.com/assistant/api/record/start?c=tongyi-web",
            {
                "taskType": "local",
                "tingwuRequest": {
                    "fileLink": token["getLink"],
                    "transId": token["genRecordId"],
                    "fileSize": stats.st_size,
                },
                "bizTerminal": "web",
                "dirIdStr": "",
            },
        )
        batch_id = (start_json.get("data") or {}).get("batchId", "")
        log(f"started batchId={batch_id}")

        _checkpoint("transcribing", {"batch_id": batch_id})

        completed_record = await poll_until_done(api, token["genRecordId"])
        log(f"record completed with status={completed_record.get('recordStatus', 'unknown')}")

        await api_json(
            api,
            "https://api.qianwen.com/assistant/api/record/read?c=tongyi-web",
            {"recordIds": [token["recordId"]]},
        )

        _checkpoint("exporting")

        export_url = await export_file(api, token["genRecordId"], export_config)

        _checkpoint("downloading", {"export_url": export_url})

        run_stamp = now_stamp()

        resolved_title = title or _get_video_title_from_db(input_path)

        export_out = build_export_output_path(
            input_path=input_path,
            output_dir=output_dir,
            export_config=export_config,
            run_stamp=run_stamp,
            title=resolved_title,
        )

        ensure_dir(output_dir)
        await download_file(export_url, export_out)

        log(f"{export_config.label} saved: {export_out}")

        if load_config().save_debug_json:
            headers = transcript_headers(token["genRecordId"])
            transcript_json = await api_json(
                api,
                "https://audio-api.qianwen.com/api/trans/getTransResult?c=tongyi-web",
                {
                    "action": "getTransResult",
                    "version": "1.0",
                    "transId": token["genRecordId"],
                },
                headers,
            )
            doc_edit_json = await api_json(
                api,
                "https://api.qianwen.com/api/doc/getTransDocEdit?c=tongyi-web",
                {
                    "action": "getTransDocEdit",
                    "version": "1.0",
                    "transId": token["genRecordId"],
                },
                headers,
            )
            output_base = input_path.stem
            debug_artifacts = save_debug_artifacts(
                output_dir=output_dir,
                output_base=output_base,
                run_stamp=run_stamp,
                transcript_json=transcript_json,
                doc_edit_json=doc_edit_json,
            )
            log(f"transcript saved: {debug_artifacts.transcript_path}")
            log(f"doc edit saved: {debug_artifacts.doc_edit_path}")

        deleted = False
        if should_delete:
            deleted = await delete_record(api, [token["recordId"]])
            log(f"delete status: {'success' if deleted else 'failed'}")

        quota_after = await get_quota_snapshot(
            auth_state_path=auth_state_path,
            account_id=account_id,
            cookie_string=cookie_string,
        )
        record_flow_quota_usage(
            account_id=account_id,
            before_snapshot=quota_before,
            after_snapshot=quota_after,
            log=log,
        )
        return FlowResult(
            record_id=token["recordId"],
            gen_record_id=token["genRecordId"],
            export_path=export_out,
            remote_deleted=deleted,
        )

    async def _try_resume_export_only(api: Any) -> FlowResult | None:
        if resume_state is None or not resume_state.export_url:
            return None
        # record_id 缺失时无法回退清理，直接走完整 flow 避免孤儿记录
        if not resume_state.record_id:
            logger.warning(
                f"resume[export_url] 跳过：record_id 缺失，无法回退清理，"
                f"gen_record_id={resume_state.gen_record_id}"
            )
            return None
        try:
            log(f"resume[export_url]: download only, gen_record_id={resume_state.gen_record_id}")
            run_stamp = now_stamp()
            resolved_title = title or _get_video_title_from_db(input_path)
            export_out = build_export_output_path(
                input_path=input_path,
                output_dir=output_dir,
                export_config=export_config,
                run_stamp=run_stamp,
                title=resolved_title,
            )
            ensure_dir(output_dir)
            await download_file(resume_state.export_url, export_out)
            log(f"{export_config.label} resumed: {export_out}")
            return FlowResult(
                record_id=resume_state.record_id or "",
                gen_record_id=resume_state.gen_record_id or "",
                export_path=export_out,
                remote_deleted=False,
            )
        except (RuntimeError, OSError, ValueError) as exc:
            logger.warning(
                f"resume[export_url] 失败，回退到完整 flow: {exc}",
                exc_info=True,
            )
            # 回退前先清掉云端旧记录：_do_flow 会拿新 token 覆盖 record_id/gen_record_id,
            # 如果不在这里清,旧 record 就会变成孤儿（额度已扣但 DB 找不回 record_id）
            await _safe_cleanup_old_record(api, resume_state.record_id)
            if run_id:
                try:
                    from media_tools.transcribe.repository import TranscribeRunRepository
                    TranscribeRunRepository.update_stage(run_id, "queued")
                except Exception:  # noqa: defensive – stage 重置失败不影响主流程
                    logger.debug("重置 stage 失败，但不影响 fallback 流程", exc_info=True)
            return None

    async def _try_resume_from_gen_record(api: Any) -> FlowResult | None:
        if resume_state is None or not resume_state.gen_record_id or not resume_state.record_id:
            return None
        if resume_state.export_url:
            return None

        try:
            log(
                f"resume[gen_record_id]: skip upload, "
                f"gen_record_id={resume_state.gen_record_id} record_id={resume_state.record_id}"
            )

            completed_record = await poll_until_done(api, resume_state.gen_record_id)
            log(f"resumed record completed with status={completed_record['recordStatus']}")

            try:
                await api_json(
                    api,
                    "https://api.qianwen.com/assistant/api/record/read?c=tongyi-web",
                    {"recordIds": [resume_state.record_id]},
                )
            except (RuntimeError, OSError, ValueError) as exc:
                logger.debug(f"resume: record/read 失败但不影响后续: {exc}")

            _checkpoint("exporting")

            export_url = await export_file(api, resume_state.gen_record_id, export_config)

            _checkpoint("downloading", {"export_url": export_url})

            run_stamp = now_stamp()
            resolved_title = title or _get_video_title_from_db(input_path)
            export_out = build_export_output_path(
                input_path=input_path,
                output_dir=output_dir,
                export_config=export_config,
                run_stamp=run_stamp,
                title=resolved_title,
            )
            ensure_dir(output_dir)
            await download_file(export_url, export_out)
            log(f"{export_config.label} resumed: {export_out}")

            return FlowResult(
                record_id=resume_state.record_id,
                gen_record_id=resume_state.gen_record_id,
                export_path=export_out,
                remote_deleted=False,
            )
        except (RuntimeError, OSError, ValueError) as exc:
            logger.warning(
                f"resume[gen_record_id] 失败，回退到完整 flow: {exc}",
                exc_info=True,
            )
            # 同样：清旧 record 避免 _do_flow 覆盖后变成孤儿
            await _safe_cleanup_old_record(api, resume_state.record_id)
            if run_id:
                try:
                    from media_tools.transcribe.repository import TranscribeRunRepository
                    TranscribeRunRepository.update_stage(run_id, "queued")
                except Exception:  # noqa: defensive – stage 重置失败不影响主流程
                    logger.debug("重置 stage 失败，但不影响 fallback 流程", exc_info=True)
            return None

    # api 统一在最外层准备，两个 resume 函数和 _do_flow 共用同一个 context；
    # 这样 resume 失败回退时也能用同一 api 清云端记录，避免旧 gen_record_id 被
    # 覆盖后变孤儿（resource leak 修复）。
    if shared_api is not None:
        resumed = await _try_resume_export_only(shared_api)
        if resumed is not None:
            return resumed
        from_gen = await _try_resume_from_gen_record(shared_api)
        if from_gen is not None:
            return from_gen
        return await _do_flow(shared_api)

    resolved_cookie = cookie_string.strip() or resolve_qwen_cookie_string(
        auth_state_path=auth_state_path,
        account_id=account_id,
    )
    api = RequestsApiContext(cookie_string=resolved_cookie)
    try:
        resumed = await _try_resume_export_only(api)
        if resumed is not None:
            return resumed
        from_gen = await _try_resume_from_gen_record(api)
        if from_gen is not None:
            return from_gen
        return await _do_flow(api)
    finally:
        await api.dispose()


def _make_flow_logger(file_name: str):
    def log(message: str) -> None:
        logger.info(f"[{file_name}] {message}")

    return log


def _make_upload_progress_logger(log):
    last_bucket = -1

    def handle_event(event: dict[str, Any]) -> None:
        nonlocal last_bucket
        event_type = event.get("type")
        if event_type == "direct-upload-complete":
            log("direct presigned upload completed")
        elif event_type == "direct-upload-failed":
            error = event.get("error")
            if event.get("mode") == "auto":
                log(f"direct upload failed, falling back to multipart: {error}")
            else:
                log(f"direct upload failed: {error}")
        elif event_type == "multipart-started":
            log(f"uploadId: {event.get('uploadId')}")
        elif event_type == "part-uploaded":
            # 优先用 completed（已完成数）保证并发上传时进度单调；fall back partNumber 兼容旧路径
            completed = int(event.get("completed") or event.get("partNumber") or 0)
            total_parts = int(event.get("totalParts") or 0)
            if total_parts <= 0:
                return
            percent = max(1, round(completed * 100 / total_parts))
            bucket = min(10, percent // 10)
            should_log = completed == 1 or completed == total_parts or bucket > last_bucket
            if should_log:
                last_bucket = bucket
                log(f"upload progress: {completed}/{total_parts} ({percent}%)")
        elif event_type == "multipart-complete":
            log("multipart upload completed")

    return handle_event

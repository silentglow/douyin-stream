from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from media_tools.logger import get_logger

from .errors import TranscribeError, TranscribeErrorClassifier, TranscribePollTimeoutError

logger = get_logger(__name__)

DEFAULT_TRANSCRIBE_POLL_TIMEOUT_SECONDS = 6 * 60 * 60
DEFAULT_RESUME_RECORD_MISSING_TIMEOUT_SECONDS = 2 * 60

from media_tools.accounts.auth_state import resolve_qwen_cookie_string
from media_tools.accounts.quota import get_quota_snapshot, record_quota_consumption
from media_tools.common.http import RequestsApiContext, api_json, download_file
from media_tools.common.runtime import ExportConfig, ensure_dir, guess_mime_type, now_stamp

from .config import load_config
from .export_utils import _get_video_title_from_db, build_export_output_path, save_debug_artifacts
from .upload.oss_upload import upload_file_to_oss


@dataclass(frozen=True)
class FlowResult:
    record_id: str
    gen_record_id: str
    export_path: Path
    remote_deleted: bool


@dataclass(frozen=True)
class ResumeState:
    stage: str = "queued"
    record_id: str | None = None
    gen_record_id: str | None = None
    batch_id: str | None = None
    export_url: str | None = None


def build_upload_tag(file_path: str | Path, mime_type: str) -> dict[str, Any]:
    parsed = Path(file_path)
    is_video = 1 if mime_type.startswith("video/") else 0
    return {
        "showName": parsed.stem,
        "fileFormat": parsed.suffix.removeprefix("."),
        "fileType": "local",
        "lang": "cn",
        "roleSplitNum": 0,
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


async def poll_until_done(
    context: Any,
    gen_record_id: str,
    timeout_seconds: float = DEFAULT_TRANSCRIBE_POLL_TIMEOUT_SECONDS,
    on_progress: Callable[[str], None] | None = None,
    missing_timeout_seconds: float | None = None,
) -> dict[str, Any]:
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
        import random

        loop_start = time.monotonic()
        last_report = 0.0
        missing_started_at: float | None = None
        report_interval = 45.0  # 轮询每 5–7s 一次，但上报节流到 ~45s，避免 DB/广播风暴
        while True:
            response = await api_json(context, url, payload)
            data = response.get("data") or {}
            found_record = False
            for batch in data.get("batchRecord", []):
                for record in batch.get("recordList", []):
                    if record.get("genRecordId") == gen_record_id:
                        found_record = True
                        missing_started_at = None
                        status = record.get("recordStatus")
                        if status == 30:
                            return record
                        if status in (40, 41):
                            fail_reason = (
                                record.get("failReason") or record.get("errorMessage") or f"recordStatus={status}"
                            )
                            error_info = TranscribeErrorClassifier.classify(fail_reason)
                            logger.error(
                                f"转写错误 [{error_info.error_code}]: {error_info.message} - {error_info.suggestion}"
                            )
                            raise TranscribeError(error_info, detail=fail_reason)
            if not found_record and missing_timeout_seconds is not None:
                now = time.monotonic()
                if missing_started_at is None:
                    missing_started_at = now
                if now - missing_started_at >= missing_timeout_seconds:
                    error_info = TranscribeErrorClassifier.classify("record not found")
                    raise TranscribeError(
                        error_info,
                        detail=f"转写记录不存在或已被删除 gen_record_id={gen_record_id}",
                    )
            # 轮询心跳：把「已等待多久」节流上报给 UI，让进度不再僵在笼统文案。
            if on_progress is not None:
                elapsed = time.monotonic() - loop_start
                if elapsed - last_report >= report_interval:
                    last_report = elapsed
                    minutes = int(elapsed // 60)
                    waited = f"已等待 {minutes} 分钟…" if minutes >= 1 else "排队等待中…"
                    try:
                        on_progress(f"云端转写中，{waited}")
                    except Exception:  # noqa: BLE001  上报失败不影响轮询
                        logger.debug("poll on_progress 回调异常", exc_info=True)
            await asyncio.sleep(5 + random.uniform(0, 2))

    try:
        return await asyncio.wait_for(_poll_loop(), timeout=timeout_seconds)
    except TimeoutError:
        error_info = TranscribeErrorClassifier.classify("timeout")
        raise TranscribePollTimeoutError(error_info, detail=f"转写轮询超时 ({timeout_seconds}s)")


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
    file_path: str | Path,
    auth_state_path: str | Path,
    download_dir: str | Path,
    export_config: ExportConfig,
    should_delete: bool = False,
    account_id: str = "",
    cookie_string: str = "",
    account_upload_lock: asyncio.Lock | None = None,
    title: str | None = None,
    shared_api: Any | None = None,
    run_id: str | None = None,
    resume_state: ResumeState | None = None,
    on_stage: Callable[[str], None] | None = None,
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

    def _stage(message: str) -> None:
        """把阶段文案推给进度回调（UI 实时显示）；回调异常不影响主流程。"""
        if on_stage is not None:
            try:
                on_stage(message)
            except Exception:  # noqa: BLE001
                logger.debug("on_stage 回调异常", exc_info=True)

    def _checkpoint(stage: str, extra: dict[str, Any] | None = None) -> bool:
        if not run_id:
            return False
        try:
            from media_tools.transcribe.repository import TranscribeRunRepository

            TranscribeRunRepository.update_stage(run_id, stage, extra)
            return True
        except (sqlite3.Error, OSError) as exc:
            logger.warning(f"transcribe_runs 打卡失败 (run_id={run_id}, stage={stage}): {exc}")
            return False

    def _poll_timeout_seconds() -> float:
        return float(
            getattr(
                load_config(),
                "transcribe_poll_timeout_seconds",
                DEFAULT_TRANSCRIBE_POLL_TIMEOUT_SECONDS,
            )
        )

    async def _safe_cleanup_old_record(api: Any, old_record_id: str | None) -> None:
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

    async def _safe_cleanup_failed_record(api: Any, record_id: str) -> bool:
        """_do_flow 失败兜底：清掉云端孤儿 recordId。
        和 _safe_cleanup_old_record 的区别：本函数在异常处理路径调用，对任何异常都吞掉
        (包括 CancelledError)，避免在外层 cancel 时把原始异常掩盖。"""
        try:
            ok = await delete_record(api, [record_id])
            if ok:
                log(f"失败兜底：已清理云端孤儿 record_id={record_id}")
                return True
            else:
                logger.warning(f"失败兜底清理云端记录返回失败 record_id={record_id}")
        except BaseException as exc:
            logger.warning(f"失败兜底清理云端记录异常 record_id={record_id}: {exc}")
        return False

    def _clear_deleted_remote_checkpoint() -> None:
        if not run_id:
            return
        try:
            from media_tools.transcribe.repository import TranscribeRunRepository

            TranscribeRunRepository.clear_remote_checkpoint(run_id)
        except (sqlite3.Error, OSError) as exc:
            logger.warning(f"清理本地远端断点失败 (run_id={run_id}): {exc}")

    def _should_preserve_failed_remote_record(exc: BaseException) -> bool:
        if isinstance(exc, TranscribeError):
            error_code = (exc.error_info.error_code or "").upper()
            if error_code in {"SERVICE_UNAVAILABLE", "UNSUPPORTED_FORMAT"}:
                return False
        return True

    async def _do_flow(api: Any) -> FlowResult:
        remote_checkpoint_persisted = False
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

        # 拿到 recordId 后，如果还没把断点写入 transcribe_runs，失败时需要清理远端记录，
        # 否则千问账号"记录"列表会越积越多。断点已持久化后则优先保留给下一次续传。
        # 历史教训 v2026-05-26：5 文件 OSS 上传超时后，20 个 recordId 全部留在账号端。
        try:
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
                        on_progress=_make_upload_progress_logger(log, _stage),
                    )

            await api_json(
                api,
                "https://api.qianwen.com/assistant/api/record/upload_heartbeat?c=tongyi-web",
                {"genRecordId": token["genRecordId"]},
            )
            log("upload heartbeat sent")

            remote_checkpoint_persisted = _checkpoint(
                "uploaded",
                {
                    "record_id": token["recordId"],
                    "gen_record_id": token["genRecordId"],
                },
            )

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

            remote_checkpoint_persisted = (
                _checkpoint("transcribing", {"batch_id": batch_id}) or remote_checkpoint_persisted
            )
            _stage("已提交云端，等待转写…")

            completed_record = await poll_until_done(
                api,
                token["genRecordId"],
                timeout_seconds=_poll_timeout_seconds(),
                on_progress=_stage,
            )
            log(f"record completed with status={completed_record.get('recordStatus', 'unknown')}")

            await api_json(
                api,
                "https://api.qianwen.com/assistant/api/record/read?c=tongyi-web",
                {"recordIds": [token["recordId"]]},
            )

            remote_checkpoint_persisted = _checkpoint("exporting") or remote_checkpoint_persisted
            _stage("导出字幕中…")

            export_url = await export_file(api, token["genRecordId"], export_config)

            remote_checkpoint_persisted = (
                _checkpoint("downloading", {"export_url": export_url}) or remote_checkpoint_persisted
            )
            _stage("下载结果中…")

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
        except TranscribePollTimeoutError:
            log(
                f"转写仍在处理中，保留云端记录以便下次续传 "
                f"record_id={token.get('recordId')} gen_record_id={token.get('genRecordId')}"
            )
            raise
        except BaseException as exc:
            # 兜底清理：尚未持久化断点的失败记录没有可恢复路径，应清掉。
            # 已写入 transcribe_runs 的远端记录在普通网络/导出/下载失败后保留，
            # 让下一次重试复用 gen_record_id，避免把可续传记录误删后继续空轮询。
            # shield 防止外层 cancel 把 cleanup 也打断；任何 cleanup 异常都吞掉，避免掩盖原始异常。
            orphan_record_id = token.get("recordId")
            if orphan_record_id:
                if remote_checkpoint_persisted and _should_preserve_failed_remote_record(exc):
                    log(
                        f"失败后保留云端记录以便下次续传 "
                        f"record_id={token.get('recordId')} gen_record_id={token.get('genRecordId')}"
                    )
                else:
                    try:
                        cleanup_ok = await asyncio.shield(_safe_cleanup_failed_record(api, orphan_record_id))
                        if cleanup_ok:
                            _clear_deleted_remote_checkpoint()
                    except BaseException:
                        logger.debug(
                            f"failure-path cleanup orphan recordId={orphan_record_id} 异常忽略",
                            exc_info=True,
                        )
            raise

    async def _try_resume_export_only(api: Any) -> FlowResult | None:
        if resume_state is None or not resume_state.export_url:
            return None
        # record_id 缺失时无法回退清理，直接走完整 flow 避免孤儿记录
        if not resume_state.record_id:
            logger.warning(
                f"resume[export_url] 跳过：record_id 缺失，无法回退清理，gen_record_id={resume_state.gen_record_id}"
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
                except Exception:  # noqa: BLE001
                    logger.warning("重置 stage 失败，但不影响 fallback 流程", exc_info=True)
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
            _stage("续传：等待云端转写…")

            completed_record = await poll_until_done(
                api,
                resume_state.gen_record_id,
                timeout_seconds=_poll_timeout_seconds(),
                on_progress=_stage,
                missing_timeout_seconds=DEFAULT_RESUME_RECORD_MISSING_TIMEOUT_SECONDS,
            )
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
            _stage("导出字幕中…")

            export_url = await export_file(api, resume_state.gen_record_id, export_config)

            _checkpoint("downloading", {"export_url": export_url})
            _stage("下载结果中…")

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
        except TranscribePollTimeoutError as exc:
            logger.warning(f"resume[gen_record_id] 轮询超时，保留旧记录等待下次续传: {exc}")
            _checkpoint(
                "transcribing",
                {
                    "record_id": resume_state.record_id,
                    "gen_record_id": resume_state.gen_record_id,
                    "batch_id": resume_state.batch_id,
                },
            )
            raise
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
                except Exception:  # noqa: BLE001
                    logger.warning("重置 stage 失败，但不影响 fallback 流程", exc_info=True)
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


def _make_upload_progress_logger(log, on_stage: Callable[[str], None] | None = None):
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
                if on_stage is not None:
                    on_stage(f"上传中 {percent}%")
        elif event_type == "multipart-complete":
            log("multipart upload completed")

    return handle_event

import asyncio
import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, HTTPException
from typing import Any
import uuid

from media_tools.api.schemas import (
    PipelineRequest,
    BatchPipelineRequest,
    DownloadBatchRequest,
    CreatorDownloadRequest,
    FullSyncRequest,
    LocalTranscribeRequest,
    CreatorTranscribeRequest,
    ScanDirectoryRequest,
    RecoverAwemeTranscribeRequest,
    CreatorTranscribeCleanupRetryRequest,
    RetryFailedAssetsRequest,
)
from media_tools.workers.task_dispatcher import (
    _start_task_worker,
    _retry_task_worker,
    dispatch_new_task,
)
from media_tools.douyin.core.cancel_registry import set_cancel_event, clear_cancel_event, clear_download_progress
from media_tools.common.paths import get_download_path, get_project_root
from media_tools.db.core import get_db_connection
from media_tools.repositories.task_repository import TaskRepository
from media_tools.core.config import get_runtime_setting_bool

# WebSocket
from media_tools.api.websocket_manager import websocket_endpoint, manager

# Task operations
from media_tools.services.task_ops import (
    cleanup_stale_tasks,
    _mark_task_cancelled,
)
from media_tools.services.task_state import (
    _active_tasks,
)
from media_tools.services.pipeline_progress import build_pipeline_progress
from media_tools.services.transcript_reconciler import reconcile_transcripts
from media_tools.services.file_browser import select_folder, scan_directory
from media_tools.services.cleanup import cleanup_paths_allowlist

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"], redirect_slashes=False)
logger = logging.getLogger(__name__)


router.websocket("/ws")(websocket_endpoint)


@router.post("/pipeline")
async def trigger_pipeline(req: PipelineRequest):
    task_id = str(uuid.uuid4())
    return await dispatch_new_task(task_id, "pipeline", {
        "url": req.url,
        "max_counts": req.max_counts,
        "auto_delete": req.auto_delete,
    })


@router.get("/active")
def get_active_tasks():
    try:
        return TaskRepository.find_active()
    except sqlite3.Error:
        logger.exception("get_active_tasks failed")
        raise HTTPException(status_code=500, detail="获取活跃任务失败")


def _enrich_task_with_pipeline_progress(task: dict[str, Any]) -> None:
    payload_raw = task.get("payload")
    payload: dict[str, Any] = {}
    if isinstance(payload_raw, str) and payload_raw:
        try:
            parsed = json.loads(payload_raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            parsed = {}
        if isinstance(parsed, dict):
            payload = parsed

    pipeline_progress = build_pipeline_progress(
        str(task.get("task_type") or ""),
        str(task.get("status") or ""),
        task.get("progress"),
        payload,
    )
    if pipeline_progress:
        payload["pipeline_progress"] = pipeline_progress
        task["payload"] = json.dumps(payload, ensure_ascii=False)


@router.get("/history")
def get_task_history():
    try:
        tasks = TaskRepository.list_recent(200)
        for task in tasks:
            _enrich_task_with_pipeline_progress(task)
        return tasks
    except sqlite3.Error:
        logger.exception("get_task_history failed")
        raise HTTPException(status_code=500, detail="获取任务历史失败")


@router.delete("/history")
def clear_task_history():
    try:
        active_task_ids = set(_active_tasks.keys())
        deleted_task_ids = TaskRepository.delete_all_except(active_task_ids)
        for task_id in deleted_task_ids:
            clear_cancel_event(task_id)
            clear_download_progress(task_id)
        return {"status": "success", "message": "历史任务已清除"}
    except (sqlite3.Error, OSError) as e:
        logger.exception("clear_task_history failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear")
def clear_task_history_compat():
    return clear_task_history()


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    try:
        active_task = _active_tasks.pop(task_id, None)
        if active_task is not None:
            set_cancel_event(task_id)
            try:
                from media_tools.bilibili.core.downloader import cancel_download
                cancel_download(task_id)
            except (RuntimeError, OSError, ImportError):
                pass
            active_task.cancel()
            try:
                # 与 cancel_task 一致用 5s 超时，避免任务在不可中断 await 上时端点阻塞
                await asyncio.wait_for(active_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        clear_cancel_event(task_id)
        TaskRepository.delete(task_id)
        return {"status": "success", "message": "任务已删除"}
    except (sqlite3.Error, OSError) as e:
        logger.exception(f"delete_task failed for {task_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}")
def get_task_status(task_id: str):
    try:
        task = TaskRepository.find_by_id(task_id)
        if task:
            _enrich_task_with_pipeline_progress(task)
            return task
        raise HTTPException(status_code=404, detail="任务不存在")
    except sqlite3.Error:
        logger.exception("get_task_status failed")
        raise HTTPException(status_code=500, detail="获取任务状态失败")


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    try:
        status, task_type = TaskRepository.get_status(task_id)
        if not status:
            raise HTTPException(status_code=404, detail="任务不存在")
        if status in ("COMPLETED", "FAILED", "CANCELLED"):
            raise HTTPException(status_code=409, detail=f"任务已处于 {status} 状态，无法取消")

        try:
            from media_tools.bilibili.core.downloader import cancel_download
            cancel_download(task_id)
        except (RuntimeError, OSError, ImportError):
            pass

        set_cancel_event(task_id)

        active_task = _active_tasks.pop(task_id, None)
        if active_task is not None:
            active_task.cancel()
            try:
                await asyncio.wait_for(active_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            await _mark_task_cancelled(task_id, task_type)
            return {"status": "success", "message": "Task cancelled"}
        else:
            await _mark_task_cancelled(task_id, task_type)
            return {"status": "success", "message": "Task marked as cancelled (was not running)"}
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, RuntimeError, asyncio.CancelledError) as e:
        logger.exception(f"cancel_task failed for {task_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/auto-retry")
async def set_auto_retry(task_id: str, enabled: bool = True):
    try:
        TaskRepository.set_auto_retry(task_id, enabled)
        return {"status": "success", "message": f"自动重试已{'启用' if enabled else '禁用'}"}
    except (sqlite3.Error, OSError, RuntimeError) as e:
        logger.exception(f"set_auto_retry failed for {task_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/pause")
async def pause_task(task_id: str):
    raise HTTPException(status_code=501, detail="暂停/恢复功能已下线")


@router.put("/{task_id}/priority")
async def update_task_priority(task_id: str, priority: int):
    try:
        TaskRepository.update_priority(task_id, priority)
        
        await manager.broadcast({
            "type": "task_priority_change",
            "payload": {
                "task_id": task_id,
                "priority": priority,
            },
        })
        
        return {"status": "success", "message": "任务优先级已更新"}
    except (sqlite3.Error, OSError, RuntimeError) as e:
        logger.exception(f"update_task_priority failed for {task_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/resume")
async def resume_task(task_id: str):
    raise HTTPException(status_code=501, detail="暂停/恢复功能已下线")


@router.post("/{task_id}/rerun")
async def rerun_task(task_id: str):
    try:
        task = TaskRepository.find_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        task_type, payload_str, current_status = TaskRepository.get_task_type_payload_status(task_id)

        if current_status not in ("FAILED", "CANCELLED", "PAUSED"):
            raise HTTPException(status_code=409, detail=f"当前状态 {current_status} 不能重新运行")

        try:
            original_params = json.loads(payload_str) if payload_str else {}
        except (json.JSONDecodeError, TypeError):
            original_params = {}
        original_params.pop("msg", None)
        original_params.pop("result_summary", None)
        original_params.pop("subtasks", None)
        original_params["_resumed"] = True

        TaskRepository.mark_running(task_id, 0.0)
        return await _start_task_worker(task_id, task_type, original_params)

    except HTTPException:
        raise
    except (sqlite3.Error, OSError, RuntimeError, asyncio.CancelledError) as e:
        logger.exception(f"rerun_task failed for {task_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/retry")
async def retry_task(task_id: str):
    try:
        task_type, payload_str = TaskRepository.get_task_type_and_payload(task_id)
        if not task_type:
            raise HTTPException(status_code=404, detail="任务不存在")

        try:
            original_params = json.loads(payload_str) if payload_str else {}
        except (json.JSONDecodeError, TypeError):
            original_params = {}

        return await _retry_task_worker(task_id, task_type, original_params)

    except HTTPException:
        raise
    except (sqlite3.Error, OSError, RuntimeError, asyncio.CancelledError) as e:
        logger.exception(f"retry_task failed for {task_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/retry-failed")
async def retry_failed_subtasks(task_id: str):
    try:
        task = TaskRepository.find_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        try:
            payload = json.loads(task.get("payload") or "{}")
        except (json.JSONDecodeError, TypeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        failed_paths: list[str] = []
        for item in payload.get("subtasks") or []:
            if not isinstance(item, dict) or item.get("status") != "failed":
                continue
            path = item.get("video_path") or item.get("file_path")
            if isinstance(path, str) and path.strip() and Path(path).exists():
                failed_paths.append(path.strip())

        failed_paths = list(dict.fromkeys(failed_paths))
        if not failed_paths:
            raise HTTPException(status_code=409, detail="没有可重试的失败视频路径")

        delete_after = bool(payload.get("delete_after", get_runtime_setting_bool("auto_delete", True)))
        directory_root = payload.get("directory_root") if isinstance(payload.get("directory_root"), str) else None
        new_task_id = str(uuid.uuid4())
        result = await dispatch_new_task(new_task_id, "local_transcribe", {
            "file_paths": failed_paths,
            "delete_after": delete_after,
            "directory_root": directory_root,
            "retry_failed_from_task_id": task_id,
        })
        result["file_count"] = len(failed_paths)
        return result

    except HTTPException:
        raise
    except (sqlite3.Error, OSError, RuntimeError, asyncio.CancelledError) as e:
        logger.exception(f"retry_failed_subtasks failed for {task_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transcribe/retry-failed-assets")
async def retry_failed_assets(req: RetryFailedAssetsRequest):
    """从 media_assets 真相源派发重试：按 creator/platform/error_type 过滤。

    与旧的 /tasks/{id}/retry-failed 区别：
      - 不依赖某个历史 task 的 payload.subtasks
      - 跨任务、跨时间都能聚合——"这个创作者所有失败的"、"所有 quota 错误的"
    """
    try:
        from media_tools.services.media_asset_service import MediaAssetService

        limit = req.limit or 1000
        rows = MediaAssetService.find_pending_to_transcribe(
            creator_uid=req.creator_uid,
            platform=req.platform,
            error_types=req.error_types,
            only_failed=True,
            limit=limit,
        )

        downloads = get_download_path()
        file_paths: list[str] = []
        asset_ids: list[str] = []
        missing: list[str] = []
        for row in rows:
            vp = (row.get("video_path") or "").strip()
            if not vp:
                continue
            candidate = Path(vp)
            if not candidate.is_absolute():
                candidate = (downloads / vp).resolve()
            if candidate.exists() and candidate.is_file():
                file_paths.append(str(candidate))
                asset_ids.append(row["asset_id"])
            else:
                missing.append(row["asset_id"])

        if not file_paths:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "没有可重试的失败视频（DB 标记为 failed 但磁盘上找不到对应文件）",
                    "failed_in_db": len(rows),
                    "missing_file_assets": missing[:50],
                },
            )

        file_paths = list(dict.fromkeys(file_paths))
        delete_after = bool(
            req.delete_after if req.delete_after is not None
            else get_runtime_setting_bool("auto_delete", True)
        )
        new_task_id = str(uuid.uuid4())

        # 提前把新 task_id 记到 asset 上，让界面能看到"这批失败正在被哪个任务处理"
        for aid in asset_ids:
            try:
                MediaAssetService.mark_transcribe_running(aid, task_id=new_task_id)
            except Exception:  # noqa: BLE001  记录失败不阻塞主流程
                logger.warning(f"mark_transcribe_running({aid}) failed", exc_info=True)

        result = await dispatch_new_task(new_task_id, "local_transcribe", {
            "file_paths": file_paths,
            "delete_after": delete_after,
            "directory_root": None,
            "retry_failed_assets": {
                "creator_uid": req.creator_uid,
                "platform": req.platform,
                "error_types": req.error_types,
                "asset_ids": asset_ids,
            },
        })
        return {
            "task_id": new_task_id,
            "status": "started",
            "file_count": len(file_paths),
            "missing_file_assets": missing,
        }
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, RuntimeError, asyncio.CancelledError) as e:
        logger.exception("retry_failed_assets failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/batch")
async def trigger_batch_pipeline(req: BatchPipelineRequest):
    task_id = str(uuid.uuid4())
    return await dispatch_new_task(task_id, "pipeline", {
        "video_urls": req.video_urls,
        "auto_delete": req.auto_delete,
    })


@router.post("/download/batch")
async def trigger_download_batch(req: DownloadBatchRequest):
    task_id = str(uuid.uuid4())
    return await dispatch_new_task(task_id, "download", {
        "video_urls": req.video_urls,
    })


@router.post("/download/creator")
async def trigger_creator_download(req: CreatorDownloadRequest):
    task_id = str(uuid.uuid4())
    return await dispatch_new_task(task_id, f"creator_sync_{req.mode}", {
        "uid": req.uid,
        "mode": req.mode,
        "batch_size": req.batch_size,
    })


@router.post("/download/full-sync")
async def trigger_full_sync(req: FullSyncRequest):
    task_id = str(uuid.uuid4())
    return await dispatch_new_task(task_id, f"full_sync_{req.mode}", {
        "mode": req.mode,
        "batch_size": req.batch_size,
    })


@router.post("/transcribe/local")
async def trigger_local_transcribe(req: LocalTranscribeRequest):
    task_id = str(uuid.uuid4())
    delete_after = req.delete_after if req.delete_after is not None else False
    return await dispatch_new_task(task_id, "local_transcribe", {
        "file_paths": req.file_paths,
        "delete_after": delete_after,
        "directory_root": req.directory_root,
    })


@router.post("/transcribe/creator")
async def trigger_creator_transcribe(req: CreatorTranscribeRequest):
    task_id = str(uuid.uuid4())
    result = await dispatch_new_task(task_id, "creator_transcribe", {
        "file_paths": [],
        "delete_after": req.delete_after,
        "directory_root": None,
        "creator_uid": req.uid,
    })
    file_count = 0
    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                """SELECT COUNT(1)
                   FROM media_assets
                   WHERE creator_uid = ?
                     AND video_status IN ('downloaded', 'pending')
                     AND transcript_status IN ('pending', 'none', 'failed')""",
                (req.uid,),
            )
            row = cursor.fetchone()
            if row:
                file_count = int(row[0] or 0)
    except (sqlite3.Error, OSError, ValueError):
        file_count = 0

    result["file_count"] = file_count
    return result


@router.post("/transcribe/creator/cleanup-retry")
def retry_creator_transcribe_cleanup(req: CreatorTranscribeCleanupRetryRequest):
    try:
        task = TaskRepository.find_by_id(req.task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        payload_raw = task.get("payload")
        payload: dict[str, Any] = {}
        if isinstance(payload_raw, str) and payload_raw:
            try:
                parsed = json.loads(payload_raw)
            except (json.JSONDecodeError, TypeError, ValueError):
                parsed = {}
            if isinstance(parsed, dict):
                payload = parsed

        raw_failed = payload.get("cleanup_failed_paths")
        failed_paths: list[Path] = []
        if isinstance(raw_failed, list):
            for item in raw_failed:
                if isinstance(item, str) and item:
                    failed_paths.append(Path(item))
                    continue
                if isinstance(item, dict):
                    path_value = item.get("path")
                    if isinstance(path_value, str) and path_value:
                        failed_paths.append(Path(path_value))

        if not failed_paths:
            TaskRepository.patch_payload(
                req.task_id,
                {
                    "cleanup_failed_count": 0,
                    "cleanup_failed_paths": [],
                    "cleanup_retry_at": datetime.now().isoformat(),
                },
            )
            return {
                "task_id": req.task_id,
                "deleted_count": 0,
                "failed_count": 0,
                "failed_paths": [],
                "total_deleted_count": int(payload.get("cleanup_deleted_count") or 0),
            }

        downloads_root = get_download_path()
        transcripts_root = get_project_root() / "transcripts"
        outcome = cleanup_paths_allowlist(
            failed_paths,
            downloads_root=downloads_root,
            transcripts_root=transcripts_root,
        )

        remaining_failed = [fp for fp in outcome.failed_paths if fp.reason != "not_found"]
        previous_deleted = int(payload.get("cleanup_deleted_count") or 0)
        total_deleted = previous_deleted + int(outcome.deleted_count or 0)

        failed_payload = [{"path": fp.path, "reason": fp.reason} for fp in remaining_failed]
        TaskRepository.patch_payload(
            req.task_id,
            {
                "cleanup_deleted_count": total_deleted,
                "cleanup_failed_count": len(failed_payload),
                "cleanup_failed_paths": failed_payload,
                "cleanup_retry_at": datetime.now().isoformat(),
            },
        )

        return {
            "task_id": req.task_id,
            "deleted_count": outcome.deleted_count,
            "failed_count": len(failed_payload),
            "failed_paths": failed_payload,
            "total_deleted_count": total_deleted,
        }
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, ValueError, TypeError) as e:
        logger.exception("retry_creator_transcribe_cleanup failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recover/aweme")
async def trigger_recover_aweme_transcribe(req: RecoverAwemeTranscribeRequest):
    task_id = str(uuid.uuid4())
    return await dispatch_new_task(task_id, "recover_aweme_transcribe", {
        "creator_uid": req.creator_uid,
        "aweme_id": req.aweme_id,
        "title": req.title,
    })


@router.post("/transcribe/select-folder")
def _select_folder():
    return select_folder()


@router.post("/transcribe/scan")
def _scan_directory(req: ScanDirectoryRequest):
    return scan_directory(req.directory)


@router.post("/reconcile-transcripts")
def _reconcile_transcripts():
    try:
        return reconcile_transcripts()
    except (OSError, RuntimeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))

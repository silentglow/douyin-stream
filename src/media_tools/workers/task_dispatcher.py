from typing import Any, Optional, Callable
import uuid

from fastapi import HTTPException

from media_tools.api.schemas import (
    PipelineRequest,
    BatchPipelineRequest,
    DownloadBatchRequest,
    LocalTranscribeRequest,
)
from media_tools.repositories.task_repository import TaskRepository
from media_tools.scheduler.ops import notify_task_update
from media_tools.scheduler.state import _register_background_task
from media_tools.services.local_asset_service import _register_local_assets
from media_tools.workers.pipeline_worker import PipelineWorker, DownloadWorker
from media_tools.workers.full_sync_worker import FullSyncWorker
from media_tools.workers.local_transcribe_worker import LocalTranscribeWorker
from media_tools.workers.creator_transcribe_worker import CreatorTranscribeWorker
from media_tools.workers.aweme_recover_worker import AwemeRecoverWorker
from media_tools.workers.creator_sync import CreatorSyncWorker


async def _create_task(task_id: str, task_type: str, request_params: dict):
    msg = "任务已启动，准备执行..."
    payload = {**request_params, "msg": msg}
    TaskRepository.create_running(task_id, task_type, payload)
    await notify_task_update(task_id, 0.0, msg, "RUNNING", task_type)


class _WorkerDispatch:
    """任务分发器注册项。

    把 task_dispatcher 中重复的 if/elif 分支提取为声明式配置，
    _start_task_worker 和 _retry_task_worker 共享同一套匹配规则。
    """

    def __init__(
        self,
        *,
        match: Callable[[str, dict[str, Any]], bool],
        build_request: Callable[[dict[str, Any]], Any],
        build_worker: Callable[[str, Any, dict[str, Any]], Any],
        retry_task_type: Optional[Callable[[Any], str]] = None,
        retry_params: Callable[[Any, dict[str, Any]], dict[str, Any]],
        needs_register_local_assets: bool = False,
        start_message: str = "Task started",
        retry_message: str = "Task retry started",
    ):
        self.match = match
        self.build_request = build_request
        self.build_worker = build_worker
        self.retry_task_type = retry_task_type
        self.retry_params = retry_params
        self.needs_register_local_assets = needs_register_local_assets
        self.start_message = start_message
        self.retry_message = retry_message


# ------------------------------------------------------------------
# Registry: 按匹配优先级排列（更具体的条件在前）
# ------------------------------------------------------------------
_WORKER_DISPATCHERS: list[_WorkerDispatch] = [
    # 1. Pipeline 单链接
    _WorkerDispatch(
        match=lambda t, p: t == "pipeline" and "url" in p,
        build_request=lambda p: PipelineRequest(
            url=p.get("url", ""),
            max_counts=p.get("max_counts", 5),
            auto_delete=p.get("auto_delete", True),
        ),
        build_worker=lambda task_id, req, _: PipelineWorker().execute(task_id, req=req),
        retry_params=lambda req, _: {
            "url": req.url,
            "max_counts": req.max_counts,
            "auto_delete": req.auto_delete,
        },
        start_message="Pipeline task rerun",
        retry_message="Pipeline task retry started",
    ),
    # 2. Pipeline 批量
    _WorkerDispatch(
        match=lambda t, p: t == "pipeline" and "video_urls" in p,
        build_request=lambda p: BatchPipelineRequest(
            video_urls=p.get("video_urls", []),
            auto_delete=p.get("auto_delete", True),
        ),
        build_worker=lambda task_id, req, _: PipelineWorker().execute(task_id, req=req),
        retry_params=lambda req, _: {
            "video_urls": req.video_urls,
            "auto_delete": req.auto_delete,
        },
        start_message="Batch pipeline task rerun",
        retry_message="Batch pipeline task retry started",
    ),
    # 3. 纯下载
    _WorkerDispatch(
        match=lambda t, p: t == "download" and "video_urls" in p,
        build_request=lambda p: DownloadBatchRequest(
            video_urls=p.get("video_urls", []),
        ),
        build_worker=lambda task_id, req, _: DownloadWorker().execute(task_id, req=req),
        retry_params=lambda req, _: {"video_urls": req.video_urls},
        start_message="Download task rerun",
        retry_message="Download task retry started",
    ),
    # 4. 创作者同步
    _WorkerDispatch(
        match=lambda t, p: t.startswith("creator_sync") and "uid" in p,
        build_request=lambda p: {
            "uid": str(p.get("uid", "")),
            "mode": str(p.get("mode", "incremental")),
            "batch_size": p.get("batch_size"),
        },
        build_worker=lambda task_id, req, orig: CreatorSyncWorker().execute(
            task_id, uid=req["uid"], mode=req["mode"], batch_size=req["batch_size"], original_params=orig
        ),
        retry_task_type=lambda req: f"creator_sync_{req['mode']}",
        retry_params=lambda req, _: {
            "uid": req["uid"],
            "mode": req["mode"],
            "batch_size": req["batch_size"],
        },
        start_message="Creator sync task rerun",
        retry_message="Creator download task retry started",
    ),
    # 5. 全量同步
    _WorkerDispatch(
        match=lambda t, p: t.startswith("full_sync") and "mode" in p,
        build_request=lambda p: {
            "mode": str(p.get("mode", "incremental")),
            "batch_size": p.get("batch_size"),
        },
        build_worker=lambda task_id, req, orig: FullSyncWorker().execute(
            task_id, mode=req["mode"], batch_size=req["batch_size"], original_params=orig
        ),
        retry_task_type=lambda req: f"full_sync_{req['mode']}",
        retry_params=lambda req, _: {
            "mode": req["mode"],
            "batch_size": req["batch_size"],
        },
        start_message="Full sync task rerun",
        retry_message="Full sync task retry started",
    ),
    # 6. 创作者转写
    _WorkerDispatch(
        match=lambda t, p: t == "creator_transcribe",
        build_request=lambda p: {
            "uid": str(p.get("creator_uid", "")),
            "delete_after": p.get("delete_after"),
        },
        build_worker=lambda task_id, req, _: CreatorTranscribeWorker().execute(
            task_id, uid=req["uid"], delete_after=req["delete_after"]
        ),
        retry_params=lambda req, _: {
            "uid": req["uid"],
            "delete_after": req["delete_after"],
        },
        start_message="Creator transcribe task started",
        retry_message="Creator transcribe task retry started",
    ),
    # 7. 本地转写（直接指定 file_paths）
    _WorkerDispatch(
        match=lambda t, p: t == "local_transcribe" and "file_paths" in p,
        build_request=lambda p: LocalTranscribeRequest(
            file_paths=p.get("file_paths", []),
            delete_after=p.get("delete_after", False),
            directory_root=p.get("directory_root"),
        ),
        build_worker=lambda task_id, req, _: LocalTranscribeWorker().execute(task_id, req=req),
        retry_params=lambda req, _: {
            "file_paths": req.file_paths,
            "delete_after": req.delete_after,
            "directory_root": req.directory_root,
        },
        needs_register_local_assets=True,
        start_message="Local transcribe task rerun",
        retry_message="Local transcribe task retry started",
    ),
    # 7. 补齐单视频
    _WorkerDispatch(
        match=lambda t, p: t == "recover_aweme_transcribe",
        build_request=lambda p: {
            "creator_uid": str(p.get("creator_uid", "")),
            "aweme_id": str(p.get("aweme_id", "")),
            "title": str(p.get("title", "")),
        },
        build_worker=lambda task_id, req, _: AwemeRecoverWorker().execute(
            task_id, creator_uid=req["creator_uid"], aweme_id=req["aweme_id"], title=req["title"]
        ),
        retry_params=lambda req, _: {
            "creator_uid": req["creator_uid"],
            "aweme_id": req["aweme_id"],
            "title": req["title"],
        },
        start_message="Aweme recover task rerun",
        retry_message="Aweme recover task retry started",
    ),
]


async def _start_task_worker(task_id: str, task_type: str, original_params: dict[str, Any]):
    for entry in _WORKER_DISPATCHERS:
        if entry.match(task_type, original_params):
            req = entry.build_request(original_params)
            if entry.needs_register_local_assets:
                _register_local_assets(
                    req.file_paths, req.delete_after, req.directory_root
                )
            _register_background_task(
                task_id, entry.build_worker(task_id, req, original_params)
            )
            return {
                "task_id": task_id,
                "status": "started",
                "message": entry.start_message,
            }
    raise HTTPException(status_code=400, detail=f"Unsupported task type: {task_type}")


async def dispatch_new_task(task_id: str, task_type: str, params: dict[str, Any]):
    """创建新任务（写入 DB）并启动对应 Worker。"""
    await _create_task(task_id, task_type, params)
    return await _start_task_worker(task_id, task_type, params)


async def _retry_task_worker(task_id: str, task_type: str, original_params: dict[str, Any]):
    """创建新任务并重试原任务逻辑。"""
    original_params.pop("msg", None)

    for entry in _WORKER_DISPATCHERS:
        if entry.match(task_type, original_params):
            req = entry.build_request(original_params)
            new_task_id = str(uuid.uuid4())
            new_task_type = (
                entry.retry_task_type(req)
                if entry.retry_task_type
                else task_type
            )
            await _create_task(
                new_task_id,
                new_task_type,
                entry.retry_params(req, original_params),
            )
            if entry.needs_register_local_assets:
                _register_local_assets(
                    req.file_paths, req.delete_after, req.directory_root
                )
            _register_background_task(
                new_task_id,
                entry.build_worker(new_task_id, req, original_params),
            )
            return {
                "task_id": new_task_id,
                "status": "started",
                "message": entry.retry_message,
            }
    raise HTTPException(
        status_code=400, detail=f"Unsupported task type for retry: {task_type}"
    )

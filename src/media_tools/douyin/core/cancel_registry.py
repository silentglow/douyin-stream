from __future__ import annotations
"""全局任务取消注册表，供 Douyin 下载器与 API 路由共享。"""
from typing import Optional

import threading
import time

from media_tools.core.task_progress import Stage, DownloadProgress, TranscribeProgress, TaskProgress

_cancel_events: dict[str, threading.Event] = {}

_download_progress: dict[str, TaskProgress] = {}

_ENTRY_TTL = 3600
_last_activity: dict[str, float] = {}

_lock = threading.Lock()


def _maybe_cleanup() -> None:
    """惰性清理过期条目，防止内存泄漏。"""
    now = time.monotonic()
    expired = [k for k, ts in _last_activity.items() if now - ts > _ENTRY_TTL]
    for k in expired:
        _cancel_events.pop(k, None)
        _download_progress.pop(k, None)
        _last_activity.pop(k, None)


def set_cancel_event(task_id: str) -> None:
    """标记指定任务为已取消。"""
    with _lock:
        event = threading.Event()
        event.set()
        _cancel_events[task_id] = event
        _last_activity[task_id] = time.monotonic()


def clear_cancel_event(task_id: str) -> None:
    """清理指定任务的取消标志。"""
    with _lock:
        _cancel_events.pop(task_id, None)
        _download_progress.pop(task_id, None)
        _last_activity.pop(task_id, None)


def is_task_cancelled(task_id: Optional[str]) -> bool:
    """检查指定任务是否已被请求取消。"""
    if not task_id:
        return False
    with _lock:
        event = _cancel_events.get(task_id)
    return event is not None and event.is_set()


def get_download_progress(task_id: str) -> Optional[dict]:
    """获取指定任务的下载进度信息。"""
    with _lock:
        progress = _download_progress.get(task_id)
        if progress:
            return progress.to_dict()
        return None


def set_download_progress(task_id: str, info: dict) -> None:
    """设置指定任务的下载进度信息（兼容旧接口）。"""
    with _lock:
        tp = TaskProgress.from_dict(info) if isinstance(info, dict) else None
        if tp:
            _download_progress[task_id] = tp
        _last_activity[task_id] = time.monotonic()
        if len(_last_activity) % 100 == 0:
            _maybe_cleanup()


def clear_download_progress(task_id: str) -> None:
    """清理指定任务的下载进度信息。"""
    with _lock:
        _download_progress.pop(task_id, None)
        _last_activity.pop(task_id, None)


def init_download_progress(
    task_id: str,
    total: int = 0,
    stage: Stage = Stage.CREATED,
) -> None:
    """初始化下载进度信息。"""
    with _lock:
        download_progress = DownloadProgress(total=total)
        tp = TaskProgress(
            stage=stage,
            overall_percent=0.0,
            download_progress=download_progress,
            transcribe_progress=None,
            error_count=0,
            errors=[],
            details=[],
            start_time=None,
        )
        _download_progress[task_id] = tp
        _last_activity[task_id] = time.monotonic()


def update_stage(task_id: str, stage: Stage) -> None:
    """更新任务阶段。"""
    with _lock:
        progress = _download_progress.get(task_id)
        if progress:
            progress.stage = stage
            _last_activity[task_id] = time.monotonic()


def update_download_status(task_id: str, status: str) -> None:
    """更新下载状态（兼容旧接口）。"""
    stage_mapping = {
        "fetching_list": Stage.FETCHING,
        "downloading": Stage.DOWNLOADING,
        "organizing": Stage.AUDITING,
        "syncing": Stage.TRANSCRIBING,
        "completed": Stage.COMPLETED,
        "failed": Stage.FAILED,
    }
    stage = stage_mapping.get(status, Stage.DOWNLOADING)
    update_stage(task_id, stage)


def update_current_video(task_id: str, video_title: str) -> None:
    """更新当前正在下载的视频。"""
    with _lock:
        progress = _download_progress.get(task_id)
        if progress and progress.download_progress:
            progress.download_progress.current_video = video_title
            progress.download_progress.current_index += 1
            _last_activity[task_id] = time.monotonic()


def update_video_progress(task_id: str, progress_value: float) -> None:
    """更新当前视频的下载进度 (0-100)。"""
    with _lock:
        progress = _download_progress.get(task_id)
        if progress and progress.download_progress:
            progress.download_progress.current_video_progress = progress_value
            _last_activity[task_id] = time.monotonic()


def increment_downloaded(task_id: str, video_title: str = "") -> None:
    """增加已下载计数。"""
    with _lock:
        progress = _download_progress.get(task_id)
        if progress:
            if progress.download_progress is None:
                progress.download_progress = DownloadProgress()
            progress.download_progress.downloaded += 1
            if video_title:
                progress.details.append({
                    "title": video_title,
                    "status": "downloaded",
                    "time": time.time(),
                })
            _update_overall_percent(progress)
        _last_activity[task_id] = time.monotonic()


def increment_skipped(task_id: str, video_title: str = "") -> None:
    """增加跳过计数。"""
    with _lock:
        progress = _download_progress.get(task_id)
        if progress:
            if progress.download_progress is None:
                progress.download_progress = DownloadProgress()
            progress.download_progress.skipped += 1
            if video_title:
                progress.details.append({
                    "title": video_title,
                    "status": "skipped",
                    "time": time.time(),
                })
        _last_activity[task_id] = time.monotonic()


def add_download_error(task_id: str, video_title: str, error_msg: str) -> None:
    """添加下载错误记录。"""
    with _lock:
        progress = _download_progress.get(task_id)
        if progress:
            if progress.download_progress is None:
                progress.download_progress = DownloadProgress()
            progress.download_progress.failed += 1
            progress.error_count += 1
            progress.errors.append({
                "title": video_title,
                "error": error_msg,
                "time": time.time(),
            })
            if len(progress.errors) > 20:
                progress.errors = progress.errors[-20:]
        _last_activity[task_id] = time.monotonic()


def set_total_count(task_id: str, total: int) -> None:
    """设置总视频数量。"""
    with _lock:
        progress = _download_progress.get(task_id)
        if progress:
            if progress.download_progress is None:
                progress.download_progress = DownloadProgress()
            progress.download_progress.total = total
            _update_overall_percent(progress)
        _last_activity[task_id] = time.monotonic()


def update_transcribe_progress(
    task_id: str,
    done: int = 0,
    total: int = 0,
    current_video: str = "",
    current_account: str = "",
    skipped: int = 0,
    failed: int = 0,
) -> None:
    """更新转写进度。"""
    with _lock:
        progress = _download_progress.get(task_id)
        if progress:
            if progress.transcribe_progress is None:
                progress.transcribe_progress = TranscribeProgress()
            progress.transcribe_progress.done = done
            progress.transcribe_progress.total = total
            progress.transcribe_progress.current_video = current_video
            progress.transcribe_progress.current_account = current_account
            progress.transcribe_progress.skipped = skipped
            progress.transcribe_progress.failed = failed
            _update_overall_percent(progress)
        _last_activity[task_id] = time.monotonic()


def increment_transcribe_done(task_id: str, video_title: str = "") -> None:
    """增加转写完成计数。"""
    with _lock:
        progress = _download_progress.get(task_id)
        if progress:
            if progress.transcribe_progress is None:
                progress.transcribe_progress = TranscribeProgress()
            progress.transcribe_progress.done += 1
            _update_overall_percent(progress)
        _last_activity[task_id] = time.monotonic()


def _update_overall_percent(progress: TaskProgress) -> None:
    """根据各阶段进度更新整体百分比。"""
    total_items = 0
    done_items = 0

    if progress.download_progress:
        dp = progress.download_progress
        total_items += dp.total if dp.total > 0 else 1
        done_items += dp.downloaded + dp.skipped

    if progress.transcribe_progress:
        tp = progress.transcribe_progress
        total_items += tp.total if tp.total > 0 else 0
        done_items += tp.done + tp.skipped

    if total_items > 0:
        progress.overall_percent = (done_items / total_items) * 100
    else:
        progress.overall_percent = 0.0


def get_progress_for_api(task_id: str) -> Optional[dict]:
    """获取适合 API 返回格式的进度信息。"""
    progress = get_download_progress(task_id)
    if not progress:
        return None
    return progress.to_dict()

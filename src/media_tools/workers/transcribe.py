from __future__ import annotations
"""转写工作者 - 视频转写逻辑"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def transcribe_files(task_id: str, _progress_fn, new_files: list, display_name: str, auto_delete: bool = False):
    """转写一批视频文件，返回统计信息。使用并发加速处理。"""
    from media_tools.core.config import load_pipeline_config
    from media_tools.transcribe.service import create_orchestrator

    await _progress_fn(0.6, f"下载完成，准备转写 {len(new_files)} 个视频...", stage="transcribe")
    pipeline_config = load_pipeline_config()
    orchestrator = create_orchestrator(
        pipeline_config,
        creator_folder_override=display_name,
    )
    total = len(new_files)
    subtasks: list[dict] = []
    video_paths = [Path(f) for f in new_files]

    # 使用 orchestrator 的 transcribe_batch 统一并发控制
    # （共享 HTTP API context、账号互斥、导出限流）
    try:
        report = await orchestrator.transcribe_batch(video_paths, resume=False)
    except (OSError, RuntimeError) as exc:
        logger.error(f"批量转写失败: {exc}")
        for vp in video_paths:
            subtasks.append({"title": vp.stem[:60], "status": "failed", "error": str(exc), "video_path": str(vp)})
        return {
            "success_count": 0,
            "failed_count": total,
            "total": total,
            "subtasks": subtasks,
            "result_summary": {"success": 0, "failed": total, "skipped": 0, "total": total},
        }

    # 从 report 构建统计和子任务列表
    success_count = report.success
    failed_count = report.failed

    for r in report.results:
        title = Path(r.get("video_path", "")).stem[:60]
        if r.get("success"):
            subtasks.append({"title": title, "status": "completed"})
        else:
            error_msg = r.get("error", "转写失败")
            error_type = r.get("error_type", "unknown")
            subtasks.append({"title": title, "status": "failed", "error": f"[{error_type}] {error_msg}", "video_path": r.get("video_path")})

    # 删除已成功转写的源视频
    if auto_delete:
        for r in report.results:
            if r.get("success"):
                vp = Path(r.get("video_path", ""))
                try:
                    vp.unlink()
                except FileNotFoundError:
                    pass
                except OSError as e:
                    logger.error(f"删除转写后视频失败: {vp}, {e}")

    result_summary = {
        "success": success_count,
        "failed": failed_count,
        "skipped": 0,
        "total": total,
    }
    await _progress_fn(
        0.9,
        f"转写完成：成功 {success_count} 个，失败 {failed_count} 个",
        result_summary=result_summary,
        subtasks=subtasks,
        stage="transcribe",
    )
    return {
        "success_count": success_count,
        "failed_count": failed_count,
        "total": total,
        "subtasks": subtasks,
        "result_summary": result_summary,
    }

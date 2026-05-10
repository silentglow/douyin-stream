import asyncio
from contextlib import asynccontextmanager
from typing import Any
from media_tools.core.logging_context import task_context
from media_tools.pipeline.worker import run_pipeline_for_user, run_batch_pipeline, run_download_only
from media_tools.repositories.task_repository import TaskRepository
from media_tools.services.task_ops import update_task_progress, _complete_task, _fail_task, _mark_task_cancelled
from media_tools.services.task_state import _task_heartbeat


@asynccontextmanager
async def _heartbeat_scope(task_id: str):
    """启动 heartbeat 协程，退出 scope 时取消并等待结束。

    所有 background worker 都按此模板使用 heartbeat，避免每个 worker 各写一份 try/finally。
    同时设置 task_id 日志上下文，worker 内所有日志自动携带 task_id。
    """
    heartbeat = asyncio.create_task(_task_heartbeat(task_id))
    try:
        with task_context(task_id=task_id):
            yield
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass


async def _background_pipeline_worker(task_id: str, req: Any):
    async def _progress_fn(p, m, stage="", pipeline_progress=None):
        await update_task_progress(task_id, p, m, "pipeline", stage=stage, pipeline_progress=pipeline_progress)

    from media_tools.core.config import get_runtime_setting_bool
    delete_after = req.auto_delete if req.auto_delete is not None else get_runtime_setting_bool("auto_delete", True)

    async with _heartbeat_scope(task_id):
        try:
            result = await run_pipeline_for_user(
                url=req.url,
                max_counts=req.max_counts,
                update_progress_fn=_progress_fn,
                delete_after=delete_after,
                task_id=task_id,
            )
            msg = "成功转写完成"
            error_msg = None
            status = "COMPLETED"

            s_count = result.get("success_count", 0)
            f_count = result.get("failed_count", 0)
            total = result.get("total", s_count + f_count)
            subtasks = result.get("subtasks", [])
            export_file = result.get("export_file")

            result_summary = {
                "success": s_count,
                "failed": f_count,
                "skipped": 0,
                "total": total,
            }

            patch: dict[str, Any] = {}
            if isinstance(total, int) and total > 0:
                patch["batch_size"] = total
            if isinstance(export_file, str) and export_file.strip():
                patch["export_file"] = export_file.strip()
                patch["export_status"] = "saved"
            if patch:
                try:
                    TaskRepository.patch_payload(task_id, patch)
                except (OSError, RuntimeError):
                    pass

            if s_count == 0 and f_count == 0:
                msg = "未找到新视频或链接无效"
            elif f_count > 0:
                status = "FAILED"
                first = subtasks[0] if subtasks and isinstance(subtasks[0], dict) else {}
                first_error = first.get("error") if first else f"转写失败 {f_count} 个视频"
                msg = f"转写完成但有失败：成功 {s_count} 个，失败 {f_count} 个"
                error_msg = first_error
            else:
                msg = f"成功转写 {s_count} 个视频，失败 {f_count} 个"

            await _complete_task(
                task_id,
                "pipeline",
                msg,
                status=status,
                error_msg=error_msg,
                result_summary=result_summary,
                subtasks=subtasks,
            )
        except asyncio.CancelledError:
            raise
        except (RuntimeError, OSError) as e:
            await _complete_task(task_id, "pipeline", str(e), status="FAILED", error_msg=str(e))


async def _background_batch_worker(task_id: str, req: Any):
    async def _progress_fn(p, m, stage="", pipeline_progress=None):
        await update_task_progress(task_id, p, m, "pipeline", stage=stage, pipeline_progress=pipeline_progress)

    from media_tools.core.config import get_runtime_setting_bool
    delete_after = req.auto_delete if req.auto_delete is not None else get_runtime_setting_bool("auto_delete", True)

    async with _heartbeat_scope(task_id):
        try:
            result = await run_batch_pipeline(
                video_urls=req.video_urls,
                update_progress_fn=_progress_fn,
                delete_after=delete_after,
                task_id=task_id,
            )
            success_count = result.get("success_count", 0)
            failed_count = result.get("failed_count", 0)
            total = result.get("total", success_count + failed_count)
            subtasks = result.get("subtasks", [])
            export_file = result.get("export_file")

            patch: dict[str, Any] = {}
            if isinstance(total, int) and total > 0:
                patch["batch_size"] = total
            if isinstance(export_file, str) and export_file.strip():
                patch["export_file"] = export_file.strip()
                patch["export_status"] = "saved"
            if patch:
                try:
                    TaskRepository.patch_payload(task_id, patch)
                except (OSError, RuntimeError):
                    pass

            result_summary = {
                "success": int(success_count or 0),
                "failed": int(failed_count or 0),
                "skipped": 0,
                "total": int(total or 0),
            }

            if failed_count > 0:
                await _complete_task(
                    task_id,
                    "pipeline",
                    f"批量处理完成但有失败：成功 {success_count} 个，失败 {failed_count} 个",
                    status="FAILED",
                    error_msg=f"处理失败 {failed_count} 个视频",
                    result_summary=result_summary,
                    subtasks=subtasks,
                )
            else:
                await _complete_task(
                    task_id,
                    "pipeline",
                    f"批量处理完成：成功 {success_count} 个，失败 {failed_count} 个",
                    result_summary=result_summary,
                    subtasks=subtasks,
                )
        except asyncio.CancelledError:
            await _mark_task_cancelled(task_id, "pipeline")
            raise
        except (RuntimeError, OSError) as e:
            await _fail_task(task_id, "pipeline", str(e))


async def _background_download_worker(task_id: str, req: Any):
    async def _progress_fn(p, m, stage=""):
        await update_task_progress(task_id, p, m, "download", stage=stage)

    async with _heartbeat_scope(task_id):
        try:
            result = await run_download_only(
                video_urls=req.video_urls,
                update_progress_fn=_progress_fn,
                task_id=task_id,
            )
            await _complete_task(
                task_id, "download",
                f"下载完成：成功 {result.get('success_count', 0)} 个，失败 {result.get('failed_count', 0)} 个"
            )
        except asyncio.CancelledError:
            await _mark_task_cancelled(task_id, "download")
            raise
        except (RuntimeError, OSError) as e:
            await _fail_task(task_id, "download", str(e))

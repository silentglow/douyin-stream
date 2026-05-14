from __future__ import annotations

import logging
from typing import Any

from media_tools.core.config import get_runtime_setting_bool
from media_tools.transcribe.worker import run_pipeline_for_user, run_batch_pipeline, run_download_only
from media_tools.scheduler.repository import TaskRepository
from media_tools.scheduler.base import BaseWorker, register_worker

logger = logging.getLogger(__name__)


def _resolve_delete_after(req: Any) -> bool:
    if req.auto_delete is not None:
        return req.auto_delete
    return get_runtime_setting_bool("auto_delete", True)


def _patch_payload_with_results(task_id: str, total: int, export_file: str | None) -> None:
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


def _build_pipeline_result_summary(result: dict[str, Any]) -> dict[str, int]:
    s = result.get("success_count", 0)
    f = result.get("failed_count", 0)
    total = result.get("total", s + f)
    return {"success": int(s or 0), "failed": int(f or 0), "skipped": 0, "total": int(total or 0)}


def _resolve_first_error(subtasks: list[dict]) -> str:
    first = subtasks[0] if subtasks and isinstance(subtasks[0], dict) else {}
    return first.get("error") if first else ""


@register_worker("pipeline")
class PipelineWorker(BaseWorker):
    """Pipeline Worker：支持单链接和批量链接两种模式。

    根据 req 是否有 url 或 video_urls 自动分发到 run_pipeline_for_user
    或 run_batch_pipeline。
    """

    task_type = "pipeline"

    async def run(self, task_id: str, *, req: Any) -> None:
        delete_after = _resolve_delete_after(req)

        if hasattr(req, "url"):
            await self._run_single(task_id, req, delete_after)
        elif hasattr(req, "video_urls"):
            await self._run_batch(task_id, req, delete_after)
        else:
            raise ValueError("PipelineRequest 必须包含 url 或 video_urls")

    async def _run_single(self, task_id: str, req: Any, delete_after: bool) -> None:
        result = await run_pipeline_for_user(
            url=req.url,
            max_counts=req.max_counts,
            update_progress_fn=self._progress_fn,
            delete_after=delete_after,
            task_id=task_id,
        )
        s_count = result.get("success_count", 0)
        f_count = result.get("failed_count", 0)
        total = result.get("total", s_count + f_count)
        subtasks = result.get("subtasks", [])
        export_file = result.get("export_file")

        _patch_payload_with_results(task_id, total, export_file)
        result_summary = _build_pipeline_result_summary(result)

        if s_count == 0 and f_count == 0:
            msg = "未找到新视频或链接无效"
            await self.finalize_success(msg, result_summary=result_summary)
            return

        msg = f"转写完成但有失败：成功 {s_count} 个，失败 {f_count} 个"
        if f_count > 0 and s_count > 0:
            first_error = _resolve_first_error(subtasks) or f"转写失败 {f_count} 个视频"
            await self.finalize_partial(
                msg,
                error_msg=first_error,
                result_summary=result_summary,
                subtasks=subtasks,
            )
        elif f_count > 0:
            first_error = _resolve_first_error(subtasks) or f"转写失败 {f_count} 个视频"
            await self.finalize_failure(
                msg,
                error_msg=first_error,
                result_summary=result_summary,
                subtasks=subtasks,
            )
        else:
            await self.finalize_success(
                f"成功转写 {s_count} 个视频，失败 {f_count} 个",
                result_summary=result_summary,
                subtasks=subtasks,
            )

    async def _run_batch(self, task_id: str, req: Any, delete_after: bool) -> None:
        result = await run_batch_pipeline(
            video_urls=req.video_urls,
            update_progress_fn=self._progress_fn,
            delete_after=delete_after,
            task_id=task_id,
        )
        success_count = result.get("success_count", 0)
        failed_count = result.get("failed_count", 0)
        total = result.get("total", success_count + failed_count)
        subtasks = result.get("subtasks", [])
        export_file = result.get("export_file")

        _patch_payload_with_results(task_id, total, export_file)
        result_summary = _build_pipeline_result_summary(result)

        if failed_count > 0 and success_count > 0:
            await self.finalize_partial(
                f"批量处理完成但有失败：成功 {success_count} 个，失败 {failed_count} 个",
                error_msg=f"处理失败 {failed_count} 个视频",
                result_summary=result_summary,
                subtasks=subtasks,
            )
        elif failed_count > 0:
            await self.finalize_failure(
                f"批量处理完成但有失败：成功 {success_count} 个，失败 {failed_count} 个",
                error_msg=f"处理失败 {failed_count} 个视频",
                result_summary=result_summary,
                subtasks=subtasks,
            )
        else:
            await self.finalize_success(
                f"批量处理完成：成功 {success_count} 个，失败 {failed_count} 个",
                result_summary=result_summary,
                subtasks=subtasks,
            )

    async def _progress_fn(self, p: float, m: str, stage: str = "", pipeline_progress: dict | None = None) -> None:
        await self.report_progress(p, m, stage=stage, pipeline_progress=pipeline_progress)


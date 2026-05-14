from __future__ import annotations

import logging
from typing import Any

from media_tools.pipeline.worker import run_local_transcribe
from media_tools.scheduler.base import BaseWorker, register_worker

logger = logging.getLogger(__name__)


@register_worker("local_transcribe")
class LocalTranscribeWorker(BaseWorker):
    """本地文件批量转写 Worker。"""

    task_type = "local_transcribe"

    async def run(self, task_id: str, *, req: Any) -> None:
        result = await run_local_transcribe(
            req.file_paths,
            self._progress_fn,
            req.delete_after,
            task_id=task_id,
        )
        s_count = result.get("success_count", 0)
        f_count = result.get("failed_count", 0)
        total = result.get("total", 0)
        subtasks = result.get("subtasks") if isinstance(result, dict) else None
        result_summary = {
            "success": int(s_count or 0),
            "failed": int(f_count or 0),
            "total": int(total or 0),
        }
        msg = (
            "没有找到有效的音视频文件"
            if total == 0
            else f"本地转写完成：成功 {s_count} 个，失败 {f_count} 个"
        )
        await self.report_progress(
            1.0,
            msg,
            stage="done",
            pipeline_progress={"transcribe": {"done": int(total or 0), "total": int(total or 0)}},
        )
        if f_count == 0:
            await self.finalize_success(
                msg, result_summary=result_summary, subtasks=subtasks
            )
        elif s_count > 0:
            await self.finalize_partial(
                msg,
                error_msg=f"转写失败 {f_count} 个文件",
                result_summary=result_summary,
                subtasks=subtasks,
            )
        else:
            await self.finalize_failure(
                msg,
                error_msg=f"转写失败 {f_count} 个文件",
                result_summary=result_summary,
                subtasks=subtasks,
            )

    async def _progress_fn(self, p: float, m: str, stage: str = "", pipeline_progress: dict | None = None) -> None:
        await self.report_progress(p, m, stage=stage, pipeline_progress=pipeline_progress)


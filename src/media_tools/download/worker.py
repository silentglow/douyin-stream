from __future__ import annotations

import logging
from typing import Any

from media_tools.scheduler.base import BaseWorker, register_worker
from media_tools.transcribe.worker import run_download_only

logger = logging.getLogger(__name__)


@register_worker("download")
class DownloadWorker(BaseWorker):
    """纯下载 Worker，不转写。"""

    task_type = "download"

    async def run(self, task_id: str, *, req: Any) -> None:
        result = await run_download_only(
            video_urls=req.video_urls,
            update_progress_fn=self._progress_fn,
            task_id=task_id,
        )
        await self.finalize_success(
            f"下载完成：成功 {result.get('success_count', 0)} 个，失败 {result.get('failed_count', 0)} 个"
        )

    async def _progress_fn(self, p: float, m: str, stage: str = "") -> None:
        await self.report_progress(p, m, stage=stage)

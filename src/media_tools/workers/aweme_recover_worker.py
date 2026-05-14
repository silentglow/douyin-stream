from __future__ import annotations

import logging
import sqlite3

from media_tools.core.config import get_runtime_setting_bool
from media_tools.store.db import get_db_connection
from media_tools.douyin.core.downloader import download_aweme_by_url
from media_tools.scheduler.base import BaseWorker, register_worker
from media_tools.workers.transcribe import transcribe_files

logger = logging.getLogger(__name__)


@register_worker("recover_aweme_transcribe")
class AwemeRecoverWorker(BaseWorker):
    """补齐单个缺失视频并转写。

    流程：下载 aweme → 自动转写 → 三态终态决策。
    """

    task_type = "recover_aweme_transcribe"

    async def run(
        self,
        task_id: str,
        *,
        creator_uid: str,
        aweme_id: str,
        title: str = "",
    ) -> None:
        resolved_title = title.strip() if isinstance(title, str) else ""
        if not resolved_title:
            try:
                with get_db_connection() as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute(
                        "SELECT desc FROM video_metadata WHERE aweme_id=? LIMIT 1",
                        (aweme_id,),
                    ).fetchone()
                    if row and row["desc"]:
                        resolved_title = str(row["desc"]).strip()
            except (sqlite3.Error, OSError, TypeError, ValueError):
                resolved_title = ""

        display_name = resolved_title or creator_uid or aweme_id

        await self.report_progress(
            0.05, f"补齐下载：{display_name}", stage="downloading"
        )
        url = f"https://www.douyin.com/video/{aweme_id}"
        dl = await download_aweme_by_url(url)
        if not isinstance(dl, dict) or not dl.get("success"):
            raise RuntimeError(f"补齐下载失败: {dl!r}")

        new_files = dl.get("new_files") or []
        if not isinstance(new_files, list) or not new_files:
            raise RuntimeError("补齐下载未产生新文件")

        auto_delete = get_runtime_setting_bool("auto_delete", True)
        tr = await transcribe_files(
            task_id, self._progress_fn, list(new_files), display_name, auto_delete=auto_delete
        )

        s = int(tr.get("success_count", 0) or 0)
        f = int(tr.get("failed_count", 0) or 0)
        total = int(tr.get("total", s + f) or (s + f))
        subtasks = tr.get("subtasks") or []
        result_summary = tr.get("result_summary") or {
            "success": s,
            "failed": f,
            "skipped": 0,
            "total": total,
        }

        msg = f"补齐并转写完成：成功 {s} 个，失败 {f} 个"
        if f == 0:
            await self.finalize_success(
                msg, result_summary=result_summary, subtasks=subtasks
            )
            return

        error_msg = msg
        if isinstance(subtasks, list) and subtasks:
            first = subtasks[0] if isinstance(subtasks[0], dict) else {}
            err = first.get("error") if isinstance(first, dict) else None
            if err:
                error_msg = str(err)

        await self.finalize_failure(
            msg, error_msg=error_msg, result_summary=result_summary, subtasks=subtasks
        )

    async def _progress_fn(
        self,
        p: float,
        m: str,
        result_summary: dict | None = None,
        subtasks: list | None = None,
        stage: str = "",
    ) -> None:
        """透传给 transcribe_files 的进度回调（签名与 transcribe_files 约定一致）。"""
        await self.report_progress(p, m, stage=stage)


from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime
from typing import Optional

from media_tools.store.db import get_db_connection
from media_tools.douyin.core.cancel_registry import clear_download_progress, get_download_progress
from media_tools.douyin.core.downloader import download_by_uid
from media_tools.douyin.core.following_mgr import list_users
from media_tools.scheduler.base import BaseWorker, register_worker
from media_tools.workers.creator_sync import _build_interval_from_last_fetch


@register_worker("full_sync")
class FullSyncWorker(BaseWorker):
    """全量同步 Worker：遍历关注列表，逐个下载创作者视频。"""

    task_type = "full_sync"

    async def run(
        self,
        task_id: str,
        *,
        mode: str = "incremental",
        batch_size: Optional[int] = None,
        original_params: Optional[dict] = None,
    ) -> None:
        users = list_users()
        if not users:
            await self.finalize_success("关注列表为空")
            return

        total = len(users)
        creator_success = 0
        creator_failed = 0
        new_video_count = 0
        skip_existing = True

        for index, user in enumerate(users, 1):
            uid = user.get("uid") or ""
            name = user.get("nickname") or user.get("name") or uid or f"creator-{index}"
            await self.report_progress(
                (index - 1) / total,
                f"正在同步 {name} ({index}/{total}) [{mode}]",
                stage="downloading",
            )

            interval = None
            if mode == "incremental":
                interval = self._fetch_interval_for_uid(uid)

            existing_source = "file" if mode == "full" else "file+db"

            try:
                dl_task = asyncio.create_task(
                    asyncio.to_thread(
                        download_by_uid,
                        uid,
                        batch_size,
                        skip_existing,
                        task_id,
                        interval,
                        existing_source,
                    )
                )
                poll_task = asyncio.create_task(
                    self._poll_creator_download(task_id, index, total, name, batch_size)
                )
                try:
                    result = await dl_task
                finally:
                    poll_task.cancel()
                    try:
                        await poll_task
                    except asyncio.CancelledError:
                        pass
                    clear_download_progress(task_id)

                if isinstance(result, dict) and result.get("success"):
                    creator_success += 1
                    new_video_count += len(result.get("new_files") or [])
                    self._update_last_fetch_time(uid)
                else:
                    creator_failed += 1
            except asyncio.CancelledError:
                raise
            except (RuntimeError, OSError) as exc:
                creator_failed += 1
                await self.report_progress(
                    (index - 1) / total,
                    f"{name} 同步失败: {exc}",
                )
            finally:
                await self.report_progress(
                    index / total,
                    f"已完成 {name} ({index}/{total})",
                )

        result_summary = {
            "success": creator_success,
            "failed": creator_failed,
            "skipped": 0,
            "total": total,
        }
        msg = (
            f"全量同步完成：成功 {creator_success} 位，失败 {creator_failed} 位，"
            f"新增 {new_video_count} 个视频（{mode}）"
        )
        await self.finalize_success(msg, result_summary=result_summary)

    def _fetch_interval_for_uid(self, uid: str) -> str | None:
        try:
            with get_db_connection() as conn:
                cursor = conn.execute(
                    "SELECT last_fetch_time FROM creators WHERE uid = ?",
                    (uid,),
                )
                row = cursor.fetchone()
                last_fetch = (
                    row["last_fetch_time"] if isinstance(row, dict) else row[0]
                ) if row else None
            return _build_interval_from_last_fetch(last_fetch)
        except (sqlite3.Error, OSError):
            return None

    def _update_last_fetch_time(self, uid: str) -> None:
        try:
            with get_db_connection() as conn:
                conn.execute(
                    "UPDATE creators SET last_fetch_time = ? WHERE uid = ?",
                    (datetime.now().isoformat(), uid),
                )
        except sqlite3.Error:
            pass

    async def _poll_creator_download(
        self,
        task_id: str,
        index: int,
        total: int,
        name: str,
        batch_size: Optional[int],
    ) -> None:
        while True:
            await asyncio.sleep(5)
            info = get_download_progress(task_id)
            if not info:
                continue
            d = info.get("download_progress", {}).get("downloaded", 0)
            s = info.get("download_progress", {}).get("skipped", 0)
            details = info.get("details", [])
            errors = info.get("errors", [])
            progress = (index - 1) / total + 0.5 / total * min(
                d / max(batch_size or 50, 1), 1.0
            )
            await self.report_progress(
                progress,
                f"{name}：已下载 {d} 个，跳过 {s} 个",
                pipeline_progress={"download": {"done": d, "skipped": s}},
            )


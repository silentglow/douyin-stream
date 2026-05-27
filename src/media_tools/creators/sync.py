from __future__ import annotations

"""创作者同步工作者"""

import asyncio
import contextlib
import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from media_tools.core.config import get_runtime_setting_bool
from media_tools.douyin.core.cancel_registry import clear_download_progress, get_download_progress
from media_tools.scheduler.base import BaseWorker, register_worker
from media_tools.scheduler.ops import update_task_progress
from media_tools.store.db import get_db_connection, get_table_columns
from media_tools.workers.transcribe import transcribe_files

logger = logging.getLogger(__name__)


def _build_interval_from_last_fetch(last_fetch_time: str | None) -> str | None:
    """根据 last_fetch_time 构建 F2 interval 参数

    F2 interval 格式: "2026-01-15|2026-04-26"
    - last_fetch_time 为 None → 返回 None（退化全量）
    - last_fetch_time 距今超过 180 天 → 返回 None（时间太久，直接全量更高效）
    - 否则 → 返回 "last_fetch_date|today"
    """
    if not last_fetch_time:
        return None

    try:
        # 兼容多种日期格式
        fetch_dt = datetime.fromisoformat(last_fetch_time.replace("Z", "+00:00"))
        if fetch_dt.tzinfo is None:
            fetch_dt = fetch_dt.replace(tzinfo=UTC)
        now = datetime.now(UTC)

        if (now - fetch_dt) > timedelta(days=180):
            logger.info("last_fetch_time 距今超过 180 天，退化为全量模式")
            return None

        start_date = fetch_dt.strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")
        return f"{start_date}|{end_date}"
    except (ValueError, OSError) as e:
        logger.warning(f"解析 last_fetch_time 失败: {e}")
        return None


@register_worker("creator_sync")
class CreatorSyncWorker(BaseWorker):
    """创作者同步 Worker - 下载 + 自动转写。

    mode:
      - incremental: 基于 last_fetch_time 的时间范围增量同步
      - full: 拉取博主全部视频
    """

    task_type = "creator_sync"

    def __init__(self) -> None:
        super().__init__()
        self._mode = "incremental"

    def _get_task_context_kwargs(self, **run_kwargs: Any) -> dict[str, Any]:
        return {"creator_uid": run_kwargs.get("uid", "")}

    async def report_progress(
        self,
        progress: float,
        message: str,
        *,
        stage: str = "",
        pipeline_progress: dict | None = None,
        result_summary: dict | None = None,
        subtasks: list | None = None,
    ) -> None:
        """覆盖基类方法，支持 result_summary/subtasks 透传（与 transcribe_files 兼容）。"""
        await update_task_progress(
            self._task_id,
            progress,
            message,
            f"creator_sync_{self._mode}",
            result_summary,
            subtasks,
            stage,
            pipeline_progress,
        )

    async def run(
        self,
        task_id: str,
        *,
        uid: str,
        mode: str = "incremental",
        batch_size: int | None = None,
        original_params: dict | None = None,
    ) -> None:
        self._mode = mode

        # 查询创作者信息
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT uid, sec_user_id, nickname, platform FROM creators WHERE uid = ? LIMIT 1",
                (uid,),
            )
            creator_row = cursor.fetchone()

        if not creator_row:
            raise RuntimeError(f"Creator not found: {uid}")

        platform = (
            creator_row.get("platform") if isinstance(creator_row, dict) else creator_row["platform"]
        ) or "douyin"
        sec_user_id = (
            creator_row.get("sec_user_id") if isinstance(creator_row, dict) else creator_row["sec_user_id"]
        ) or ""
        display_name = (
            creator_row.get("nickname") if isinstance(creator_row, dict) else creator_row["nickname"]
        ) or uid

        # 查询 last_fetch_time（增量模式需要）
        last_fetch_time = None
        if mode == "incremental":
            with get_db_connection() as conn:
                cursor = conn.execute(
                    "SELECT last_fetch_time FROM creators WHERE uid = ?",
                    (uid,),
                )
                row = cursor.fetchone()
                if row:
                    last_fetch_time = row["last_fetch_time"] if isinstance(row, dict) else row[0]

        # 确定下载参数
        max_counts = None
        interval = None

        if batch_size is not None:
            max_counts = batch_size
            mode_label = f"每批 {batch_size} 个"
        elif mode == "full":
            max_counts = None
            mode_label = "全部"
        else:
            interval = _build_interval_from_last_fetch(last_fetch_time)
            mode_label = f"增量（{interval}）" if interval else "增量（退化全量）"

        await self.report_progress(0.05, f"开始同步 {display_name} 的视频（{mode_label}）...", stage="fetching")

        skip_existing = self._mode != "full"
        total_downloaded = 0
        all_new_files: list[str] = []
        last_result: dict[str, Any] = {}
        transcribe_stats = {"success_count": 0, "failed_count": 0, "total": 0}
        all_subtasks: list[dict] = []

        info = get_download_progress(task_id) or {}
        await self.report_progress(0.1, "下载中...", stage=info.get("stage", "downloading"))

        if platform == "bilibili":
            logger.info(f"[创作者同步] 使用 yt-dlp 下载 B 站 UP 主 {display_name} (mid={sec_user_id or uid})")
            new_files = await self._download_bilibili(task_id, uid, sec_user_id, max_counts, skip_existing, last_result)
        else:
            logger.info(f"[创作者同步] 使用 F2 下载抖音用户 {display_name} (sec_user_id={sec_user_id})")
            new_files = await self._download_douyin(
                task_id, uid, sec_user_id, max_counts, skip_existing, interval, last_result
            )

        logger.info(f"[创作者同步] 下载阶段完成 — {display_name}: {len(new_files)} 个新文件")

        # 对账
        missing_items, missing_subtasks, reconcile_total, reconcile_missing = await self._reconcile(uid)
        if missing_items:
            all_subtasks.extend(missing_subtasks)
        if reconcile_total > 0:
            await self.report_progress(0.72, f"对账完成：缺失 {reconcile_missing} 条", stage="auditing")

        # 自动转写
        auto_transcribe = get_runtime_setting_bool("auto_transcribe")
        auto_delete = get_runtime_setting_bool("auto_delete", True)
        if auto_transcribe and new_files:
            tr = await transcribe_files(task_id, self._progress_fn, new_files, display_name, auto_delete)
            transcribe_stats["success_count"] += tr.get("success_count", 0)
            transcribe_stats["failed_count"] += tr.get("failed_count", 0)
            transcribe_stats["total"] += tr.get("total", 0)
            all_subtasks.extend(tr.get("subtasks", []))

        total_downloaded = len(new_files)
        all_new_files.extend(new_files)

        # 更新创作者信息
        await self._update_creator_info(last_result, uid)

        # 构建结果摘要
        result_summary = self._build_result_summary(transcribe_stats, reconcile_total, reconcile_missing)
        msg = self._build_message(
            display_name, total_downloaded, transcribe_stats, reconcile_total, reconcile_missing, mode
        )

        # 更新 last_fetch_time
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE creators SET last_fetch_time = CURRENT_TIMESTAMP WHERE uid = ?",
                (uid,),
            )
            conn.commit()

        # 三态决策
        rs_success = int(result_summary.get("success") or 0)
        rs_failed = int(result_summary.get("failed") or 0)
        if rs_failed == 0:
            await self.finalize_success(msg, result_summary=result_summary, subtasks=all_subtasks or None)
        elif rs_success > 0:
            error_msg = None
            if transcribe_stats["failed_count"] > 0:
                error_msg = f"转写失败 {transcribe_stats['failed_count']} 个视频"
            elif reconcile_total > 0 and reconcile_missing > 0:
                error_msg = f"下载对账缺失 {reconcile_missing} 条"
            await self.finalize_partial(
                msg,
                error_msg=error_msg,
                result_summary=result_summary,
                subtasks=all_subtasks or None,
            )
        else:
            error_msg = None
            if transcribe_stats["failed_count"] > 0:
                error_msg = f"转写失败 {transcribe_stats['failed_count']} 个视频"
            elif reconcile_total > 0 and reconcile_missing > 0:
                error_msg = f"下载对账缺失 {reconcile_missing} 条"
            await self.finalize_failure(
                msg,
                error_msg=error_msg,
                result_summary=result_summary,
                subtasks=all_subtasks or None,
            )

    # ------------------------------------------------------------------
    # 下载逻辑
    # ------------------------------------------------------------------
    async def _download_bilibili(
        self,
        task_id: str,
        uid: str,
        sec_user_id: str,
        max_counts: int | None,
        skip_existing: bool,
        last_result: dict[str, Any],
    ) -> list[str]:
        from media_tools.platform.bilibili import download_up_by_url

        mid = sec_user_id or uid.split(":", 1)[-1]
        url = f"https://space.bilibili.com/{mid}"
        logger.info(f"[B站下载] 启动: space.bilibili.com/{mid} (max={max_counts or '全部'}, skip={skip_existing})")
        try:
            result = await asyncio.to_thread(
                download_up_by_url, url, max_counts, skip_existing, None, task_id, False, not skip_existing
            )
        except (RuntimeError, OSError, ValueError) as e:
            error_msg = str(e)
            logger.error(f"[B站下载] 失败: {error_msg}")
            if "412" in error_msg or "blocked" in error_msg.lower():
                await self.report_progress(
                    0.5,
                    "B站请求被拦截(412)，请更换IP或稍后重试",
                    stage="downloading",
                )
                raise RuntimeError(f"B站请求被拦截(412)，请更换IP或稍后重试: {error_msg}")
            raise
        if isinstance(result, dict):
            last_result.update(result)
            new_files = result.get("new_files") or []
            uploader = result.get("uploader")
            logger.info(
                f"[B站下载] 结束: {len(new_files)} 个新文件"
                f"{'，UP主=' + uploader.get('nickname', '?') if uploader else ''}"
            )
            return new_files
        logger.warning(f"[B站下载] 返回格式异常: {type(result)}")
        return []

    async def _download_douyin(
        self,
        task_id: str,
        uid: str,
        sec_user_id: str,
        max_counts: int | None,
        skip_existing: bool,
        interval: str | None,
        last_result: dict[str, Any],
    ) -> list[str]:
        from media_tools.platform.douyin import download_by_url

        if sec_user_id.startswith("MS4w"):
            url = f"https://www.douyin.com/user/{sec_user_id}"
        else:
            url = f"https://www.douyin.com/user/{uid}"

        existing_source = "file" if self._mode == "full" else "file+db"

        dl_task = asyncio.create_task(
            asyncio.to_thread(
                download_by_url,
                url,
                max_counts,
                False,
                skip_existing,
                task_id,
                interval,
                existing_source,
            )
        )
        poll_task = asyncio.create_task(self._poll_download(task_id))
        try:
            result = await dl_task
        finally:
            poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await poll_task
            clear_download_progress(task_id)

        if isinstance(result, dict):
            last_result.update(result)

        if not isinstance(result, dict) or not result.get("success"):
            err = result.get("error") if isinstance(result, dict) else ""
            msg = f"下载失败: {err}" if err else f"下载失败: {result}"
            logger.warning(msg)
            raise RuntimeError(msg)

        return (result.get("new_files") or []) if isinstance(result, dict) else []

    async def _poll_download(self, task_id: str) -> None:
        """Douyin 下载进度轮询。"""
        while True:
            await asyncio.sleep(5)
            info = get_download_progress(task_id)
            if not info:
                continue
            d = info.get("download_progress", {}).get("downloaded", 0)
            s = info.get("download_progress", {}).get("skipped", 0)
            errors = info.get("errors", [])
            subtasks = [
                {"title": d_.get("title", "未知")[:60], "status": d_.get("status", "unknown")} for d_ in errors[-50:]
            ]
            dl_info = info.get("download_progress") or {}
            total = dl_info.get("total", 0)
            current_video = dl_info.get("current_video", "")
            current_index = dl_info.get("current_index", 0)
            progress = 0.1 + 0.6 * (min(d / total, 1.0) if total > 0 else 0.0)
            await self.report_progress(
                progress,
                f"正在下载 ({current_index}/{total}): {current_video}"
                if current_video
                else f"已下载 {d} 个，跳过 {s} 个",
                stage=info.get("stage", "downloading"),
                pipeline_progress={
                    "download": {
                        "done": d,
                        "total": total,
                        "current_title": current_video,
                        "current_index": current_index,
                    },
                },
                subtasks=subtasks,
            )

    # ------------------------------------------------------------------
    # 对账逻辑
    # ------------------------------------------------------------------
    async def _reconcile(self, uid: str) -> tuple[list[dict], list[dict], int, int]:
        missing_items: list[dict[str, Any]] = []
        missing_subtasks: list[dict[str, Any]] = []
        reconcile_total = 0
        reconcile_missing = 0
        try:
            with get_db_connection() as conn:
                cursor = conn.execute("SELECT aweme_id, desc FROM video_metadata WHERE uid = ?", (uid,))
                rows = cursor.fetchall()
                if rows:
                    videos: list[tuple[str, str]] = []
                    for r in rows:
                        aweme_id = r["aweme_id"] if isinstance(r, sqlite3.Row) else r[0]
                        title = r["desc"] if isinstance(r, sqlite3.Row) else r[1]
                        videos.append((str(aweme_id), str(title or "")))

                    reconcile_total = len(videos)
                    placeholders = ",".join(["?"] * len(videos))
                    cursor = conn.execute(
                        f"SELECT asset_id, video_status FROM media_assets WHERE creator_uid = ? AND asset_id IN ({placeholders})",
                        (uid, *[v[0] for v in videos]),
                    )
                    status_map = {}
                    for r in cursor.fetchall():
                        asset_id = r["asset_id"] if isinstance(r, sqlite3.Row) else r[0]
                        video_status = r["video_status"] if isinstance(r, sqlite3.Row) else r[1]
                        status_map[str(asset_id)] = str(video_status or "")

                    for aweme_id, title in videos:
                        video_status = status_map.get(aweme_id) or ""
                        if video_status not in ("downloaded", "archived"):
                            reason = "未找到已下载文件"
                            reconcile_missing += 1
                            missing_items.append(
                                {
                                    "aweme_id": aweme_id,
                                    "title": title,
                                    "status": "manual_required",
                                    "reason": reason,
                                    "attempts": 0,
                                }
                            )
                            missing_subtasks.append({"title": title, "status": "manual_required", "error": reason})

                    if missing_items:
                        try:
                            row = conn.execute(
                                "SELECT payload FROM task_queue WHERE task_id = ?",
                                (self._task_id,),
                            ).fetchone()
                            existing_raw = (
                                row["payload"] if row and isinstance(row, sqlite3.Row) else (row[0] if row else None)
                            )
                            base: dict[str, Any] = {}
                            if existing_raw:
                                try:
                                    parsed = json.loads(str(existing_raw))
                                except (TypeError, ValueError, json.JSONDecodeError):
                                    parsed = {}
                                if isinstance(parsed, dict):
                                    base = parsed
                            base["missing_items"] = missing_items
                            conn.execute(
                                "UPDATE task_queue SET payload = ? WHERE task_id = ?",
                                (json.dumps(base, ensure_ascii=False), self._task_id),
                            )
                            conn.commit()
                        except sqlite3.Error:
                            pass
        except (sqlite3.Error, OSError, ValueError, TypeError):
            missing_items = []
            missing_subtasks = []
            reconcile_total = 0
            reconcile_missing = 0

        return missing_items, missing_subtasks, reconcile_total, reconcile_missing

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    async def _update_creator_info(self, last_result: dict[str, Any], uid: str) -> None:
        uploader = last_result.get("uploader")
        if not uploader or not uploader.get("nickname"):
            return
        with get_db_connection() as conn:
            creator_columns = get_table_columns(conn, "creators")
            if "homepage_url" in creator_columns:
                conn.execute(
                    "UPDATE creators SET nickname = ?, homepage_url = ? WHERE uid = ?",
                    (uploader["nickname"], uploader.get("homepage_url", ""), uid),
                )
            else:
                conn.execute(
                    "UPDATE creators SET nickname = ? WHERE uid = ?",
                    (uploader["nickname"], uid),
                )
            conn.commit()

    def _build_result_summary(
        self,
        transcribe_stats: dict[str, int],
        reconcile_total: int,
        reconcile_missing: int,
    ) -> dict[str, int]:
        if transcribe_stats["total"] > 0:
            return {
                "success": transcribe_stats["success_count"],
                "failed": transcribe_stats["failed_count"],
                "skipped": 0,
                "total": transcribe_stats["total"],
            }
        elif reconcile_total > 0:
            return {
                "success": max(reconcile_total - reconcile_missing, 0),
                "failed": reconcile_missing,
                "skipped": 0,
                "total": reconcile_total,
            }
        return {"success": 0, "failed": 0, "skipped": 0, "total": 0}

    def _build_message(
        self,
        display_name: str,
        total_downloaded: int,
        transcribe_stats: dict[str, int],
        reconcile_total: int,
        reconcile_missing: int,
        mode: str,
    ) -> str:
        if transcribe_stats["total"] > 0:
            return (
                f"{display_name} 同步完成：下载 {total_downloaded} 个，"
                f"转写成功 {transcribe_stats['success_count']} 个，"
                f"失败 {transcribe_stats['failed_count']} 个"
            )
        elif reconcile_total > 0 and reconcile_missing > 0:
            return (
                f"{display_name} 同步完成：入库 {reconcile_total} 条，缺失 {reconcile_missing} 条，可在任务详情中补齐"
            )
        return f"{display_name} 同步完成：共 {total_downloaded} 个新视频（{mode}）"

    async def _progress_fn(
        self,
        p: float,
        m: str,
        result_summary: dict | None = None,
        subtasks: list | None = None,
        stage: str = "",
        pipeline_progress: dict | None = None,
    ) -> None:
        """透传给 transcribe_files 的进度回调。"""
        await self.report_progress(
            p,
            m,
            stage=stage,
            pipeline_progress=pipeline_progress,
            result_summary=result_summary,
            subtasks=subtasks,
        )

from __future__ import annotations
"""创作者同步工作者"""

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Union

from media_tools.core.config import get_runtime_setting_bool
from media_tools.core.logging_context import task_context
from media_tools.douyin.core.cancel_registry import clear_download_progress, get_download_progress
from media_tools.services.task_ops import (
    _complete_task,
    notify_task_update,
    update_task_progress,
)
from media_tools.services.task_state import _task_heartbeat
from media_tools.db.core import get_db_connection, get_table_columns
from media_tools.workers.transcribe import transcribe_files

logger = logging.getLogger(__name__)


def _build_interval_from_last_fetch(last_fetch_time: Optional[str]) -> Optional[str]:
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
            fetch_dt = fetch_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

        if (now - fetch_dt) > timedelta(days=180):
            logger.info(f"last_fetch_time 距今超过 180 天，退化为全量模式")
            return None

        start_date = fetch_dt.strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")
        return f"{start_date}|{end_date}"
    except (ValueError, OSError) as e:
        logger.warning(f"解析 last_fetch_time 失败: {e}")
        return None


async def background_creator_download_worker(
    task_id: str,
    uid: str,
    mode: str = "incremental",
    batch_size: Optional[int] = None,
    original_params: Optional[dict] = None,
):
    """创作者同步 Worker - 下载 + 自动转写

    mode:
      - incremental: 基于 last_fetch_time 的时间范围增量同步
        有 last_fetch_time → F2 interval 参数限制时间范围，只拉取上次同步后发布的新视频
        无 last_fetch_time → 退化为全量模式
      - full: 拉取博主全部视频（F2 max_counts=None，内部翻页拉完所有）
    batch_size:
      用户指定时优先使用，覆盖 mode 的默认行为
    """

    async def _progress_fn(p, m, result_summary=None, subtasks=None, stage=""):
        await update_task_progress(task_id, p, m, f"creator_sync_{mode}", result_summary, subtasks, stage)

    heartbeat = asyncio.create_task(_task_heartbeat(task_id))
    try:
        with task_context(task_id=task_id, creator_uid=uid):
            with get_db_connection() as conn:
                cursor = conn.execute(
                    "SELECT uid, sec_user_id, nickname, platform FROM creators WHERE uid = ? LIMIT 1",
                    (uid,),
                )
                creator_row = cursor.fetchone()

        if not creator_row:
            raise RuntimeError(f"Creator not found: {uid}")

        platform = (creator_row.get("platform") if isinstance(creator_row, dict) else creator_row["platform"]) or "douyin"
        sec_user_id = (creator_row.get("sec_user_id") if isinstance(creator_row, dict) else creator_row["sec_user_id"]) or ""
        display_name = (creator_row.get("nickname") if isinstance(creator_row, dict) else creator_row["nickname"]) or uid

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
            # 用户显式指定 batch_size，优先使用
            max_counts = batch_size
            mode_label = f"每批 {batch_size} 个"
        elif mode == "full":
            max_counts = None
            mode_label = "全部"
        else:
            # 增量模式：基于时间范围
            interval = _build_interval_from_last_fetch(last_fetch_time)
            if interval:
                mode_label = f"增量（{interval}）"
            else:
                # 无 last_fetch_time 或距今太久，退化为全量
                mode_label = "增量（退化全量）"

        await _progress_fn(0.05, f"开始同步 {display_name} 的视频（{mode_label}）...", stage="fetching")

        skip_existing = True
        total_downloaded = 0
        all_new_files: list[str] = []
        last_result: dict[str, Any] = {}
        transcribe_stats = {"success_count": 0, "failed_count": 0, "total": 0}
        all_subtasks: list[dict] = []

        info = get_download_progress(task_id) or {}
        await _progress_fn(0.1, f"下载中...", stage=info.get("stage", "downloading"))

        if platform == "bilibili":
            from media_tools.bilibili.core.downloader import download_up_by_url

            mid = sec_user_id or uid.split(":", 1)[-1]
            url = f"https://space.bilibili.com/{mid}"
            try:
                result = await asyncio.to_thread(download_up_by_url, url, max_counts, skip_existing, None, task_id)
            except (RuntimeError, OSError, ValueError) as e:
                error_msg = str(e)
                if "412" in error_msg or "blocked" in error_msg.lower():
                    await _progress_fn(0.5, f"B站请求被拦截(412)，请更换IP或稍后重试", stage=info.get("stage", "downloading"))
                    raise RuntimeError(f"B站请求被拦截(412)，请更换IP或稍后重试: {error_msg}")
                raise
            if isinstance(result, dict):
                last_result = result
            new_files = (result.get("new_files") or []) if isinstance(result, dict) else []

        else:
            from media_tools.douyin.core.downloader import download_by_url

            if sec_user_id.startswith("MS4w"):
                url = f"https://www.douyin.com/user/{sec_user_id}"
            else:
                url = f"https://www.douyin.com/user/{uid}"

            existing_source = "file" if mode == "full" else "file+db"

            dl_task = asyncio.create_task(
                asyncio.to_thread(download_by_url, url, max_counts, False, skip_existing, task_id, interval, existing_source)
            )

            async def _poll():
                while True:
                    await asyncio.sleep(5)
                    info = get_download_progress(task_id)
                    if info:
                        d = info.get("download_progress", {}).get("downloaded", 0)
                        s = info.get("download_progress", {}).get("skipped", 0)
                        errors = info.get("errors", [])
                        subtasks = [
                            {"title": d_.get("title", "未知")[:60], "status": d_.get("status", "unknown")}
                            for d_ in errors[-50:]
                        ]
                        await update_task_progress(
                            task_id,
                            0.1 + 0.6 * min(d / 100, 1.0),
                            f"已下载 {d} 个，跳过 {s} 个",
                            f"creator_sync_{mode}",
                            subtasks=subtasks,
                            stage=info.get("stage", "downloading"),
                        )

            poll_task = asyncio.create_task(_poll())
            try:
                result = await dl_task
            finally:
                poll_task.cancel()
                try:
                    await poll_task
                except asyncio.CancelledError:
                    pass
                clear_download_progress(task_id)

            if isinstance(result, dict):
                last_result = result

            if not isinstance(result, dict) or not result.get("success"):
                logger.warning(f"下载失败: {result}")
                raise RuntimeError(f"下载失败: {result}")

            new_files = (result.get("new_files") or []) if isinstance(result, dict) else []

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
                        if video_status != "downloaded":
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
                            missing_subtasks.append(
                                {"title": title, "status": "manual_required", "error": reason}
                            )

                    if missing_items:
                        try:
                            row = conn.execute("SELECT payload FROM task_queue WHERE task_id = ?", (task_id,)).fetchone()
                            existing_raw = row["payload"] if row and isinstance(row, sqlite3.Row) else (row[0] if row else None)
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
                                (json.dumps(base, ensure_ascii=False), task_id),
                            )
                            conn.commit()
                        except sqlite3.Error:
                            pass
        except (sqlite3.Error, OSError, ValueError, TypeError):
            missing_items = []
            missing_subtasks = []
            reconcile_total = 0
            reconcile_missing = 0

        if missing_items:
            all_subtasks.extend(missing_subtasks)
        if reconcile_total > 0:
            await _progress_fn(
                0.72,
                f"对账完成：缺失 {reconcile_missing} 条",
                stage="auditing",
            )

        # 自动转写
        auto_transcribe = get_runtime_setting_bool("auto_transcribe")
        auto_delete = get_runtime_setting_bool("auto_delete", True)
        if auto_transcribe and new_files:
            tr = await transcribe_files(task_id, _progress_fn, new_files, display_name, auto_delete)
            transcribe_stats["success_count"] += tr.get("success_count", 0)
            transcribe_stats["failed_count"] += tr.get("failed_count", 0)
            transcribe_stats["total"] += tr.get("total", 0)
            all_subtasks.extend(tr.get("subtasks", []))

        total_downloaded = len(new_files)
        all_new_files.extend(new_files)

        # 更新创作者信息
        if uploader := last_result.get("uploader"):
            if uploader.get("nickname"):
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

        # 构建结果摘要
        if transcribe_stats["total"] > 0:
            result_summary = {
                "success": transcribe_stats["success_count"],
                "failed": transcribe_stats["failed_count"],
                "skipped": 0,
                "total": transcribe_stats["total"],
            }
        elif reconcile_total > 0:
            result_summary = {
                "success": max(reconcile_total - reconcile_missing, 0),
                "failed": reconcile_missing,
                "skipped": 0,
                "total": reconcile_total,
            }
        else:
            result_summary = {"success": 0, "failed": 0, "skipped": 0, "total": 0}
        if transcribe_stats["total"] > 0:
            msg = f"{display_name} 同步完成：下载 {total_downloaded} 个，转写成功 {transcribe_stats['success_count']} 个，失败 {transcribe_stats['failed_count']} 个"
        elif reconcile_total > 0 and reconcile_missing > 0:
            msg = f"{display_name} 同步完成：入库 {reconcile_total} 条，缺失 {reconcile_missing} 条，可在任务详情中补齐"
        else:
            msg = f"{display_name} 同步完成：共 {total_downloaded} 个新视频（{mode}）"
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE creators SET last_fetch_time = CURRENT_TIMESTAMP WHERE uid = ?",
                (uid,)
            )
            conn.commit()
        # 三态决策：全成功 -> COMPLETED，全失败 -> FAILED，混合 -> PARTIAL_FAILED。
        # 用 result_summary 已合并的 success/failed 计数（含 reconcile_missing），
        # 避免在判定逻辑里再算一次 reconcile + transcribe 之和。
        rs_success = int(result_summary.get("success") or 0)
        rs_failed = int(result_summary.get("failed") or 0)
        if rs_failed == 0:
            status = "COMPLETED"
        elif rs_success > 0:
            status = "PARTIAL_FAILED"
        else:
            status = "FAILED"
        error_msg = None
        if transcribe_stats["failed_count"] > 0:
            error_msg = f"转写失败 {transcribe_stats['failed_count']} 个视频"
        elif reconcile_total > 0 and reconcile_missing > 0:
            error_msg = f"下载对账缺失 {reconcile_missing} 条"
        await _complete_task(
            task_id,
            f"creator_sync_{mode}",
            msg,
            status=status,
            error_msg=error_msg,
            result_summary=result_summary,
            subtasks=all_subtasks or None,
        )
    except asyncio.CancelledError:
        raise
    except (RuntimeError, OSError, sqlite3.Error) as e:
        logger.exception(f"creator_download_worker failed for {uid}")
        await _complete_task(task_id, f"creator_sync_{mode}", str(e), status="FAILED", error_msg=str(e))
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass

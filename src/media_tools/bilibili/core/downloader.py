from __future__ import annotations

import inspect
import os
import re
import shutil
import sqlite3
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Union

from media_tools.common.paths import get_download_path
from media_tools.logger import get_logger

from media_tools.bilibili.utils.cookies import get_bilibili_cookie_string
from media_tools.bilibili.utils.naming import sanitize_filename
from .temp_files import managed_temp_file
from .task_control import (
    PauseController,
    register_cancel_flag,
    cancel_download,
    unregister_cancel_flag,
    register_pause_controller,
    get_pause_controller,
    unregister_pause_controller,
    pause_task,
    resume_task,
    cancel_task_download,
)

logger = get_logger("bilibili")


@dataclass
class UploaderInfo:
    """B站 UP 主信息"""
    nickname: str
    mid: str
    homepage_url: str = ""


# 扩展进度回调：支持详细进度信息
DownloadProgress = dict[str, Any]
ProgressCallback = Callable[[float, str, DownloadProgress], Any]
# 兼容旧的回调签名
LegacyProgressCallback = Callable[[float, str], Any]

try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None

def _format_speed(speed_bytes_per_sec: float) -> str:
    """格式化下载速度"""
    if speed_bytes_per_sec >= 1024 * 1024:
        return f"{speed_bytes_per_sec / (1024 * 1024):.1f} MB/s"
    elif speed_bytes_per_sec >= 1024:
        return f"{speed_bytes_per_sec / 1024:.1f} KB/s"
    else:
        return f"{speed_bytes_per_sec:.0f} B/s"


def _format_eta(seconds: int | float) -> str:
    """格式化剩余时间"""
    if seconds >= 3600:
        return f"{int(seconds / 3600)}h {int((seconds % 3600) / 60)}m"
    elif seconds >= 60:
        return f"{int(seconds / 60)}m {int(seconds % 60)}s"
    else:
        return f"{int(seconds)}s"


def _build_output_template(base_dir: Path, creator_folder: str, series_folder: str) -> str:
    safe_creator = sanitize_filename(creator_folder) or "bilibili"
    safe_series = sanitize_filename(series_folder) or "全部投稿"
    target_dir = base_dir / safe_creator / safe_series
    target_dir.mkdir(parents=True, exist_ok=True)
    return str(target_dir / "%(title)s__%(id)s__%(format_id)s.%(ext)s")


def _iter_yt_dlp_entries(info: Optional[dict]):
    """扁平化 yt-dlp info：单视频返回自身，playlist/channel 递归其 entries。"""
    if not isinstance(info, dict):
        return
    entries = info.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            yield from _iter_yt_dlp_entries(entry)
    else:
        yield info


def _persist_bilibili_assets_to_db(
    info: Optional[dict],
    new_files: list[str],
    downloads_path: Path,
    uploader_info: UploaderInfo | None,
) -> None:
    """把 yt-dlp 本次下载的结果写入 media_assets。

    asset_id 用 build_bilibili_asset_id(bvid, p_index)，与前端/后端已有命名约定保持一致。
    仅在文件实际被下载到磁盘时才入库（new_files 命中）。
    """
    if not new_files:
        return

    from media_tools.assets.service import MediaAssetService
    from media_tools.bilibili.utils.naming import build_bilibili_creator_uid, build_bilibili_asset_id

    new_files_resolved = {str(Path(p).resolve()): p for p in new_files}

    for entry in _iter_yt_dlp_entries(info):
        bvid = entry.get("id") or entry.get("display_id")
        if not bvid:
            continue

        # 解析对应的下载文件（requested_downloads 里有 filepath）
        requested = entry.get("requested_downloads") or []
        downloaded_path: Optional[Path] = None
        for item in requested:
            fp = item.get("filepath")
            if not fp:
                continue
            resolved = str(Path(fp).resolve())
            if resolved in new_files_resolved:
                downloaded_path = Path(fp)
                break
        if downloaded_path is None:
            continue

        uploader = (
            entry.get("uploader") or entry.get("channel") or entry.get("uploader_name")
            or (uploader_info.nickname if uploader_info else "")
        )
        mid = (
            entry.get("uploader_id") or entry.get("channel_id") or entry.get("mid")
            or (uploader_info.mid if uploader_info else "")
        )
        if not mid:
            # 没 mid 就没法挂创作者，跳过而非乱写
            continue
        creator_uid = build_bilibili_creator_uid(str(mid))

        p_index_raw = entry.get("playlist_index")
        p_index = int(p_index_raw) if isinstance(p_index_raw, int) else None
        asset_id = build_bilibili_asset_id(str(bvid), p_index)

        title = entry.get("title") or downloaded_path.stem
        duration = entry.get("duration")
        duration_int = int(duration) if isinstance(duration, (int, float)) else None
        source_url = entry.get("webpage_url") or entry.get("original_url") or ""

        try:
            video_path_rel = str(downloaded_path.relative_to(downloads_path))
        except ValueError:
            video_path_rel = str(downloaded_path)

        try:
            folder_path = downloaded_path.parent.name
        except (OSError, ValueError):
            folder_path = ""

        MediaAssetService.mark_downloaded(
            asset_id=asset_id,
            creator_uid=creator_uid,
            title=title,
            video_path=video_path_rel,
            source_platform="bilibili",
            source_url=source_url,
            folder_path=folder_path,
            duration=duration_int,
        )


def download_up_by_url(
    url: str,
    max_counts: Optional[int] = None,
    skip_existing: bool = True,
    progress_cb: ProgressCallback | None = None,
    task_id: Optional[str] = None,
    disable_auto_transcribe: bool = False,
) -> dict:
    if YoutubeDL is None:
        raise RuntimeError("yt-dlp not installed")

    downloads_path = get_download_path()

    cookie = get_bilibili_cookie_string()

    uploader_info: UploaderInfo | None = None
    cancel_flag = register_cancel_flag(task_id) if task_id else None

    def hook(d: dict):
        nonlocal uploader_info

        # 检查是否被取消（线程安全）
        if cancel_flag and cancel_flag.is_set():
            raise RuntimeError(f"下载已取消: task_id={task_id}")

        if not progress_cb:
            return

        # 检测回调函数签名，兼容新旧版本
        try:
            sig = inspect.signature(progress_cb)
            param_count = len(sig.parameters)
        except (ValueError, TypeError):
            param_count = 2  # 默认兼容旧签名

        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            speed = d.get("speed") or 0
            eta = d.get("eta")

            p = (downloaded / total) if total else 0.0
            progress_msg = "下载中"

            # 构建详细进度信息
            extra_info: DownloadProgress = {}
            if total > 0:
                extra_info["total_bytes"] = total
                extra_info["downloaded_bytes"] = downloaded
                extra_info["percent"] = p * 100

            if speed and speed > 0:
                extra_info["speed"] = speed
                speed_str = _format_speed(speed)
                progress_msg = f"下载中 {speed_str}"

            if eta is not None and eta > 0:
                extra_info["eta_seconds"] = eta
                eta_str = _format_eta(eta)
                progress_msg = f"{progress_msg} · 剩余 {eta_str}" if progress_msg != "下载中" else f"剩余 {eta_str}"

            # 根据回调签名调用
            if param_count >= 3:
                progress_cb(min(max(p, 0.0), 1.0), progress_msg, extra_info)  # type: ignore[call-arg]
            else:
                progress_cb(min(max(p, 0.0), 1.0), progress_msg)  # type: ignore[call-arg]
        elif status == "finished":
            if param_count >= 3:
                progress_cb(1.0, "下载完成", {})  # type: ignore[call-arg]
            else:
                progress_cb(1.0, "下载完成")  # type: ignore[call-arg]

        # 提取 uploader 信息（从第一个视频条目）
        if uploader_info is None:
            entry = d.get("info", {})
            if entry:
                uploader = entry.get("uploader") or entry.get("uploader_name") or entry.get("channel") or entry.get("channel_id")
                mid = entry.get("uploader_id") or entry.get("channel_id") or entry.get("mid")
                if uploader and mid:
                    uploader_info = UploaderInfo(
                        nickname=uploader,
                        mid=str(mid),
                        homepage_url=f"https://space.bilibili.com/{mid}",
                    )

    ydl_opts: dict[str, Any] = {
        "noplaylist": False,
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "overwrites": False,
        "continuedl": True,
        "consoletitle": False,
        "outtmpl": _build_output_template(downloads_path, "bilibili", "全部投稿"),
        "format": "best/bestvideo+bestaudio",
        "merge_output_format": "mp4",
        "retries": 5,
        "extractor_retries": 5,
        "sleep_interval": 2,
        "max_sleep_interval": 6,
    }

    if skip_existing:
        archive_path = downloads_path / ".bilibili-download-archive.txt"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        ydl_opts["download_archive"] = str(archive_path)

    from media_tools.core.config import get_app_config
    proxy = get_app_config().bilibili_proxy
    ydl_opts["proxy"] = proxy

    # Cookie 配置 - 转换为 Netscape 格式文件
    # expires 使用 2038-01-01 (2145888000) 避免 session cookie 立即过期
    cookie_content: Optional[str] = None
    if cookie:
        cookie_lines = ["# Netscape HTTP Cookie File"]
        for part in cookie.split(";"):
            part = part.strip()
            if "=" in part:
                key, value = part.split("=", 1)
                cookie_lines.append(f".bilibili.com	TRUE	/	FALSE	2145888000	{key}	{value}")
        cookie_content = "\n".join(cookie_lines)

    headers: dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
    }
    ydl_opts["http_headers"] = headers

    if max_counts is not None:
        ydl_opts["playlistend"] = max_counts

    if cookie_content is not None:
        with managed_temp_file(mode='w', suffix='.txt') as (f, cookie_path):
            f.write(cookie_content)
            f.flush()
            ydl_opts["cookiefile"] = cookie_path
            try:
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
            except BaseException:
                # extract_info 抛错时立刻 unregister，否则 _cancel_flags 内存泄漏
                if task_id:
                    unregister_cancel_flag(task_id)
                raise
    else:
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except BaseException:
            if task_id:
                unregister_cancel_flag(task_id)
            raise

    # 尝试从 info 中提取 uploader 信息（如果 hook 没有捕获到）
    if uploader_info is None and isinstance(info, dict):
        uploader = info.get("uploader") or info.get("channel") or info.get("uploader_name")
        mid = info.get("uploader_id") or info.get("channel_id") or info.get("mid")
        if uploader and mid:
            uploader_info = UploaderInfo(
                nickname=uploader,
                mid=str(mid),
                homepage_url=f"https://space.bilibili.com/{mid}",
            )

    new_files: list[str] = []
    if isinstance(info, dict):
        requested = info.get("requested_downloads") or []
        for item in requested:
            fp = item.get("filepath")
            if fp and Path(fp).exists():
                new_files.append(str(Path(fp)))

    if not new_files:
        logger.warning("No files downloaded")

    # 下载完成后检查是否被取消
    if cancel_flag and cancel_flag.is_set():
        logger.info(f"下载被取消，清理已下载文件: task_id={task_id}")
        for f in new_files:
            try:
                Path(f).unlink()
            except OSError:
                pass
        if task_id:
            unregister_cancel_flag(task_id)
        return {"success": False, "new_files": [], "cancelled": True}

    if task_id:
        unregister_cancel_flag(task_id)

    # 把每个已下载文件落到 media_assets，让 B 站视频与其它平台一样受视频级状态机管理
    try:
        _persist_bilibili_assets_to_db(info, new_files, downloads_path, uploader_info)
    except Exception as e:  # noqa: BLE001  入库失败不应阻塞下载流程
        logger.warning(f"bilibili 下载入库失败: {e}")

    result = {"success": True, "new_files": new_files}
    if uploader_info:
        result["uploader"] = {
            "nickname": uploader_info.nickname,
            "mid": uploader_info.mid,
            "homepage_url": uploader_info.homepage_url,
        }
    return result

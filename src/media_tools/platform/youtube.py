from __future__ import annotations

import contextlib
import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from media_tools.bilibili.task_control import (
    register_cancel_flag,
    unregister_cancel_flag,
)
from media_tools.bilibili.temp_files import managed_temp_file
from media_tools.common.paths import get_download_path
from media_tools.logger import get_logger

logger = get_logger("youtube")


@dataclass
class UploaderInfo:
    """YouTube 频道信息"""

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


def sanitize_filename(name: str) -> str:
    value = name or ""
    value = re.sub(r'[<>:"/\\|?*]', "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _build_output_template(base_dir: Path, creator_folder: str) -> str:
    safe_creator = sanitize_filename(creator_folder) or "youtube"
    target_dir = base_dir / safe_creator
    target_dir.mkdir(parents=True, exist_ok=True)
    return str(target_dir / "%(title)s__%(id)s.%(ext)s")


def _iter_yt_dlp_entries(info: dict | None):
    """扁平化 yt-dlp info：单视频返回自身，playlist/channel 递归其 entries。"""
    if not isinstance(info, dict):
        return
    entries = info.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            yield from _iter_yt_dlp_entries(entry)
    else:
        yield info


def fetch_youtube_channel_info(url: str) -> dict[str, str]:
    """提取 YouTube 频道的基本元数据（包括真正的 channel_id 和 nickname）"""
    if YoutubeDL is None:
        raise RuntimeError("yt-dlp not installed")

    ydl_opts = {
        "skip_download": True,
        "playlistend": 1,
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
    }

    # 获取 YouTube 代理
    from media_tools.core.config import get_app_config, normalize_download_proxy

    proxy = normalize_download_proxy(get_app_config().youtube_proxy)
    if proxy is not None:
        ydl_opts["proxy"] = proxy

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise ValueError("无法提取 YouTube 频道信息")

    # YouTube API / webpage_url 返回 of info 对象在 playlist 时结构通常包含 channel, channel_id, channel_url
    nickname = info.get("channel") or info.get("uploader") or info.get("title") or "YouTube Channel"
    channel_id = info.get("channel_id") or info.get("id") or ""

    if not channel_id:
        raise ValueError("无法获取 YouTube 频道 ID")

    homepage_url = info.get("channel_url") or info.get("webpage_url") or f"https://www.youtube.com/channel/{channel_id}"

    return {
        "nickname": nickname,
        "channel_id": channel_id,
        "homepage_url": homepage_url,
    }


def download_channel_by_url(
    url: str,
    max_counts: int | None = None,
    skip_existing: bool = True,
    progress_cb: ProgressCallback | None = None,
    task_id: str | None = None,
    disable_auto_transcribe: bool = False,
    force: bool = False,
) -> dict:
    if YoutubeDL is None:
        raise RuntimeError("yt-dlp not installed")

    downloads_path = get_download_path()

    # 从账号池获取 youtube cookie
    from media_tools.core.cookie_manager import get_cookie_manager
    cookie = get_cookie_manager().get_cookie("youtube")

    uploader_info: UploaderInfo | None = None
    cancel_flag = register_cancel_flag(task_id) if task_id else None

    mode_label = "全量" if force else ("增量" if skip_existing else "强制")
    logger.info(f"[YouTube下载] 开始 {mode_label} 下载: {url[:80]}..." + (f" (task={task_id})" if task_id else ""))

    def hook(d: dict):
        nonlocal uploader_info

        # 检查是否被取消（线程安全）
        if cancel_flag and cancel_flag.is_set():
            raise RuntimeError(f"下载已取消: task_id={task_id}")

        if not progress_cb:
            return

        try:
            sig = inspect.signature(progress_cb)
            param_count = len(sig.parameters)
        except (ValueError, TypeError):
            param_count = 2

        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            speed = d.get("speed") or 0
            eta = d.get("eta")

            p = (downloaded / total) if total else 0.0
            progress_msg = "下载中"

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

            if param_count >= 3:
                progress_cb(min(max(p, 0.0), 1.0), progress_msg, extra_info)
            else:
                progress_cb(min(max(p, 0.0), 1.0), progress_msg)
        elif status == "finished":
            if param_count >= 3:
                progress_cb(1.0, "下载完成", {})
            else:
                progress_cb(1.0, "下载完成")

        if uploader_info is None:
            entry = d.get("info", {})
            if entry:
                uploader = entry.get("channel") or entry.get("uploader") or entry.get("uploader_name")
                channel_id = entry.get("channel_id") or entry.get("uploader_id")
                if uploader and channel_id:
                    uploader_info = UploaderInfo(
                        nickname=uploader,
                        mid=str(channel_id),
                        homepage_url=f"https://www.youtube.com/channel/{channel_id}",
                    )

    ydl_opts: dict[str, Any] = {
        "noplaylist": False,
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "overwrites": force,
        "continuedl": not force,
        "consoletitle": False,
        "outtmpl": _build_output_template(downloads_path, "youtube"),
        # 优先 AVC(H.264)，避免转写时报错
        "format": "best[vcodec~='^avc']/bestvideo[vcodec~='^avc']+bestaudio/best/bestvideo+bestaudio",
        "merge_output_format": "mp4",
        "retries": 5,
        "extractor_retries": 5,
        "sleep_interval": 2,
        "max_sleep_interval": 6,
    }

    if skip_existing:
        archive_path = downloads_path / ".youtube-download-archive.txt"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        ydl_opts["download_archive"] = str(archive_path)

    from media_tools.core.config import get_app_config, normalize_download_proxy

    proxy = normalize_download_proxy(get_app_config().youtube_proxy)
    if proxy is not None:
        ydl_opts["proxy"] = proxy

    import shutil
    if shutil.which("aria2c"):
        ydl_opts["external_downloader"] = "aria2c"
        ydl_opts["external_downloader_args"] = {
            "default": ["-x", "16", "-s", "16", "-j", "16", "-k", "1M"]
        }

    # Cookie 转换
    cookie_content: str | None = None
    if cookie:
        cookie_lines = ["# Netscape HTTP Cookie File"]
        for part in cookie.split(";"):
            part = part.strip()
            if "=" in part:
                key, value = part.split("=", 1)
                cookie_lines.append(f".youtube.com	TRUE	/	FALSE	2145888000	{key}	{value}")
        cookie_content = "\n".join(cookie_lines)

    headers: dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.youtube.com/",
    }
    ydl_opts["http_headers"] = headers

    if max_counts is not None:
        ydl_opts["playlistend"] = max_counts

    def _run_download(ydl_opts_inner: dict[str, Any]) -> dict:
        nonlocal uploader_info
        try:
            preflight_opts = {
                k: v
                for k, v in ydl_opts_inner.items()
                if k not in ("progress_hooks", "overwrites", "continuedl", "download_archive")
            }
            preflight_opts["skip_download"] = True
            preflight_opts["extract_flat"] = True
            with YoutubeDL(preflight_opts) as pre_ydl:
                pre_info = pre_ydl.extract_info(url, download=False)
            if isinstance(pre_info, dict):
                nick = pre_info.get("channel") or pre_info.get("uploader") or pre_info.get("uploader_name") or ""
                channel_id = pre_info.get("channel_id") or pre_info.get("uploader_id") or ""
                if nick and channel_id:
                    uploader_info = UploaderInfo(
                        nickname=nick,
                        mid=str(channel_id),
                        homepage_url=f"https://www.youtube.com/channel/{channel_id}",
                    )
                    ydl_opts_inner["outtmpl"] = _build_output_template(downloads_path, nick)
        except Exception:  # noqa: BLE001
            logger.debug("预提取 YouTube 频道信息失败，使用默认路径", exc_info=True)

        with YoutubeDL(ydl_opts_inner) as ydl:
            return ydl.extract_info(url, download=True)

    if cookie_content is not None:
        with managed_temp_file(mode="w", suffix=".txt") as (f, cookie_path):
            f.write(cookie_content)
            f.flush()
            ydl_opts["cookiefile"] = cookie_path
            try:
                info = _run_download(ydl_opts)
            except BaseException:
                if task_id:
                    unregister_cancel_flag(task_id)
                raise
    else:
        try:
            info = _run_download(ydl_opts)
        except BaseException:
            if task_id:
                unregister_cancel_flag(task_id)
            raise

    if uploader_info is None and isinstance(info, dict):
        uploader = info.get("channel") or info.get("uploader") or info.get("uploader_name")
        channel_id = info.get("channel_id") or info.get("uploader_id")
        if uploader and channel_id:
            uploader_info = UploaderInfo(
                nickname=uploader,
                mid=str(channel_id),
                homepage_url=f"https://www.youtube.com/channel/{channel_id}",
            )

    new_files: list[str] = []
    skipped_count = 0
    failed_count = 0
    total_entries = 0

    if isinstance(info, dict):
        seen: set[str] = set()
        for entry in _iter_yt_dlp_entries(info):
            total_entries += 1
            yt_id = entry.get("id") or "?"

            fp = entry.get("filepath")
            if fp and Path(fp).exists():
                resolved = str(Path(fp).resolve())
                if resolved not in seen:
                    seen.add(resolved)
                    new_files.append(str(Path(fp)))
                    continue

            found = False
            for item in entry.get("requested_downloads") or []:
                fp = item.get("filepath")
                if fp and Path(fp).exists():
                    resolved = str(Path(fp).resolve())
                    if resolved not in seen:
                        seen.add(resolved)
                        new_files.append(str(Path(fp)))
                        found = True
                        break

            if not found:
                err = entry.get("error") or ""
                if err:
                    failed_count += 1
                    logger.debug(f"[YouTube下载] 视频 {yt_id} 下载失败: {err}")
                else:
                    skipped_count += 1
                    logger.debug(f"[YouTube下载] 视频 {yt_id} 已存在或跳过")

    if new_files:
        logger.info(
            f"[YouTube下载] 完成 — 新下载 {len(new_files)} 个"
            f"{'，跳过 ' + str(skipped_count) + ' 个' if skipped_count else ''}"
            f"{'，失败 ' + str(failed_count) + ' 个' if failed_count else ''}"
            f" (共 {total_entries} 个视频)"
        )
    elif total_entries > 0:
        if skipped_count and not failed_count:
            logger.info(f"[YouTube下载] 完成 — 全部 {skipped_count} 个视频已存在（无新文件）")
        elif failed_count:
            logger.warning(f"[YouTube下载] 完成 — {failed_count} 个下载失败，{skipped_count} 个已存在")
        else:
            logger.warning(f"[YouTube下载] 完成 — 无新文件 ({total_entries} 个视频)")
    else:
        logger.warning("[YouTube下载] 完成 — 未获取到任何视频")

    if cancel_flag and cancel_flag.is_set():
        logger.info(f"下载被取消，清理已下载文件: task_id={task_id}")
        for f in new_files:
            with contextlib.suppress(OSError):
                Path(f).unlink()
        if task_id:
            unregister_cancel_flag(task_id)
        return {"success": False, "new_files": [], "cancelled": True}

    if task_id:
        unregister_cancel_flag(task_id)

    try:
        _persist_youtube_assets_to_db(info, new_files, downloads_path, uploader_info)
    except Exception as e:
        logger.warning(f"youtube 下载入库失败: {e}")

    result = {"success": True, "new_files": new_files}
    if uploader_info:
        result["uploader"] = {
            "nickname": uploader_info.nickname,
            "mid": uploader_info.mid,
            "homepage_url": uploader_info.homepage_url,
        }
    return result


def _persist_youtube_assets_to_db(
    info: dict | None,
    new_files: list[str],
    downloads_path: Path,
    uploader_info: UploaderInfo | None,
) -> None:
    if not new_files:
        return

    from media_tools.assets.service import MediaAssetService

    new_files_resolved = {str(Path(p).resolve()): p for p in new_files}

    for entry in _iter_yt_dlp_entries(info):
        yt_id = entry.get("id")
        if not yt_id:
            continue

        requested = entry.get("requested_downloads") or []
        downloaded_path: Path | None = None
        for item in requested:
            fp = item.get("filepath")
            if not fp:
                continue
            resolved = str(Path(fp).resolve())
            if resolved in new_files_resolved:
                downloaded_path = Path(fp)
                break
        if downloaded_path is None:
            # fallback: check entry itself filepath
            fp = entry.get("filepath")
            if fp and str(Path(fp).resolve()) in new_files_resolved:
                downloaded_path = Path(fp)

        if downloaded_path is None:
            continue

        mid = entry.get("channel_id") or entry.get("uploader_id") or (uploader_info.mid if uploader_info else "")
        if not mid:
            mid = "unknown"

        creator_uid = f"youtube:{mid}"
        asset_id = f"youtube:{yt_id}"

        title = entry.get("title") or downloaded_path.stem
        duration = entry.get("duration")
        duration_int = int(duration) if isinstance(duration, (int, float)) else None
        source_url = entry.get("webpage_url") or entry.get("original_url") or f"https://www.youtube.com/watch?v={yt_id}"

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
            source_platform="youtube",
            source_url=source_url,
            folder_path=folder_path,
            duration=duration_int,
        )


def cancel_download(task_id: str) -> None:
    from media_tools.bilibili.task_control import cancel_download as bilibili_cancel
    bilibili_cancel(task_id)

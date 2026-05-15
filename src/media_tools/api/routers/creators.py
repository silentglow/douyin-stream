import asyncio
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from media_tools.common.paths import get_download_path, get_transcripts_path
from media_tools.store.db import get_db_connection, resolve_safe_path, resolve_query_value
from media_tools.creators.repository import CreatorRepository
from media_tools.assets.repository import AssetRepository
from media_tools.services.bilibili_nickname import fetch_bilibili_nickname
import os
import re
import sqlite3
import shutil
import logging
import threading
import time
from pydantic import BaseModel
from pathlib import Path

router = APIRouter(prefix="/api/v1/creators", tags=["creators"], redirect_slashes=False)
logger = logging.getLogger(__name__)

_DISK_COUNTS_TTL_SECONDS = 10.0
_disk_counts_cache: dict[str, tuple[float, dict[str, int]]] = {}
_disk_counts_lock = threading.Lock()


def _scan_creator_disk_counts(folder_name: str) -> dict[str, int]:
    download_dir = get_download_path() / folder_name
    transcripts_dir = get_transcripts_path() / folder_name

    from collections import Counter

    media_counts: Counter[str] = Counter()
    transcript_counts: Counter[str] = Counter()
    suffix_re = re.compile(r"_\d+$")
    try:
        from media_tools.transcribe.media_extensions import MEDIA_EXTENSIONS
        exts = set(MEDIA_EXTENSIONS)
    except ImportError:
        exts = {".mp4"}

    try:
        if download_dir.is_dir():
            for p in download_dir.rglob("*"):
                if p.is_file() and p.suffix.lower() in exts:
                    base = suffix_re.sub("", p.stem)
                    media_counts[base] += 1
    except OSError:
        media_counts = Counter()

    try:
        if transcripts_dir.is_dir():
            for p in transcripts_dir.rglob("*"):
                if not p.is_file():
                    continue
                if ".cache" in p.parts:
                    continue
                if p.suffix.lower() in {".md", ".docx"}:
                    base = suffix_re.sub("", p.stem)
                    transcript_counts[base] += 1
    except OSError:
        transcript_counts = Counter()

    keys = set(media_counts.keys()) | set(transcript_counts.keys())
    disk_assets = sum(max(media_counts.get(k, 0), transcript_counts.get(k, 0)) for k in keys)
    pending = sum(max(media_counts.get(k, 0) - transcript_counts.get(k, 0), 0) for k in keys)
    completed = sum(transcript_counts.values())

    return {
        "disk_asset_count": disk_assets,
        "disk_transcript_completed_count": completed,
        "disk_transcript_pending_count": pending,
    }


def _get_creator_folder_name(creator: dict) -> str:
    nickname = str(creator.get("nickname") or "").strip()
    uid = str(creator.get("uid") or "").strip()

    candidates: list[str] = []
    if nickname:
        candidates.append(nickname)
        try:
            from media_tools.douyin.utils.config import sanitize_folder_name

            candidates.append(sanitize_folder_name(nickname))
        except ImportError:
            pass
        value = re.sub(r'[<>"/\\|?*]', "", nickname).strip()
        value = re.sub(r"\.+", "_", value).strip()
        if value:
            candidates.append(value)

    if uid:
        candidates.append(uid)

    seen: set[str] = set()
    deduped: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            deduped.append(c)

    download_base = get_download_path()
    transcripts_base = get_transcripts_path()
    for c in deduped:
        if (download_base / c).exists() or (transcripts_base / c).exists():
            return c

    return deduped[0] if deduped else uid


def _get_cached_creator_disk_counts(folder_name: str) -> dict[str, int]:
    now = time.monotonic()
    with _disk_counts_lock:
        hit = _disk_counts_cache.get(folder_name)
        if hit and hit[0] > now:
            return dict(hit[1])

    counts = _scan_creator_disk_counts(folder_name)
    with _disk_counts_lock:
        _disk_counts_cache[folder_name] = (now + _DISK_COUNTS_TTL_SECONDS, counts)
    return dict(counts)


class CreatorCreateRequest(BaseModel):
    url: str


class ToggleAutoSyncRequest(BaseModel):
    auto_sync: bool


@router.get("")
def list_creators(
    limit: Optional[int] = Query(default=None, ge=1, le=500),
    offset: Optional[int] = Query(default=None, ge=0),
):
    limit = resolve_query_value(limit, 100)
    offset = resolve_query_value(offset, 0)
    try:
        creators = CreatorRepository.list_with_stats(limit=limit, offset=offset)
        for creator in creators:
            folder_name = _get_creator_folder_name(creator)
            creator.update(_get_cached_creator_disk_counts(folder_name))
        return creators
    except sqlite3.Error:
        logger.exception("list_creators failed")
        raise HTTPException(status_code=500, detail="获取创作者列表失败")


@router.post("")
async def create_creator(req: CreatorCreateRequest):
    try:
        if "bilibili.com" in req.url or "b23.tv" in req.url:
            from media_tools.bilibili.core.url_parser import BilibiliUrlKind, normalize_bilibili_url
            from media_tools.bilibili.utils.naming import build_bilibili_creator_uid

            parsed = normalize_bilibili_url(req.url)
            if parsed.kind is not BilibiliUrlKind.SPACE or not parsed.mid:
                raise HTTPException(status_code=400, detail="暂只支持 B 站 UP 主空间链接（space.bilibili.com/<mid>）")

            uid = build_bilibili_creator_uid(parsed.mid)

            # 尝试获取B站用户真实昵称（异步，不阻塞线程池）
            nickname = parsed.mid
            homepage_url = f"https://space.bilibili.com/{parsed.mid}"
            try:
                nickname = await fetch_bilibili_nickname(parsed.mid)
            except (RuntimeError, OSError, ValueError) as e:
                logger.warning(f"获取B站昵称失败: {e}")
                # 使用 mid 作为后备

            created = CreatorRepository.upsert_bilibili_creator(
                uid=uid,
                sec_user_id=parsed.mid,
                nickname=nickname,
                homepage_url=homepage_url,
            )

            return {
                "status": "created" if created else "exists",
                "creator": {
                    "uid": uid,
                    "nickname": nickname,
                    "sec_user_id": parsed.mid,
                    "platform": "bilibili",
                    "homepage_url": homepage_url,
                    "sync_status": "active",
                },
            }

        from media_tools.douyin.core.following_mgr import add_user

        success, user_info = await asyncio.to_thread(add_user, req.url)
        if success:
            return {"status": "created", "creator": user_info}
        if user_info:
            return {"status": "exists", "creator": user_info}
        raise HTTPException(status_code=400, detail="无法添加创作者，请检查主页链接是否有效")
    except HTTPException:
        raise
    except (RuntimeError, OSError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{uid}/auto-sync")
def toggle_creator_auto_sync(uid: str, req: ToggleAutoSyncRequest):
    """切换创作者自动同步状态"""
    try:
        if not CreatorRepository.exists(uid):
            raise HTTPException(status_code=404, detail="Creator not found")
        CreatorRepository.toggle_auto_sync(uid, req.auto_sync)
        return {"status": "success", "auto_sync": req.auto_sync}
    except HTTPException:
        raise
    except (sqlite3.Error, RuntimeError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{uid}")
def delete_creator(uid: str):
    try:
        nickname, assets = CreatorRepository.delete_with_assets(uid)
        if nickname is None:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Phase 2: Delete files after DB commit (outside transaction)
        for asset in assets:
            video_path = asset.get('video_path')
            transcript_name = asset.get('transcript_path')

            # Delete video file
            if video_path:
                full_video_path = resolve_safe_path(get_download_path(), video_path)
                if full_video_path and full_video_path.exists():
                    try:
                        full_video_path.unlink()
                    except OSError as e:
                        logger.warning(f"删除视频文件失败: {full_video_path} ({e})")

            # Delete transcript file
            if transcript_name:
                full_transcript_path = resolve_safe_path(get_transcripts_path(), transcript_name)
                if full_transcript_path and full_transcript_path.exists():
                    try:
                        full_transcript_path.unlink()
                    except OSError as e:
                        logger.warning(f"删除转写文件失败: {full_transcript_path} ({e})")

        # Also try to delete the creator's download folder if it exists
        # 重名保护：仅当没有其他 creator 仍以此 folder_name 作为 nickname/uid 时才删除
        download_base = get_download_path().resolve()
        for folder_name in [nickname, uid]:
            if not folder_name:
                continue
            creator_dir = resolve_safe_path(download_base, folder_name)
            if not (creator_dir and creator_dir.exists() and creator_dir.is_dir()):
                continue
            try:
                with get_db_connection() as conn:
                    in_use = conn.execute(
                        "SELECT 1 FROM creators WHERE nickname = ? OR uid = ? LIMIT 1",
                        (folder_name, folder_name),
                    ).fetchone()
            except sqlite3.Error as e:
                logger.warning(f"检查 {folder_name} 是否被复用失败: {e}")
                in_use = True  # 安全侧失败：宁可不删
            if in_use:
                logger.info(f"目录 {creator_dir} 仍被其他创作者使用，跳过删除")
                continue
            try:
                shutil.rmtree(creator_dir)
            except OSError as e:
                logger.warning(f"删除创作者目录失败: {creator_dir} ({e})")

        return {"status": "success", "message": f"Creator {uid} and all their assets deleted successfully"}

    except HTTPException:
        raise
    except (sqlite3.Error, RuntimeError) as e:
        raise HTTPException(status_code=500, detail=str(e))

import asyncio
import logging
import re
import shutil
import sqlite3
import threading
import time

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

from media_tools.bilibili.nickname import fetch_bilibili_profile
from media_tools.common.paths import get_download_path, get_transcripts_path
from media_tools.creators.repository import CreatorRepository
from media_tools.store.db import get_db_connection, resolve_query_value, resolve_safe_path

router = APIRouter(prefix="/api/v1/creators", tags=["creators"], redirect_slashes=False)
logger = logging.getLogger(__name__)

_DISK_COUNTS_TTL_SECONDS = 60.0
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


class BulkAutoSyncRequest(BaseModel):
    auto_sync: bool = True


@router.get("")
def list_creators(
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int | None = Query(default=None, ge=0),
):
    limit = resolve_query_value(limit, 500)
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
            from media_tools.bilibili.naming import build_bilibili_creator_uid
            from media_tools.bilibili.url_parser import BilibiliUrlKind, normalize_bilibili_url

            parsed = normalize_bilibili_url(req.url)
            if parsed.kind is not BilibiliUrlKind.SPACE or not parsed.mid:
                raise HTTPException(status_code=400, detail="暂只支持 B 站 UP 主空间链接（space.bilibili.com/<mid>）")

            uid = build_bilibili_creator_uid(parsed.mid)

            # 尝试获取B站用户真实昵称+头像（异步，不阻塞线程池）
            nickname = parsed.mid
            avatar = ""
            homepage_url = f"https://space.bilibili.com/{parsed.mid}"
            try:
                profile = await fetch_bilibili_profile(parsed.mid)
                nickname = profile["nickname"]
                avatar = profile["avatar"]
            except (RuntimeError, OSError, ValueError) as e:
                logger.warning(f"获取B站资料失败: {e}")
                # 使用 mid 作为后备

            created = CreatorRepository.upsert_bilibili_creator(
                uid=uid,
                sec_user_id=parsed.mid,
                nickname=nickname,
                homepage_url=homepage_url,
                avatar=avatar,
            )

            return {
                "status": "created" if created else "exists",
                "creator": {
                    "uid": uid,
                    "nickname": nickname,
                    "sec_user_id": parsed.mid,
                    "platform": "bilibili",
                    "homepage_url": homepage_url,
                    "avatar": avatar,
                    "sync_status": "active",
                },
            }

        elif "youtube.com" in req.url or "youtu.be" in req.url:
            from media_tools.platform.youtube import fetch_youtube_channel_info

            try:
                info = await asyncio.to_thread(fetch_youtube_channel_info, req.url)
                nickname = info.get("nickname") or "YouTube Channel"
                channel_id = info.get("channel_id") or ""
                homepage_url = info.get("homepage_url") or req.url
                avatar = info.get("avatar") or ""
            except Exception as e:
                logger.error(f"提取 YouTube 频道信息失败: {e}")
                raise HTTPException(status_code=400, detail=f"无法获取 YouTube 频道信息，请检查链接或网络代理: {e}")

            if not channel_id:
                raise HTTPException(status_code=400, detail="无法解析 YouTube 频道 ID")

            uid = f"youtube:{channel_id}"
            created = CreatorRepository.upsert_youtube_creator(
                uid=uid,
                sec_user_id=channel_id,
                nickname=nickname,
                homepage_url=homepage_url,
                avatar=avatar,
            )

            return {
                "status": "created" if created else "exists",
                "creator": {
                    "uid": uid,
                    "nickname": nickname,
                    "sec_user_id": channel_id,
                    "platform": "youtube",
                    "homepage_url": homepage_url,
                    "avatar": avatar,
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
def toggle_creator_auto_sync(*, uid: str = Path(..., min_length=1, max_length=128), req: ToggleAutoSyncRequest):
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


@router.post("/auto-sync/bulk")
def bulk_set_auto_sync(req: BulkAutoSyncRequest):
    """一键设置全部创作者的自动同步开关。"""
    try:
        updated = CreatorRepository.set_all_auto_sync(req.auto_sync)
        return {"status": "success", "auto_sync": req.auto_sync, "updated": updated}
    except (sqlite3.Error, RuntimeError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{uid}/refollow")
def refollow_creator(*, uid: str = Path(..., min_length=1, max_length=128)):
    """恢复已停跟的创作者（文稿本来就在，只改状态）。"""
    try:
        if not CreatorRepository.exists(uid):
            raise HTTPException(status_code=404, detail="Creator not found")
        ok = CreatorRepository.refollow(uid)
        return {"status": "success", "refollowed": ok}
    except HTTPException:
        raise
    except (sqlite3.Error, RuntimeError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{uid}")
def delete_creator(
    uid: str = Path(..., min_length=1, max_length=128),
    keep_content: bool = Query(
        False,
        description="true=停跟并保留文稿/素材；false=连同库记录与本地文件一并删除",
    ),
):
    try:
        if keep_content:
            result = CreatorRepository.unfollow_keep_content(uid)
            if result is None:
                raise HTTPException(status_code=404, detail="Creator not found")
            return {
                "status": "success",
                "mode": "keep_content",
                "message": "已停止关注，文稿与素材仍保留",
                "creator": result,
            }

        nickname, assets = CreatorRepository.delete_with_assets(uid)
        if nickname is None:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Phase 2: Delete files after DB commit (outside transaction)
        for asset in assets:
            video_path = asset.get("video_path")
            transcript_name = asset.get("transcript_path")

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
        transcripts_base = get_transcripts_path().resolve()
        for folder_name in [nickname, uid]:
            if not folder_name:
                continue
            for base in (download_base, transcripts_base):
                creator_dir = resolve_safe_path(base, folder_name)
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

        return {
            "status": "success",
            "mode": "purge",
            "message": f"Creator {uid} and all their assets deleted successfully",
            "deleted_assets": len(assets),
        }

    except HTTPException:
        raise
    except (sqlite3.Error, RuntimeError) as e:
        raise HTTPException(status_code=500, detail=str(e))

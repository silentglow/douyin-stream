#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频下载模块 - 单个/批量/交互下载（直接调用 F2 API）
"""

from typing import Optional, Union
import asyncio
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import re

from media_tools.douyin.core.f2_helper import get_f2_kwargs as _build_f2_kwargs
from media_tools.logger import get_logger
from media_tools.store.db import resolve_safe_path
from media_tools.core.task_progress import Stage
from media_tools.douyin.core.file_ops import _clean_video_title, _reorganize_files, _update_last_fetch_time

logger = get_logger('downloader')

from media_tools.douyin.core.ui import (
    error,
    info,
    print_header,
    print_status,
    success,
    warning,
    ProgressBar,
)
from media_tools.douyin.core.config_mgr import get_config
from media_tools.douyin.core.following_mgr import list_users


MIN_VIDEO_BYTES = 10240  # 10KB（与 pipeline/task_helpers.py 保持一致）


def _is_probably_valid_mp4(file_path: Path) -> bool:
    try:
        if not file_path.exists() or not file_path.is_file():
            return False
        if file_path.stat().st_size < MIN_VIDEO_BYTES:
            return False
        with file_path.open("rb") as f:
            header = f.read(16)
        return len(header) >= 12 and header[4:8] == b"ftyp"
    except OSError:
        return False


def _extract_aweme_id_from_filename(stem: str) -> Optional[str]:
    m = re.search(r"\d{15,}", stem)
    return m.group(0) if m else None


def _scan_local_aweme_files(user_path: Path) -> tuple[set[str], set[str], dict[str, list[Path]]]:
    existing: set[str] = set()
    corrupt: set[str] = set()
    corrupt_files: dict[str, list[Path]] = {}

    if not user_path.exists():
        return existing, corrupt, corrupt_files

    for f in user_path.glob("*.mp4"):
        aweme_id = _extract_aweme_id_from_filename(f.stem)
        if not aweme_id:
            continue
        existing.add(aweme_id)
        if not _is_probably_valid_mp4(f):
            corrupt.add(aweme_id)
            corrupt_files.setdefault(aweme_id, []).append(f)

    return existing, corrupt, corrupt_files


def _select_videos_to_download(
    video_list: list,
    existing_aweme_ids: set[str],
    corrupt_files: dict[str, list[Path]],
) -> tuple[list, int]:
    new_videos: list = []
    skipped = 0

    for video in video_list:
        aweme_id = (
            video.get("aweme_id", "") if isinstance(video, dict) else getattr(video, "aweme_id", "")
        )
        aweme_id = str(aweme_id or "")

        if aweme_id and aweme_id in corrupt_files:
            for p in corrupt_files.get(aweme_id) or []:
                try:
                    p.unlink()
                except OSError:
                    pass
            new_videos.append(video)
            existing_aweme_ids.add(aweme_id)
            continue

        if aweme_id and aweme_id not in existing_aweme_ids:
            new_videos.append(video)
            existing_aweme_ids.add(aweme_id)
        else:
            skipped += 1

    return new_videos, skipped


def _get_skill_dir():
    """获取项目根目录"""
    return get_config().project_root


def _get_f2_kwargs() -> dict:
    """获取 F2 所需的配置参数"""
    return _build_f2_kwargs()


def _prepare_f2_temp_dir(downloads_path: Path) -> Path:
    """清理并重建 F2 临时目录，避免残留文件和缺失父目录。"""
    f2_temp_path = downloads_path / "douyin"
    if f2_temp_path.exists():
        if f2_temp_path.is_dir():
            shutil.rmtree(f2_temp_path)
        else:
            f2_temp_path.unlink()
        logger.info("已清理 F2 临时目录")
        logger.info(info("[清理] F2 临时目录"))
    f2_temp_path.mkdir(parents=True, exist_ok=True)
    return f2_temp_path


def _create_video_metadata_table():
    """确保视频元数据表存在"""
    config = get_config()
    db_path = config.get_db_path()
    conn = None
    try:
        from media_tools.store.db import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS video_metadata (
                    aweme_id TEXT PRIMARY KEY,
                    uid TEXT NOT NULL,
                    nickname TEXT,
                    desc TEXT,
                    create_time INTEGER,
                    duration INTEGER,
                    digg_count INTEGER DEFAULT 0,
                    comment_count INTEGER DEFAULT 0,
                    collect_count INTEGER DEFAULT 0,
                    share_count INTEGER DEFAULT 0,
                    play_count INTEGER DEFAULT 0,
                    local_filename TEXT,
                    file_size INTEGER,
                    fetch_time INTEGER
                )
            """
            )

            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_video_uid ON video_metadata(uid)"
            )

            try:
                cursor.execute("ALTER TABLE video_metadata ADD COLUMN nickname TEXT")
            except sqlite3.OperationalError:
                pass

            conn.commit()
    finally:
        if conn:
            conn.close()


def _save_video_metadata_from_raw(raw_data: dict, nickname: str = ""):
    """从原始 API 响应中提取并保存视频统计数据"""
    aweme_list = raw_data.get("aweme_list", [])
    if not aweme_list:
        return 0

    config = get_config()
    db_path = config.get_db_path()
    conn = None
    try:
        from media_tools.store.db import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()

            fetch_time = int(datetime.now().timestamp())
            saved_count = 0

            for video in aweme_list:
                aweme_id = video.get("aweme_id", "")
                if not aweme_id:
                    continue

                stats = video.get("statistics", {}) or {}
                author = video.get("author", {}) or {}
                video_nickname = author.get("nickname", nickname)

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO video_metadata
                    (aweme_id, uid, nickname, desc, create_time, duration,
                     digg_count, comment_count, collect_count, share_count, play_count,
                     fetch_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        aweme_id,
                        author.get("uid", ""),
                        video_nickname,
                        video.get("desc", ""),
                        video.get("create_time", 0),
                        video.get("video", {}).get("duration", 0) if video.get("video") else 0,
                        stats.get("digg_count", 0),
                        stats.get("comment_count", 0),
                        stats.get("collect_count", 0),
                        stats.get("share_count", 0),
                        stats.get("play_count", 0),
                        fetch_time,
                    ),
                )
                saved_count += 1

            conn.commit()
            return saved_count
    finally:
        if conn:
            conn.close()


def _save_single_video_metadata(video: dict, nickname: str = "") -> int:
    """保存单个视频的元数据"""
    if not video:
        return 0

    aweme_id = video.get("aweme_id", "")
    if not aweme_id:
        return 0

    config = get_config()
    db_path = config.get_db_path()
    conn = None
    try:
        from media_tools.store.db import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()

            stats = video.get("statistics", {}) or {}
            author = video.get("author", {}) or {}
            video_nickname = (
                video.get("nickname")
                or author.get("nickname")
                or nickname
            )
            uid = (
                video.get("uid")
                or author.get("uid")
                or video.get("sec_user_id", "")
            )

            cursor.execute(
                """
                INSERT OR REPLACE INTO video_metadata
                (aweme_id, uid, nickname, desc, create_time, duration,
                 digg_count, comment_count, collect_count, share_count, play_count,
                 fetch_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    aweme_id,
                    uid,
                    video_nickname,
                    video.get("desc", ""),
                    video.get("create_time", 0),
                    video.get("video", {}).get("duration", 0) if video.get("video") else 0,
                    stats.get("digg_count", 0),
                    stats.get("comment_count", 0),
                    stats.get("collect_count", 0),
                    stats.get("share_count", 0),
                    stats.get("play_count", 0),
                    int(datetime.now().timestamp()),
                ),
            )

            conn.commit()
            return 1
    finally:
        if conn:
            conn.close()


def _rename_videos_in_downloads(nickname: str, uid: str, downloads_path: Path) -> Optional[str]:
    """重命名下载目录下的视频文件（包括已在目标子目录的情况）"""
    import re
    import sqlite3

    config = get_config()
    db_path = config.get_db_path()

    # 博主文件夹
    folder_name = nickname or uid
    user_dir = resolve_safe_path(downloads_path, folder_name)
    if not user_dir:
        logger.warning(f"Path traversal blocked for folder: {folder_name}")
        user_dir = resolve_safe_path(downloads_path, uid) or downloads_path
    user_dir.mkdir(parents=True, exist_ok=True)

    # 连接数据库获取该博主最近的视频标题
    try:
        from media_tools.store.db import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 查询该博主所有视频标题（不限数量，确保批量下载时全部能匹配）
            cursor.execute(
                "SELECT aweme_id, desc FROM video_metadata WHERE uid = ? ORDER BY fetch_time DESC",
                (uid,)
            )
            recent_videos = cursor.fetchall()

            if not recent_videos:
                return None

            # 构建 aweme_id -> 标题 映射
            title_map = {row[0]: row[1] for row in recent_videos}

            renamed_count = 0
            processed_count = 0
            db_updated = False

            # 只扫描当前博主的目录和 F2 临时目录（douyin/post/），
            # 绝不 rglob 整个 downloads_path，避免把其他博主的文件移过来
            MIN_VIDEO_BYTES = 10240  # 10KB
            scan_dirs = [user_dir]
            # F2 临时目录（下载后尚未整理的文件）
            f2_temp = downloads_path / "douyin" / "post"
            if f2_temp.is_dir():
                scan_dirs.append(f2_temp)
            # downloads_path 根目录（旧版 F2 可能直接下载到这里）
            for f_in_root in downloads_path.glob("*.mp4"):
                scan_dirs.append(f_in_root)

            files_to_process: list[Path] = []
            for scan_dir in scan_dirs:
                if scan_dir.is_file():
                    files_to_process.append(scan_dir)
                elif scan_dir.is_dir():
                    for f in scan_dir.rglob("*.mp4"):
                        files_to_process.append(f)

            for f in files_to_process:
                if f.stat().st_size < MIN_VIDEO_BYTES:
                    continue

                stem = f.stem

                # 方法0：直接从文件名提取 aweme_id（处理 F2 原始格式如 7620767195682364133_video.mp4）
                aweme_id = None
                aweme_match = re.match(r'^(\d{15,})(?:_video)?$', stem)
                if aweme_match:
                    candidate = aweme_match.group(1)
                    if candidate in title_map:
                        aweme_id = candidate
                    else:
                        # 不在 title_map 里，直接查 DB
                        cursor.execute("SELECT desc FROM video_metadata WHERE aweme_id = ?", (candidate,))
                        row = cursor.fetchone()
                        if row and row[0]:
                            title_map[candidate] = row[0]
                            aweme_id = candidate

                # 方法1：尝试从文件名匹配 title_map 中的 aweme_id
                if not aweme_id:
                    for vid in title_map.keys():
                        if vid in stem:
                            aweme_id = vid
                            break

                # 方法2：如果文件名不包含 aweme_id，使用标题关键词匹配
                if not aweme_id:
                    for vid, title in title_map.items():
                        # 提取标题中的中文关键词
                        clean_title = _clean_video_title(title)
                        # 检查标题中的连续中文是否出现在文件名中
                        chinese_words = re.findall(r'[\u4e00-\u9fa5]{2,}', clean_title)
                        for word in chinese_words[:3]:  # 取前3个关键词
                            if word in stem:
                                aweme_id = vid
                                break
                        if aweme_id:
                            break

                if aweme_id and aweme_id in title_map:
                    title = title_map[aweme_id]
                    clean_title = _clean_video_title(title)
                    clean_title = re.sub(r'[<>:"/\\|?*]', '', clean_title).strip()
                    if len(clean_title) > 60:
                        clean_title = clean_title[:60]

                    new_name = f"{clean_title}{f.suffix}"
                    dest = user_dir / new_name

                    # 如果文件名已经是清洗后的（与新名相同），跳过
                    if f.name == new_name and f.parent == user_dir:
                        # 更新数据库中的 local_filename
                        cursor.execute(
                            "UPDATE video_metadata SET local_filename = ? WHERE aweme_id = ?",
                            (new_name, aweme_id)
                        )
                        db_updated = True
                        continue

                    if not dest.exists():
                        shutil.move(str(f), str(dest))
                        processed_count += 1
                        renamed_count += 1
                        logger.info(info(f"  [重命名] {f.name[:40]}... -> {new_name[:40]}..."))
                    else:
                        counter = 1
                        while dest.exists():
                            new_name = f"{clean_title}_{counter}{f.suffix}"
                            dest = user_dir / new_name
                            counter += 1
                        shutil.move(str(f), str(dest))
                        processed_count += 1
                        renamed_count += 1

                    # 更新数据库中的 local_filename
                    cursor.execute(
                        "UPDATE video_metadata SET local_filename = ? WHERE aweme_id = ?",
                        (new_name, aweme_id)
                    )
                    db_updated = True
                else:
                    # 无法匹配 aweme_id，跳过——绝不移动无法确认归属的文件
                    # 之前的逻辑会把所有未匹配 mp4 移入当前博主目录，造成跨博主污染
                    pass

            if processed_count > 0:
                logger.info(info(f"  [整理] 已处理 {processed_count} 个文件到 {folder_name}/（{renamed_count} 个已重命名）"))
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"整理下载文件失败: {e}")

    return folder_name


def _sync_media_assets(uid: str, nickname: str, folder_name: str):
    """将 video_metadata 中的数据同步到全新的 V2 media_assets 表"""
    import re

    config = get_config()
    db_path = config.get_db_path()
    downloads_path = config.get_download_path()

    try:
        from media_tools.store.db import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 获取该用户的所有视频元数据
            cursor.execute("SELECT aweme_id, desc, duration FROM video_metadata WHERE uid = ?", (uid,))
            videos = cursor.fetchall()

            # 修复：优化文件查找算法，从O(N*M)降到O(N+M)
            # 先扫描一次所有文件，构建查找表
            user_dir = resolve_safe_path(downloads_path, folder_name)
            if not user_dir:
                logger.warning(f"Path traversal blocked for folder: {folder_name}")
                user_dir = resolve_safe_path(downloads_path, uid) or downloads_path
            file_lookup = {}  # {aweme_id: filename}
            keyword_lookup = {}  # {keyword: [filename, ...]}

            if user_dir and user_dir.exists():
                # 一次性获取所有mp4文件，过滤掉下载失败的垃圾文件
                MIN_VIDEO_BYTES = 10240  # 10KB
                all_files = [f for f in user_dir.glob("*.mp4") if f.stat().st_size >= MIN_VIDEO_BYTES]

                # 构建aweme_id查找表
                for f in all_files:
                    # 尝试从文件名提取aweme_id（15位及以上数字）
                    aweme_matches = re.findall(r'\d{15,}', f.stem)
                    for aweme_id in aweme_matches:
                        file_lookup[aweme_id] = f"{folder_name}/{f.name}"

                    # 构建关键词查找表（同一关键词对应多个文件时用列表保留）
                    clean_stem = f.stem.lower()
                    chinese_words = re.findall(r'[\u4e00-\u9fa5]{2,}', clean_stem)
                    for word in chinese_words:
                        keyword_lookup.setdefault(word, []).append(f"{folder_name}/{f.name}")

            # 方法0：先构建 aweme_id -> local_filename 的精确映射
            # _rename_videos_in_downloads 已在重命名时写入此字段
            local_filename_map: dict[str, str] = {}
            cursor.execute(
                "SELECT aweme_id, local_filename FROM video_metadata WHERE uid = ? AND local_filename IS NOT NULL AND local_filename != ''",
                (uid,)
            )
            for row in cursor.fetchall():
                local_filename_map[row[0]] = row[1]

            for aweme_id, desc, duration in videos:
                # 尝试在查找表中寻找该视频文件
                video_path = ""
                video_status = "pending"

                # 方法0：通过 video_metadata.local_filename 精确匹配（最可靠）
                if aweme_id in local_filename_map:
                    candidate = f"{folder_name}/{local_filename_map[aweme_id]}"
                    abs_path = downloads_path / candidate
                    if abs_path.exists():
                        video_path = candidate
                        video_status = "downloaded" if _is_probably_valid_mp4(abs_path) else "corrupt_file"

                # 方法1：通过aweme_id匹配 + 校验文件存在
                if not video_path and aweme_id in file_lookup:
                    candidate = file_lookup[aweme_id]
                    abs_path = downloads_path / candidate
                    if abs_path.exists():
                        video_path = candidate
                        video_status = "downloaded" if _is_probably_valid_mp4(abs_path) else "corrupt_file"

                # 方法2：通过中文关键词匹配 + 校验文件存在（兜底，加防误匹配校验）
                if not video_path:
                    clean_title = _clean_video_title(desc)
                    chinese_words = re.findall(r'[一-龥]{2,}', clean_title)
                    for word in chinese_words[:3]:
                        if word in keyword_lookup:
                            for candidate in keyword_lookup[word]:
                                abs_path = downloads_path / candidate
                                if abs_path.exists():
                                    # 防误匹配：候选文件名必须包含标题前8个汉字中的至少2个关键词
                                    candidate_stem = Path(candidate).stem.lower()
                                    title_prefix = ''.join(chinese_words)[:8]
                                    match_count = sum(1 for w in re.findall(r'[一-龥]{2,}', title_prefix) if w in candidate_stem)
                                    if match_count >= 2 or len(title_prefix) <= 4:
                                        video_path = candidate
                                        video_status = "downloaded" if _is_probably_valid_mp4(abs_path) else "corrupt_file"
                                        break
                            if video_path:
                                break

                # 统一使用 MediaAssetService 入库，与 Bilibili 保持一致
                from media_tools.assets.service import MediaAssetService
                MediaAssetService.mark_downloaded(
                    asset_id=aweme_id,
                    creator_uid=uid,
                    title=desc,
                    video_path=video_path,
                    source_platform="douyin",
                    folder_path=folder_name,
                    duration=duration,
                    video_status=video_status,
                )
    except (sqlite3.Error, OSError) as e:
        logger.error(f"同步 media_assets 失败: {e}")

async def _download_with_stats(
    url: str,
    max_counts: Optional[int] = None,
    skip_existing: bool = True,
    interval: Optional[str] = None,
    existing_source: str = "file+db",
    task_id: Optional[str] = None,
):
    """
    使用 F2 API 下载视频并保存统计数据

    Args:
        url: 用户主页 URL
        max_counts: 最大下载数量
        skip_existing: 跳过已下载视频
        interval: 时间范围，格式 "2026-01-01|2026-04-26"，F2 按此范围翻页拉取
        task_id: 关联任务 ID，用于向 cancel_registry 推送下载进度
    """
    from f2.apps.douyin.db import AsyncUserDB
    from f2.apps.douyin.handler import DouyinHandler

    # 导入进度追踪函数
    from media_tools.douyin.core.cancel_registry import (
        init_download_progress,
        update_stage,
        update_current_video,
        increment_downloaded,
        increment_skipped,
        add_download_error,
        set_total_count,
    )

    logger.info(f"开始下载: {url}")
    kwargs = _get_f2_kwargs()
    kwargs["url"] = url

    if max_counts:
        kwargs["max_counts"] = max_counts
        logger.info(f"限制下载数量: {max_counts}")

    if interval:
        kwargs["interval"] = interval
        logger.info(f"时间范围: {interval}")

    config = get_config()
    downloads_path = config.get_download_path()

    # 清理临时目录
    f2_temp_path = _prepare_f2_temp_dir(downloads_path)

    logger.info(info("[下载] 开始下载..."))
    logger.info(info(f"[路径] {downloads_path}"))
    logger.info(f"下载路径: {downloads_path}")

    # 创建元数据表
    _create_video_metadata_table()

    # 初始化进度追踪
    if task_id:
        init_download_progress(task_id, total=max_counts or 0)
        update_stage(task_id, Stage.FETCHING)

    # 初始化 Handler
    handler = DouyinHandler(kwargs)

    # 解析 sec_user_id
    from f2.apps.douyin.utils import SecUserIdFetcher

    try:
        sec_user_id = await SecUserIdFetcher.get_sec_user_id(url)
    except (RuntimeError, OSError, ValueError) as e:
        logger.error(f"解析 sec_user_id 失败: {e}")
        logger.info(error("[错误] 无法解析用户 ID"))
        if task_id:
            add_download_error(task_id, url, f"解析用户ID失败: {e}")
            update_stage(task_id, Stage.FAILED)
        return False

    if not sec_user_id:
        logger.error("无法解析用户 ID")
        logger.info(error("[错误] 无法解析用户 ID"))
        if task_id:
            add_download_error(task_id, url, "无法解析用户ID")
            update_stage(task_id, Stage.FAILED)
        return False

    logger.info(f"sec_user_id: {sec_user_id[:30]}...")
    logger.info(info(f"[信息] sec_user_id: {sec_user_id[:30]}..."))

    # 获取用户信息并保存
    async with AsyncUserDB(str(config.get_db_path())) as db:
        user_path = await handler.get_or_add_user_data(kwargs, sec_user_id, db)

    # 从数据库获取用户信息（通过 sec_user_id 精确匹配）
    db_path = config.get_db_path()
    user_info = None
    try:
        from media_tools.store.db import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT uid, nickname FROM user_info_web WHERE sec_user_id = ? LIMIT 1",
                (sec_user_id,)
            )
            user_info = cursor.fetchone()
    except (sqlite3.Error, OSError):
        pass

    # 如果没找到，使用最新记录（向后兼容）
    if not user_info:
        try:
            from media_tools.store.db import get_db_connection
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT uid, nickname FROM user_info_web ORDER BY ROWID DESC LIMIT 1"
                )
                user_info = cursor.fetchone()
        except (sqlite3.Error, OSError):
            pass

    uid = user_info[0] if user_info else ""
    nickname = user_info[1] if user_info else ""

    if nickname:
        logger.info(f"博主: {nickname} (UID: {uid})")
        logger.info(info(f"[博主] {nickname} (UID: {uid})"))

    # 统计本地已有视频（增量下载）
    existing_videos = set()
    corrupt_videos: set[str] = set()
    corrupt_files: dict[str, list[Path]] = {}
    if skip_existing:
        existing_videos, corrupt_videos, corrupt_files = _scan_local_aweme_files(user_path)
        if corrupt_videos:
            existing_videos -= corrupt_videos
        if existing_videos:
            logger.info(info(f"[本地] 已有 {len(existing_videos)} 个视频文件，将跳过已下载的"))

        # 同时从数据库获取已下载的视频 ID（防止文件被删除后重复下载）
        if existing_source != "file":
            try:
                from media_tools.store.db import get_db_connection
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT aweme_id FROM video_metadata WHERE uid = ? AND aweme_id != ''",
                        (uid,)
                    )
                    db_videos = {row[0] for row in cursor.fetchall() if row[0]}

                    if db_videos:
                        new_from_db = db_videos - existing_videos
                        if new_from_db:
                            logger.info(info(f"[数据库] 发现 {len(new_from_db)} 条历史记录（文件可能已删除）"))
                        existing_videos.update(db_videos)
            except (sqlite3.Error, OSError) as e:
                logger.warning(f"查询数据库失败: {e}")
    else:
        logger.info(info("[模式] 全量重拉：不跳过已存在视频"))

    # 收集所有视频数据
    total_downloaded = 0
    total_skipped = 0
    total_stats_saved = 0
    new_aweme_ids = []
    progress_details: list[dict] = []
    all_videos_count = 0

    logger.info(info("[下载] 正在获取视频列表..."))
    logger.info("正在获取视频列表...")

    fetch_error: Optional[str] = None
    try:
        async for aweme_data_list in handler.fetch_user_post_videos(
            sec_user_id, max_counts=max_counts or float("inf")
        ):
            video_list = aweme_data_list._to_list()
            all_videos_count += len(video_list)

            if video_list:
                # 保存统计数据
                raw_data = aweme_data_list._to_raw()
                stats_saved = _save_video_metadata_from_raw(raw_data, nickname)
                total_stats_saved += stats_saved

                # 增量/全量：过滤或全量重拉
                if skip_existing:
                    new_videos, skipped = _select_videos_to_download(
                        video_list, existing_videos, corrupt_files
                    )
                    total_skipped += skipped
                    # 更新跳过的视频进度
                    for video in video_list:
                        if video not in new_videos:
                            title = video.get('desc', '') if isinstance(video, dict) else getattr(video, 'desc', '')
                            aweme_id = video.get('aweme_id', '') if isinstance(video, dict) else getattr(video, 'aweme_id', '')
                            if task_id:
                                increment_skipped(task_id, str(title or aweme_id or "未知"))
                else:
                    new_videos = list(video_list)

                if new_videos:
                    # 更新状态为下载中
                    if task_id:
                        update_stage(task_id, Stage.DOWNLOADING)

                    # 逐个下载视频，追踪进度
                    new_videos_total = len(new_videos)
                    for video_idx, video in enumerate(new_videos, 1):
                        aweme_id = video.get('aweme_id', '') if isinstance(video, dict) else getattr(video, 'aweme_id', '')
                        title = video.get('desc', '') if isinstance(video, dict) else getattr(video, 'desc', '')
                        video_title = str(title or aweme_id or "未知")

                        # 更新当前下载的视频
                        if task_id:
                            update_current_video(task_id, video_title)

                        logger.info(info(f"[下载] ({video_idx}/{new_videos_total}) {video_title[:50]}..."))

                        try:
                            # 单视频下载
                            await handler.downloader.create_download_tasks(
                                kwargs, [video], user_path
                            )

                            if aweme_id:
                                new_aweme_ids.append(aweme_id)
                            total_downloaded += 1
                            progress_details.append({"title": video_title, "status": "downloaded"})

                            # 更新进度
                            if task_id:
                                increment_downloaded(task_id, video_title)

                            logger.info(info(f"[成功] {video_title[:50]}..."))
                        except (RuntimeError, OSError, ValueError) as e:
                            logger.error(f"下载视频失败 {video_title}: {e}")
                            logger.info(error(f"[失败] {video_title[:50]}..."))
                            if task_id:
                                add_download_error(task_id, video_title, str(e))

                    page_skipped = len(video_list) - len(new_videos) if skip_existing else 0
                    if skip_existing:
                        logger.info(info(f"[下载] 本页 {len(new_videos)} 个新视频（跳过 {page_skipped} 个已有）"))
                    else:
                        logger.info(info(f"[下载] 本页 {len(new_videos)} 个视频（全量重拉）"))
                else:
                    logger.info(info(f"[跳过] 本页 {len(video_list)} 个视频均为本地已有"))

                # 如果指定了 max_counts，检查是否已达到上限
                if max_counts and total_downloaded >= max_counts:
                    logger.info(info(f"[限制] 已达到下载上限 ({max_counts} 个)"))
                    break

                logger.info(info(f"[下载] 累计新增 {total_downloaded} 个，跳过 {total_skipped} 个已有"))
    except (RuntimeError, OSError, ValueError) as e:
        fetch_error = str(e)
        logger.error(f"下载过程中出错: {e}")
        logger.info(error(f"下载过程中出错: {e}"))
        if task_id:
            add_download_error(task_id, url, str(e))
        # 继续处理已下载的视频，但末尾返回 success=False

    # 更新总数量
    if task_id:
        set_total_count(task_id, all_videos_count)

    logger.info(f"保存了 {total_stats_saved} 条视频元数据")
    logger.info(success(f"[统计] 新增 {total_downloaded} 个，跳过 {total_skipped} 个已有"))

    # 更新状态为整理中
    if task_id:
        update_stage(task_id, Stage.AUDITING)

    # 整理文件
    logger.info(info("[整理] 重新组织文件..."))
    post_path = downloads_path / "douyin" / "post"
    folder_name = None
    
    # 处理 douyin/post 下的文件
    if post_path.exists():
        for folder in post_path.iterdir():
            if folder.is_dir():
                folder_name = _reorganize_files(folder.name, uid)
    
    # 处理直接在下载目录或子目录下的文件（兼容不同 F2 版本的下载路径）
    folder_name = _rename_videos_in_downloads(nickname, uid, downloads_path) or folder_name

    # 更新 last_fetch_time
    if folder_name:
        _update_last_fetch_time(uid, nickname or folder_name)

    # 更新状态为同步资产库
    if task_id:
        update_stage(task_id, Stage.TRANSCRIBING)

    # 同步 V2 资产库
    if folder_name:
        logger.info(info("[资产] 同步至媒体资产库..."))
        _sync_media_assets(uid, nickname, folder_name)

    new_files = []
    if new_aweme_ids and folder_name:
        try:
            from media_tools.store.db import get_db_connection
            with get_db_connection() as conn:
                cursor = conn.cursor()
                placeholders = ','.join(['?'] * len(new_aweme_ids))
                cursor.execute(f"SELECT video_path FROM media_assets WHERE asset_id IN ({placeholders})", new_aweme_ids)
                for row in cursor.fetchall():
                    if row[0]:
                        full_path = downloads_path / row[0]
                        if full_path.exists():
                            new_files.append(str(full_path))
        except (sqlite3.Error, OSError) as e:
            logger.error(f"查询新文件路径失败: {e}")
    # 去重：同一个物理文件不应被转写多次
    new_files = list(dict.fromkeys(new_files))

    # 静默失败检测：F2 可能在 create_download_tasks 阶段静默失败
    # （cookie 过期、风控、网络等），声明下载了 N 个但实际 0 个落盘
    silent_fail_error = ""
    if new_aweme_ids and not new_files:
        silent_fail_error = (
            f"声明下载 {len(new_aweme_ids)} 个但实际 0 个落盘（cookie 可能过期或被风控）"
        )
        logger.error(silent_fail_error)
        logger.info(error(f"[失败] {silent_fail_error}"))
        if task_id:
            add_download_error(task_id, url, silent_fail_error)

    # 更新状态为完成
    if task_id:
        update_stage(task_id, Stage.COMPLETED)

    logger.info(f"下载完成: 共 {total_downloaded} 个视频")
    logger.info(success(f"\n[完成] 共下载 {total_downloaded} 个视频"))
    if folder_name:
        logger.info(info(f"[位置] {downloads_path / folder_name}"))

    final_error = fetch_error or silent_fail_error
    return {
        'success': not final_error,
        'error': final_error,
        'uid': uid,
        'nickname': nickname,
        'new_files': new_files,
    }


def download_by_url_sync(url, max_counts=None, skip_existing: bool = True, interval: Optional[str] = None, existing_source: str = "file+db", task_id: Optional[str] = None):
    """同步包装器：通过 URL 下载单个博主的视频"""
    try:
        # 检查是否已有运行中的事件循环
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # 如果已有事件循环，创建任务并等待
            import warnings
            warnings.warn(
                "download_by_url_sync called from running event loop. "
                "Consider using the async version directly.",
                RuntimeWarning,
                stacklevel=2
            )
            # 在已有循环中，我们需要用 run_until_complete 的替代方案
            # 但由于无法在同步函数中等待异步，只能抛出异常
            raise RuntimeError(
                "Cannot call sync wrapper from async context. "
                "Use _download_with_stats directly."
            )
        else:
            # 没有运行中的循环，可以安全使用 asyncio.run()
            return asyncio.run(_download_with_stats(url, max_counts, skip_existing=skip_existing, interval=interval, existing_source=existing_source, task_id=task_id))
    except (RuntimeError, OSError, ValueError) as e:
        logger.info(error(f"下载出错: {e}"))
        return False


def download_by_url(
    url,
    max_counts: Optional[int] = None,
    disable_auto_transcribe=False,
    skip_existing: bool = True,
    task_id: Optional[str] = None,
    interval: Optional[str] = None,
    existing_source: str = "file+db",
):
    """
    通过 URL 下载单个博主的视频

    Args:
        url: 博主主页 URL
        max_counts: 最大下载数量
        disable_auto_transcribe: 是否禁用自动转写
        task_id: 关联的任务 ID（用于取消检测与进度推送）
        interval: 时间范围，格式 "2026-01-01|2026-04-26"

    Returns:
        dict: 包含 success, uid, nickname, new_files 的字典，或 False
    """
    print_header("下载博主视频")
    logger.info(info(f"博主 URL: {url}"))
    if max_counts:
        logger.info(info(f"最大下载数量: {max_counts}"))
    if interval:
        logger.info(info(f"时间范围: {interval}"))
    logger.info("")

    logger.info(info("开始下载..."))
    logger.info("")

    result = download_by_url_sync(url, max_counts, skip_existing=skip_existing, interval=interval, existing_source=existing_source, task_id=task_id)

    if result:
        logger.info(success("下载完成！"))
        return result
    else:
        logger.info(error("下载失败，请检查日志"))
        return False


async def download_aweme_by_url(url: str):
    """按单个视频 URL 精确下载一个视频"""
    from f2.apps.douyin.db import AsyncUserDB
    from f2.apps.douyin.handler import DouyinHandler
    from f2.apps.douyin.utils import AwemeIdFetcher

    print_header("下载单个视频")
    logger.info(info(f"视频 URL: {url}"))
    logger.info("")

    config = get_config()
    downloads_path = config.get_download_path()
    kwargs = _get_f2_kwargs()
    kwargs["url"] = url

    _prepare_f2_temp_dir(downloads_path)

    _create_video_metadata_table()

    try:
        aweme_id = await AwemeIdFetcher.get_aweme_id(url)
    except (RuntimeError, OSError, ValueError) as e:
        logger.info(error(f"解析视频 ID 失败: {e}"))
        return False

    if not aweme_id:
        logger.info(error("无法解析视频 ID"))
        return False

    handler = DouyinHandler(kwargs)

    try:
        aweme_data = await handler.fetch_one_video(aweme_id)
    except (RuntimeError, OSError, ValueError) as e:
        logger.info(error(f"获取视频详情失败: {e}"))
        return False

    aweme_dict = aweme_data._to_dict()
    uid = str(aweme_dict.get("uid") or aweme_dict.get("author", {}).get("uid") or "")
    nickname = str(aweme_dict.get("nickname") or aweme_dict.get("author", {}).get("nickname") or "")

    async with AsyncUserDB(str(config.get_db_path())) as db:
        user_path = await handler.get_or_add_user_data(kwargs, aweme_data.sec_user_id, db)

    before_files = {p.resolve() for p in user_path.glob("*.mp4")} if user_path.exists() else set()

    _save_single_video_metadata(aweme_dict, nickname=nickname)

    await handler.downloader.create_download_tasks(kwargs, aweme_dict, user_path)

    folder_name = None

    post_path = downloads_path / "douyin" / "post"
    if post_path.exists():
        for folder in post_path.iterdir():
            if folder.is_dir():
                folder_name = _reorganize_files(folder.name, uid) or folder_name

    folder_name = _rename_videos_in_downloads(nickname, uid, downloads_path) or folder_name or user_path.name

    if uid:
        _sync_media_assets(uid, nickname, folder_name)
        _update_last_fetch_time(uid, nickname or folder_name)

    new_files: list[str] = []
    target_dir = downloads_path / folder_name if folder_name else user_path
    if target_dir.exists():
        for file_path in target_dir.glob("*.mp4"):
            if file_path.resolve() not in before_files:
                new_files.append(str(file_path))

    try:
        from media_tools.store.db import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT video_path FROM media_assets WHERE asset_id = ?",
                (aweme_id,),
            )
            row = cursor.fetchone()
            if row and row[0]:
                full_path = downloads_path / row[0]
                if full_path.exists():
                    if str(full_path) not in new_files:
                        new_files.append(str(full_path))
    except (sqlite3.Error, OSError, RuntimeError) as e:
        logger.warning(f"查询单视频文件路径失败: {e}")

    logger.info(success(f"[完成] 单个视频下载成功: {aweme_id}"))
    return {
        "success": True,
        "uid": uid,
        "nickname": nickname,
        "aweme_id": aweme_id,
        "new_files": new_files,
    }


def download_by_uid(uid, max_counts=None, skip_existing: bool = True, task_id: Optional[str] = None, interval: Optional[str] = None, existing_source: str = "file+db"):
    """
    通过 UID 下载博主视频

    Args:
        uid: 用户 UID
        max_counts: 最大下载数量
        task_id: 关联的任务 ID（用于取消检测）
        interval: 时间范围，格式 "2026-01-01|2026-04-26"

    Returns:
        是否成功
    """
    from media_tools.douyin.core.following_mgr import get_user

    user = get_user(uid)
    if not user:
        logger.info(error(f"用户 {uid} 不在关注列表中"))
        return False

    # 构建 URL
    sec_user_id = user.get("sec_user_id", "")
    if sec_user_id and sec_user_id.startswith("MS4w"):
        url = f"https://www.douyin.com/user/{sec_user_id}"
    else:
        url = f"https://www.douyin.com/user/{uid}"

    name = user.get("nickname", user.get("name", "未知"))
    logger.info(info(f"博主: {name} (UID: {uid})"))

    result = download_by_url(url, max_counts, skip_existing=skip_existing, task_id=task_id, interval=interval, existing_source=existing_source)

    return result


def download_all(auto_confirm=False):
    """
    下载所有关注的博主

    Args:
        auto_confirm: 是否跳过确认

    Returns:
        (success_count, failed_count) 元组
    """
    print_header("全量下载")

    users = list_users()
    if not users:
        logger.info(info("关注列表为空"))
        logger.info(info("请先使用 '添加博主' 功能添加关注"))
        return 0, 0

    logger.info(info(f"共 {len(users)} 位博主"))
    logger.info("")

    if not auto_confirm:
        confirm = input("确认开始下载？(y/N): ").strip().lower()
        if confirm != "y":
            logger.info(info("已取消"))
            return 0, 0

    success_count = 0
    failed_count = 0

    for i, user in enumerate(users, 1):
        uid = user.get("uid")
        name = user.get("nickname", user.get("name", "未知"))

        logger.info("")
        logger.info(info(f"[{i}/{len(users)}] 下载: {name}"))

        ok = download_by_uid(uid, existing_source="file")
        if ok:
            success_count += 1
        else:
            failed_count += 1

    logger.info("")
    print_header("下载完成")
    logger.info(success(f"成功: {success_count}"))
    logger.info(error(f"失败: {failed_count}"))

    return success_count, failed_count


def interactive_select():
    """
    交互式选择博主下载

    Returns:
        (success_count, failed_count) 元组
    """
    print_header("选择下载")

    users = list_users()
    if not users:
        logger.info(info("关注列表为空"))
        logger.info(info("请先使用 '添加博主' 功能添加关注"))
        return 0, 0

    config = get_config()
    downloads_path = config.get_download_path()

    # 显示用户列表
    logger.info(info("选择要下载的博主（输入序号，逗号分隔，all=全部，q=返回）"))
    logger.info("")

    for i, user in enumerate(users, 1):
        uid = user.get("uid", "未知")
        name = user.get("nickname", user.get("name", "未知"))
        folder = user.get("folder", name or uid)
        user_dir = downloads_path / folder
        local_count = len(list(user_dir.glob("*.mp4"))) if user_dir.exists() else 0

        status = f"已下载 {local_count} 个" if local_count > 0 else "未下载"
        logger.info(f"  {i:2}. {name} ({status})")

    logger.info("")
    choice = input("请选择: ").strip().lower()

    if choice == "q" or not choice:
        logger.info(info("已取消"))
        return 0, 0

    if choice == "all":
        return download_all(auto_confirm=True)

    # 解析选择
    try:
        indices = [int(x.strip()) for x in choice.split(",") if x.strip()]
        selected = []
        for idx in indices:
            if 1 <= idx <= len(users):
                selected.append(users[idx - 1])
            else:
                logger.info(warning(f"无效的序号: {idx}"))

        if not selected:
            logger.info(error("没有有效的选择"))
            return 0, 0

        logger.info("")
        logger.info(info(f"已选择 {len(selected)} 个博主"))

        success_count = 0
        failed_count = 0

        for i, user in enumerate(selected, 1):
            uid = user.get("uid")
            name = user.get("nickname", user.get("name", "未知"))

            logger.info("")
            logger.info(info(f"[{i}/{len(selected)}] 下载: {name}"))

            ok = download_by_uid(uid)
            if ok:
                success_count += 1
            else:
                failed_count += 1

        logger.info("")
        logger.info(success(f"下载完成: 成功 {success_count}，失败 {failed_count}"))
        return success_count, failed_count

    except ValueError:
        logger.info(error("无效的输入，请输入数字"))
        return 0, 0


def download_sample(auto_confirm=False):
    """
    采样下载：每个博主只下载1个视频，用于快速更新统计数据

    Args:
        auto_confirm: 是否跳过确认

    Returns:
        (success_count, failed_count) 元组
    """
    print_header("采样下载")

    users = list_users()
    if not users:
        logger.info(info("关注列表为空"))
        return 0, 0

    logger.info(info("每个博主只下载 1 个视频"))
    logger.info(info(f"共 {len(users)} 位博主"))
    logger.info("")

    if not auto_confirm:
        confirm = input("确认开始？(y/N): ").strip().lower()
        if confirm != "y":
            logger.info(info("已取消"))
            return 0, 0

    success_count = 0
    failed_count = 0

    for i, user in enumerate(users, 1):
        uid = user.get("uid")
        name = user.get("nickname", user.get("name", "未知"))

        logger.info(info(f"[{i}/{len(users)}] 采样: {name}"))

        ok = download_by_uid(uid, max_counts=1)
        if ok:
            success_count += 1
        else:
            failed_count += 1

    logger.info("")
    logger.info(success(f"采样完成: 成功 {success_count}，失败 {failed_count}"))
    return success_count, failed_count

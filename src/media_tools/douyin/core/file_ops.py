from __future__ import annotations

"""抖音下载器文件操作工具"""
import contextlib
import logging
import shutil
import sqlite3

from media_tools.douyin.core.config_mgr import get_config
from media_tools.store.db import resolve_safe_path

logger = logging.getLogger(__name__)


def info(msg: str) -> str:
    """格式化信息日志"""
    return msg


def _clean_video_title(raw_title: str) -> str:
    """清洗视频标题：去掉换行符和 #话题标签，并智能截断长标题"""
    main_part = raw_title.replace("<br>", "\n").split("\n")[0]
    clean = main_part[: main_part.index("#")].strip() if "#" in main_part else main_part.strip()
    if len(clean) > 40:
        for p in ["？", "！", "。"]:
            idx = clean.find(p)
            if 10 < idx < 50:
                return clean[: idx + 1].strip()
        space_idx = clean.find(" ")
        if space_idx > 15:
            return clean[:space_idx].strip()
        comma_idx = clean.find("，")
        if comma_idx > 10:
            return clean[: comma_idx + 1].strip()
        return clean[:35] + "..."
    return clean


def _reorganize_files(nickname: str, uid: str) -> str | None:
    """整理文件到下载目录/{博主昵称}/"""
    config = get_config()
    downloads_path = config.get_download_path()
    old_path = resolve_safe_path(downloads_path, f"douyin/post/{nickname}")
    if not old_path or not old_path.exists():
        return None
    folder_name = nickname or uid
    new_path = resolve_safe_path(downloads_path, folder_name)
    if not new_path:
        logger.warning(f"Path traversal blocked for folder: {folder_name}")
        new_path = resolve_safe_path(downloads_path, uid) or downloads_path
    new_path.mkdir(parents=True, exist_ok=True)
    moved_count = 0
    for pattern in ["*.mp4", "*.jpg", "*.webp"]:
        for f in old_path.glob(pattern):
            dest = new_path / f.name
            if not dest.exists():
                shutil.move(str(f), str(dest))
                moved_count += 1
    if old_path.exists():
        with contextlib.suppress(OSError):
            shutil.rmtree(old_path)
    if moved_count > 0:
        logger.info(info(f"  [移动] {nickname} -> {folder_name} ({moved_count} 文件)"))
    return folder_name


def _update_last_fetch_time(uid: str, nickname: str = ""):
    """更新 SQLite 中的 last_fetch_time — 使用 UTC CURRENT_TIMESTAMP 保持一致性"""
    try:
        from media_tools.store.db import get_db_connection

        with get_db_connection() as conn:
            cursor = conn.cursor()
            # 使用 CURRENT_TIMESTAMP（UTC），与 creator_sync.py 保持一致
            # 不再用 datetime.now().isoformat()（本地时间，会导致时区不一致）
            cursor.execute("UPDATE creators SET last_fetch_time = CURRENT_TIMESTAMP WHERE uid = ?", (uid,))
            # 兼容旧表（仅在表存在时更新）
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='douyin_users'")
            if cursor.fetchone():
                cursor.execute("UPDATE douyin_users SET last_fetch_time = CURRENT_TIMESTAMP WHERE sec_uid = ?", (uid,))
            conn.commit()
    except (sqlite3.Error, OSError) as e:
        logger.error(f"更新 last_fetch_time 失败: {e}")

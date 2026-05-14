from __future__ import annotations
"""本地视频扫描和数据库记录查询"""

import sqlite3
from pathlib import Path

from media_tools.logger import get_logger
from .config_mgr import get_config
from .following_mgr import list_users

logger = get_logger(__name__)


def scan_local_videos():
    """
    扫描本地所有视频文件

    Returns:
        dict: {uid: {video_files: set, folder: str}}
    """
    config = get_config()
    downloads_path = config.get_download_path()

    users = list_users()
    local_data = {}
    uid_to_user = {user.get("uid"): user for user in users}

    if not downloads_path.exists():
        return local_data

    try:
        for folder in downloads_path.iterdir():
            if not folder.is_dir():
                continue
            if folder.name in ["douyin", ".git", "__pycache__"]:
                continue

            folder_name = folder.name
            matched_uid = None

            for user in users:
                user_folder = user.get("folder")
                if user_folder and user_folder == folder_name:
                    matched_uid = user.get("uid")
                    break

            if not matched_uid and folder_name.isdigit():
                if folder_name in uid_to_user:
                    matched_uid = folder_name

            if not matched_uid:
                for uid, user in uid_to_user.items():
                    name = user.get("nickname", user.get("name", ""))
                    if name == folder_name or str(uid) == folder_name:
                        matched_uid = uid
                        break

            if matched_uid:
                try:
                    video_files = set(f.name for f in folder.glob("*.mp4"))
                    local_data[matched_uid] = {
                        "folder": folder_name,
                        "video_files": video_files,
                        "count": len(video_files),
                    }
                except (PermissionError, OSError):
                    local_data[matched_uid] = {
                        "folder": folder_name,
                        "video_files": set(),
                        "count": 0,
                    }
    except (PermissionError, OSError) as e:
        logger.info(f"扫描目录失败: {e}")
        return local_data

    return local_data


def get_db_video_records():
    """
    获取数据库中所有视频记录

    Returns:
        dict: {uid: {aweme_ids: set, records: list}}
    """
    config = get_config()
    db_path = config.get_db_path()

    if not db_path.exists():
        return {}

    try:
        from media_tools.store.db import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT aweme_id, uid, desc, local_filename FROM video_metadata")
            rows = cursor.fetchall()

            db_data = {}
            for aweme_id, uid, desc, local_filename in rows:
                if uid not in db_data:
                    db_data[uid] = {
                        "aweme_ids": set(),
                        "records": [],
                    }
                db_data[uid]["aweme_ids"].add(aweme_id)
                db_data[uid]["records"].append({
                    "aweme_id": aweme_id,
                    "desc": desc,
                    "local_filename": local_filename,
                })

            return db_data
    except (sqlite3.Error, OSError) as e:
        logger.info(f"数据库读取失败: {e}")
        return {}

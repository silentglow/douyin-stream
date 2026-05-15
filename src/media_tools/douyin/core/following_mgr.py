#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关注列表管理模块 - 增删查取关清理
"""

import sqlite3
from datetime import datetime

from media_tools.store.db import get_db_connection
from media_tools.logger import get_logger

from .config_mgr import get_config
from .ui import (
    info,
    print_header,
    success,
)
from .utils import _run_async_coro, _resolve_sec_user_id, _clean_nickname

logger = get_logger(__name__)


def list_users():
    """
    列出所有关注的博主 (从 SQLite V2 架构读取)

    Returns:
        用户列表 (List of dicts)
    """
    config = get_config()
    db_path = config.get_db_path()
    
    users = []
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT uid, sec_user_id, nickname, platform, sync_status, last_fetch_time FROM creators ORDER BY last_fetch_time DESC")

            for row in cursor.fetchall():
                users.append({
                    "uid": row["uid"],
                    "sec_user_id": row["sec_user_id"],
                    "nickname": row["nickname"] or row["uid"],
                    "name": row["nickname"] or row["uid"],
                    "platform": row["platform"],
                    "sync_status": row["sync_status"],
                    "last_fetch_time": row["last_fetch_time"]
                })
    except (sqlite3.Error, OSError) as e:
        logger.error(f"读取关注列表失败: {e}")

    return users


def get_user(uid: str):
    config = get_config()
    db_path = config.get_db_path()
    try:
        from media_tools.store.db import get_db_connection
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT uid, sec_user_id, nickname, platform, sync_status, last_fetch_time FROM creators WHERE uid = ?",
                (uid,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "uid": row["uid"],
                "sec_user_id": row["sec_user_id"],
                "nickname": row["nickname"] or row["uid"],
                "name": row["nickname"] or row["uid"],
                "platform": row["platform"],
                "sync_status": row["sync_status"],
                "last_fetch_time": row["last_fetch_time"],
            }
    except (sqlite3.Error, OSError) as e:
        logger.error(f"读取用户失败: {e}")
        return None


def add_user(url):
    """
    通过主页链接添加用户 (写入 SQLite V2 架构)

    Args:
        url: 抖音主页链接

    Returns:
        (success, user_info) 元组
    """
    print_header("添加关注博主")

    sec_user_id = _resolve_sec_user_id(url)
    if not sec_user_id:
        logger.error("无法从链接解析有效的 sec_user_id")
        logger.info(info("请使用可访问的抖音主页链接，格式如:"))
        logger.info(info("https://www.douyin.com/user/MS4wLjABAAAA..."))
        return False, None

    # 检查是否已存在
    config = get_config()
    db_path = config.get_db_path()
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT uid, nickname FROM creators WHERE sec_user_id = ?", (sec_user_id,))
            row = cursor.fetchone()
            if row:
                name = row[1] or "未知"
                logger.warning(f"用户已在关注列表: {name} (UID: {row[0]})")
                return False, {"uid": row[0], "sec_user_id": sec_user_id, "nickname": name}
    except (sqlite3.Error, OSError) as e:
        logger.error(f"查询数据库失败: {e}")

    # 通过 F2 获取用户信息
    logger.info(info("正在通过 F2 获取用户信息..."))
    user_info = _fetch_user_info_via_f2(url, sec_user_id)

    if not user_info:
        logger.error("获取用户信息失败")
        return False, None

    uid = user_info.get("uid")
    nickname = user_info.get("nickname", "")
    
    # 写入数据库 (代替旧版的 following.json)
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            avatar = user_info.get("avatar_url", "")
            bio = user_info.get("signature", "")
            
            homepage_url = f"https://www.douyin.com/user/{sec_user_id}"
            cursor.execute("""
                INSERT OR REPLACE INTO creators 
                (uid, sec_user_id, nickname, avatar, bio, homepage_url, platform, sync_status, last_fetch_time)
                VALUES (?, ?, ?, ?, ?, ?, 'douyin', 'active', ?)
            """, (uid, sec_user_id, nickname, avatar, bio, homepage_url, now))
            conn.commit()
    except (sqlite3.Error, OSError) as e:
        logger.error(f"保存用户到数据库失败: {e}")
        return False, None

    logger.info(success(f"已添加用户: {nickname} (UID: {uid})"))
    logger.info(info("提示: 运行下载功能可获取完整用户信息和视频"))

    return True, user_info


def _fetch_user_info_via_f2(url, sec_user_id):
    """
    通过 F2 的实时 profile 接口获取用户信息。

    这里不再依赖 user_info_web 的“最新一条记录”回填，避免串到错误博主。
    """

    async def _fetch_profile():
        from .downloader import _get_f2_kwargs
        from f2.apps.douyin.handler import DouyinHandler

        kwargs = _get_f2_kwargs()
        handler = DouyinHandler(kwargs)
        profile = await handler.fetch_user_profile(sec_user_id)
        return profile._to_dict()

    try:
        profile_data = _run_async_coro(_fetch_profile())
    except (RuntimeError, OSError, ValueError) as exc:
        logger.error(f"获取用户 profile 失败: {exc}")
        return None

    uid = str(profile_data.get("uid", "")).strip()
    nickname = _clean_nickname(str(profile_data.get("nickname", "")).strip())
    if not uid:
        logger.error("实时 profile 返回的 uid 为空")
        return None

    return {
        "uid": uid,
        "sec_user_id": str(profile_data.get("sec_user_id", sec_user_id) or sec_user_id),
        "name": nickname or uid,
        "nickname": nickname or uid,
        "homepage_url": f"https://www.douyin.com/user/{sec_user_id}",
        "avatar_url": profile_data.get("avatar_url", "") or "",
        "signature": profile_data.get("signature", "") or "",
        "follower_count": profile_data.get("follower_count", 0) or 0,
        "following_count": profile_data.get("following_count", 0) or 0,
        "video_count": profile_data.get("aweme_count", 0) or 0,
        "last_updated": datetime.now().isoformat(),
        "last_fetch_time": None,
    }

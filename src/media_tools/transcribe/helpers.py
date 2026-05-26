from __future__ import annotations
"""Pipeline 工具函数"""
from typing import Optional

import logging
import re
import sqlite3
from pathlib import Path

from media_tools.store.db import get_db_connection

logger = logging.getLogger(__name__)


def _clean_title_for_export(raw_title: str) -> Optional[str]:
    """清洗标题用于导出文件名：去掉换行和 #话题标签"""
    main_part = raw_title.replace('<br>', '\n').split('\n')[0]
    if '#' in main_part:
        clean = main_part[:main_part.index('#')].strip()
    else:
        clean = main_part.strip()
    clean = re.sub(r'[<>:""/\\|?*]', '', clean).strip()
    if len(clean) > 50:
        clean = clean[:50]
    return clean if len(clean) > 2 else None


def _lookup_video_title(video_path: Path) -> Optional[str]:
    """从数据库查询视频标题（通过文件名中的 aweme_id）"""
    aweme_matches = re.findall(r'\d{15,}', video_path.name)
    if not aweme_matches:
        return None

    aweme_id = aweme_matches[0]
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT desc FROM video_metadata WHERE aweme_id = ?", (aweme_id,))
            row = cursor.fetchone()
            if not row or not row[0]:
                cursor.execute("SELECT title FROM media_assets WHERE asset_id = ?", (aweme_id,))
                row = cursor.fetchone()
            if row and row[0]:
                return _clean_title_for_export(row[0])
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"查询视频标题失败: {e}")

    return None


def _lookup_creator_folder(video_path: Path) -> Optional[str]:
    """从视频所在目录或数据库查询视频所属创作者昵称（用作转写子目录名）"""

    # 方法1：从视频所在目录获取（视频在 downloads/创作者名/ 下）
    parent_name = video_path.parent.name
    if parent_name and parent_name not in ["downloads", "douyin", "bilibili", ""]:
        # 清理目录名
        name = re.sub(r'[<>"/\\|?*]', '', parent_name).strip()
        name = re.sub(r'\.+', '_', name).strip()
        if name and name != "downloads":
            return name

    # 方法2：从文件名中的 aweme_id 查询
    aweme_matches = re.findall(r'\d{15,}', video_path.name)
    if not aweme_matches:
        return None

    aweme_id = aweme_matches[0]
    try:
        from media_tools.common.paths import get_db_path as _get_db_path
        db_path = _get_db_path()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # media_assets.creator_uid -> creators.nickname
            cursor.execute("""
                SELECT c.nickname
                FROM creators c
                JOIN media_assets m ON c.uid = m.creator_uid
                WHERE m.asset_id = ?
            """, (aweme_id,))
            row = cursor.fetchone()
            if row and row[0]:
                return _clean_title_for_export(row[0])

            # 方法3：从 video_metadata 表的 nickname 字段（之前错误地查了 creator_name）
            cursor.execute("SELECT nickname FROM video_metadata WHERE aweme_id = ?", (aweme_id,))
            row = cursor.fetchone()
            if row and row[0]:
                return _clean_title_for_export(row[0])
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"查询创作者信息失败: {e}")

    return None

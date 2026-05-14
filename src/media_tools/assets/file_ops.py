from __future__ import annotations
"""素材文件操作服务"""
from typing import Optional, Union

import logging
import os
import sys
from pathlib import Path

from media_tools.common.paths import get_download_path, get_project_root
from media_tools.store.db import resolve_safe_path
from media_tools.assets.local import LOCAL_CREATOR_UID

logger = logging.getLogger(__name__)


def _resolve_asset_video_file(
    *,
    creator_uid: Optional[str],
    source_url: Optional[str],
    video_path: Optional[str],
    download_dir: Path,
) -> Optional[Path]:
    """解析素材视频文件的实际路径（含安全检查）"""
    if creator_uid == LOCAL_CREATOR_UID and source_url:
        try:
            target = Path(source_url).resolve()
            home = Path.home().resolve()
            allowed_roots = [home, Path("/tmp").resolve()]
            if sys.platform == "darwin":
                allowed_roots.append(Path("/Volumes").resolve())
            dir_str = str(target)
            for root in allowed_roots:
                root_str = str(root)
                if dir_str.startswith(root_str + os.sep) or dir_str == root_str:
                    return target
            logger.warning(f"Local asset path traversal blocked: {source_url}")
            return None
        except (OSError, ValueError):
            return None
    return resolve_safe_path(download_dir, video_path)


def get_source_url_column(conn) -> str:
    """返回 source_url 列的 SELECT 片段（兼容旧表结构）"""
    from media_tools.store.db import get_table_columns
    return "source_url," if "source_url" in get_table_columns(conn, "media_assets") else "'' AS source_url,"


def delete_asset_files(
    creator_uid: str,
    source_url: Optional[str],
    video_path: Optional[str],
    transcript_name: Optional[str],
    *,
    download_dir: Optional[Path] = None,
    transcripts_dir: Optional[Path] = None,
) -> list[str]:
    """删除素材关联的文件，返回失败的列表"""
    failed: list[str] = []
    if download_dir is None:
        download_dir = get_download_path()
    if transcripts_dir is None:
        transcripts_dir = get_project_root() / "transcripts"

    # Delete video file
    # 注：本地素材的 video 是用户主目录中的原始文件（不在 downloads 内），
    # 单独删除素材记录时不应连带删除用户文件——只删 DB 行。
    if creator_uid != LOCAL_CREATOR_UID and (source_url or video_path):
        full_video_path = _resolve_asset_video_file(
            creator_uid=creator_uid,
            source_url=source_url,
            video_path=video_path,
            download_dir=download_dir,
        )
        if full_video_path and full_video_path.exists():
            try:
                full_video_path.unlink()
            except OSError:
                failed.append(f"video:{full_video_path}")

    # Delete transcript file
    if transcript_name:
        full_transcript_path = resolve_safe_path(transcripts_dir, transcript_name)
        if full_transcript_path and full_transcript_path.exists():
            try:
                full_transcript_path.unlink()
            except OSError:
                failed.append(f"transcript:{full_transcript_path}")

    return failed

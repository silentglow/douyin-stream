from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, field_validator
from media_tools.common.paths import get_download_path, get_transcripts_path
from media_tools.store.db import get_db_connection, resolve_safe_path, resolve_query_value
from media_tools.assets.file_ops import (
    delete_asset_files,
    _resolve_asset_video_file,
)
from media_tools.assets.gc import cleanup_stale_assets
from media_tools.assets.local import LOCAL_CREATOR_UID
from media_tools.assets.repository import AssetRepository
from typing import Optional
import sqlite3
import logging
import io
import zipfile
import mimetypes
import os
from pathlib import Path

router = APIRouter(prefix="/api/v1/assets", tags=["assets"], redirect_slashes=False)
logger = logging.getLogger(__name__)


@router.get("")
def list_assets(
    creator_uid: Optional[str] = Query(None),
    transcript_status: Optional[str] = Query(
        default=None,
        description="按转写状态过滤：completed / pending / none / failed；支持逗号分隔多个",
        max_length=200,
    ),
    limit: Optional[int] = Query(default=None, ge=1, le=500),
    offset: Optional[int] = Query(default=None, ge=0),
    silent: bool = Query(default=False, description="返回空列表而非抛错（兼容旧版）"),
):
    """
    获取素材列表

    - silent=false（默认）：数据库错误抛 500
    - silent=true：数据库错误返回空列表（兼容旧版）
    """
    limit = resolve_query_value(limit, 100)
    offset = resolve_query_value(offset, 0)
    transcript_status = resolve_query_value(transcript_status, None)

    # 解析 transcript_status 过滤：白名单校验，拒绝 SQL 注入
    allowed_statuses = {"completed", "pending", "none", "failed"}
    status_filter: list[str] = []
    if transcript_status:
        for token in transcript_status.split(","):
            t = token.strip().lower()
            if t and t in allowed_statuses:
                status_filter.append(t)
        status_filter = list(dict.fromkeys(status_filter))

    try:
        return AssetRepository.list_with_filters(
            creator_uid=creator_uid,
            status_filter=status_filter or None,
            limit=limit,
            offset=offset,
        )
    except (sqlite3.Error, OSError, RuntimeError) as e:
        logger.exception(f"list_assets 错误: creator_uid={creator_uid}, limit={limit}, offset={offset}")
        if silent:
            return []
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
def search_assets(q: str = Query(..., min_length=1, max_length=200)):
    """搜索素材标题和转写文稿内容（FTS5全文索引）"""
    try:
        # 1) 移除控制字符（防 tokenizer 异常）
        cleaned = "".join(c for c in q if c.isprintable() or c.isspace()).strip()
        if not cleaned:
            return []
        return AssetRepository.search_fts(cleaned)
    except (sqlite3.Error, OSError, RuntimeError) as e:
        logger.exception("search_assets failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export")
def export_transcripts(asset_ids: list[str]):
    """批量导出转写文稿为 zip"""
    if not asset_ids:
        raise HTTPException(status_code=400, detail="No asset IDs provided")

    transcripts_dir = get_transcripts_path()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        used_filenames: set[str] = set()
        rows = AssetRepository.find_by_ids_for_export(asset_ids)
        for row in rows:
            transcript_file = resolve_safe_path(transcripts_dir, row['transcript_path'])
            if transcript_file and transcript_file.exists():
                suffix = transcript_file.suffix or ".md"
                stem = f"{row['title'] or row['asset_id']}"
                # 清理文件名
                stem = ''.join(c for c in stem if c not in '<>:"/\\|?*').strip() or str(row['asset_id'])
                filename = f"{stem}{suffix}"
                if filename in used_filenames:
                    filename = f"{stem}-{row['asset_id']}{suffix}"
                used_filenames.add(filename)
                zf.writestr(filename, transcript_file.read_bytes())

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=transcripts.zip"}
    )


@router.get("/{asset_id}/transcript")
def get_transcript(asset_id: str):
    try:
        transcript_path = AssetRepository.get_transcript_path(asset_id)

        if not transcript_path:
            raise HTTPException(status_code=404, detail="Transcript not found in database")

        transcripts_dir = get_transcripts_path()
        transcript_file = resolve_safe_path(transcripts_dir, transcript_path)

        if not transcript_file or not transcript_file.exists():
            raise HTTPException(status_code=404, detail="Transcript file not found on disk")

        if transcript_file.suffix.lower() == ".docx":
            from media_tools.transcribe.preview import extract_transcript_text

            content = extract_transcript_text(transcript_file)
        else:
            content = transcript_file.read_text(encoding="utf-8", errors="replace")
        return {"content": content}

    except HTTPException:
        raise
    except (OSError, ValueError, RuntimeError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{asset_id}/file")
def get_transcript_file(asset_id: str):
    """直接 serving 转写文件（支持浏览器内联查看 PDF / 下载 DOCX）"""
    try:
        transcript_path = AssetRepository.get_transcript_path(asset_id)
        if not transcript_path:
            raise HTTPException(status_code=404, detail="Transcript not found in database")

        transcripts_dir = get_transcripts_path()
        transcript_file = resolve_safe_path(transcripts_dir, transcript_path)
        if not transcript_file or not transcript_file.exists():
            raise HTTPException(status_code=404, detail="Transcript file not found on disk")

        media_type, _ = mimetypes.guess_type(str(transcript_file))
        if not media_type:
            media_type = "application/octet-stream"

        # PDF / 图片类浏览器可直接查看；其他格式触发下载
        disposition = "inline" if media_type in ("application/pdf", "image/png", "image/jpeg", "image/webp", "text/plain", "text/markdown") else "attachment"

        return FileResponse(
            path=transcript_file,
            media_type=media_type,
            filename=transcript_file.name,
            headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{transcript_file.name}"},
        )
    except HTTPException:
        raise
    except (OSError, ValueError, RuntimeError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{asset_id}/folder")
def browse_asset_folder(asset_id: str):
    """浏览素材对应的本地文件夹内容"""
    try:
        row = AssetRepository.find_by_id(asset_id)
        if not row:
            raise HTTPException(status_code=404, detail="Asset not found")

        folder_path = row.get("folder_path")
        if not folder_path:
            raise HTTPException(status_code=404, detail="该素材没有关联文件夹")

        transcripts_dir = get_transcripts_path()
        target_dir = resolve_safe_path(transcripts_dir, folder_path)
        if not target_dir or not target_dir.exists() or not target_dir.is_dir():
            raise HTTPException(status_code=404, detail="文件夹不存在")

        files = []
        for entry in sorted(target_dir.iterdir(), key=lambda e: e.name):
            if entry.is_file():
                stat = entry.stat()
                files.append({
                    "name": entry.name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "suffix": entry.suffix.lower(),
                })

        return {
            "path": str(target_dir.relative_to(transcripts_dir)),
            "files": files,
        }
    except HTTPException:
        raise
    except (OSError, ValueError, RuntimeError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{asset_id}")
def delete_asset(asset_id: str):
    try:
        with get_db_connection() as conn:
            # 开启事务，文件删除失败可回滚
            conn.execute("BEGIN IMMEDIATE")

            row = AssetRepository.find_for_deletion(asset_id)
            if not row:
                raise HTTPException(status_code=404, detail="Asset not found")

            failed = delete_asset_files(
                row['creator_uid'], row['source_url'], row['video_path'], row['transcript_path']
            )
            if failed:
                conn.rollback()
                raise HTTPException(status_code=500, detail=f"删除文件失败: {failed[0]}")

            # Phase 3: Delete from database (后删DB)
            AssetRepository.delete_with_fts(asset_id, conn=conn)
            conn.commit()

            return {"status": "success", "message": f"Asset {asset_id} deleted successfully"}

    except HTTPException:
        raise
    except OSError:
        raise
    except (sqlite3.Error, RuntimeError) as e:
        raise HTTPException(status_code=500, detail=str(e))


class AssetMarkRequest(BaseModel):
    is_read: Optional[bool] = None
    is_starred: Optional[bool] = None


@router.patch("/{asset_id}/mark")
def mark_asset(asset_id: str, req: AssetMarkRequest):
    """标记素材为已读/收藏"""
    if req.is_read is None and req.is_starred is None:
        raise HTTPException(status_code=400, detail="No fields to update")

    rowcount = AssetRepository.mark_asset(
        asset_id, is_read=req.is_read, is_starred=req.is_starred
    )
    if rowcount == 0:
        raise HTTPException(status_code=404, detail="Asset not found")
    return {"status": "success"}


class BulkAssetMarkRequest(BaseModel):
    ids: list[str]
    is_read: Optional[bool] = None
    is_starred: Optional[bool] = None

    @field_validator("ids")
    @classmethod
    def limit_batch_size(cls, v):
        if len(v) > 500:
            raise ValueError("单次批量操作最多 500 条")
        return v


@router.post("/bulk_mark")
def bulk_mark_assets(req: BulkAssetMarkRequest):
    """批量标记素材为已读/收藏"""
    if not req.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    if req.is_read is None and req.is_starred is None:
        raise HTTPException(status_code=400, detail="至少指定 is_read 或 is_starred")

    updated = AssetRepository.bulk_mark(
        req.ids, is_read=req.is_read, is_starred=req.is_starred
    )
    return {"status": "success", "updated": updated}


class BulkAssetDeleteRequest(BaseModel):
    ids: list[str]

    @field_validator("ids")
    @classmethod
    def limit_batch_size(cls, v):
        if len(v) > 200:
            raise ValueError("单次批量操作最多 200 条")
        return v


@router.post("/bulk_delete")
def bulk_delete_assets(req: BulkAssetDeleteRequest):
    """批量删除素材（含视频与转写文件）"""
    if not req.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")

    download_dir = get_download_path()
    transcripts_dir = get_transcripts_path()

    # Phase 1: 收集 + 删除 DB 行（事务内），磁盘删除留到 commit 后做。
    # 这样即便磁盘删除部分失败，也不会出现「DB 已回滚但文件已删除」的不一致。
    rows_to_clean: list[dict] = []
    deleted = 0
    with get_db_connection() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            rows_to_clean = AssetRepository.find_for_bulk_deletion(req.ids)
            deleted = AssetRepository.bulk_delete_with_fts(req.ids, conn=conn)
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise

    # Phase 2: DB 已提交，再做磁盘清理；失败仅记录日志，不影响接口结果
    failed_deletions: list[str] = []
    for row in rows_to_clean:
        failed = delete_asset_files(
            row["creator_uid"], row["source_url"], row["video_path"], row["transcript_path"],
            download_dir=download_dir, transcripts_dir=transcripts_dir,
        )
        if failed:
            failed_deletions.extend(failed)
    if failed_deletions:
        logger.warning(f"bulk_delete: {len(failed_deletions)} files failed to delete; sample={failed_deletions[:5]}")

    return {"status": "success", "deleted": deleted, "file_cleanup_failed": len(failed_deletions)}


@router.post("/cleanup")
def cleanup_missing_assets():
    """清理不存在的素材（视频文件已被删除的记录）"""
    download_dir = get_download_path()
    transcripts_dir = get_transcripts_path()

    deleted = 0
    with get_db_connection() as conn:
        rows = AssetRepository.list_all_for_cleanup()

        for row in rows:
            asset_id = row["asset_id"]
            creator_uid = row["creator_uid"]
            source_url = row["source_url"]
            video_path = row["video_path"]
            transcript_name = row["transcript_path"]

            video_exists = False
            transcript_exists = False

            # 检查视频文件是否存在
            if source_url or video_path:
                full_video_path = _resolve_asset_video_file(
                    creator_uid=creator_uid,
                    source_url=source_url,
                    video_path=video_path,
                    download_dir=download_dir,
                )
                if full_video_path and full_video_path.exists():
                    video_exists = True

            # 检查转写文件是否存在
            if transcript_name:
                full_transcript_path = resolve_safe_path(transcripts_dir, transcript_name)
                if full_transcript_path and full_transcript_path.exists():
                    transcript_exists = True

            # 如果视频和转写都不存在，删除记录
            if not video_exists and not transcript_exists:
                conn.execute("DELETE FROM media_assets WHERE asset_id = ?", (asset_id,))
                deleted += 1

        conn.commit()
    return {"status": "success", "deleted": deleted}


@router.post("/gc")
def gc_stale_assets():
    with get_db_connection() as conn:
        result = cleanup_stale_assets(conn)
    return {"status": "success", **result}

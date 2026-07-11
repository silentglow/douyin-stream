import io
import logging
import mimetypes
import sqlite3
import zipfile

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, field_validator

from media_tools.assets.file_ops import (
    _resolve_asset_video_file,
    delete_asset_files,
)
from media_tools.assets.gc import cleanup_stale_assets
from media_tools.assets.repository import AssetRepository
from media_tools.common.paths import get_download_path, get_transcripts_path
from media_tools.store.db import get_db_connection, resolve_query_value, resolve_safe_path

router = APIRouter(prefix="/api/v1/assets", tags=["assets"], redirect_slashes=False)
transcripts_router = APIRouter(prefix="/api/v1/transcripts", tags=["transcripts"], redirect_slashes=False)
logger = logging.getLogger(__name__)


@transcripts_router.get("")
def list_transcripts(
    status: str | None = Query(default="all", description="all / unread / starred"),
    availability: str | None = Query(
        default="local",
        description="local（默认，仅本地可读）/ missing / all",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """获取文稿列表。默认只返回本地文件仍存在的条目（可读）。"""
    try:
        avail = (availability or "local").strip().lower()
        if avail not in ("all", "local", "missing"):
            raise HTTPException(status_code=400, detail="availability must be all|local|missing")

        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            base_sql = """
                SELECT
                    a.asset_id, a.title, a.creator_uid, a.create_time,
                    a.is_read, a.is_starred, a.transcript_status, a.transcript_path,
                    a.transcript_preview,
                    c.nickname as creator_name
                FROM media_assets a
                LEFT JOIN creators c ON a.creator_uid = c.uid
                WHERE LOWER(a.transcript_status) = 'completed'
                  AND a.transcript_path IS NOT NULL
                  AND a.transcript_path != ''
            """
            params: list = []

            if status == "unread":
                base_sql += " AND (a.is_read = 0 OR a.is_read IS NULL)"
            elif status == "starred":
                base_sql += " AND a.is_starred = 1"

            # 磁盘存在性无法由 SQLite 可靠判断；过滤模式必须扫描完整结果集，
            # 否则第 500 条之后的文稿会丢失，total 和后续分页也会不准确。
            if avail == "all":
                base_sql += " ORDER BY a.create_time DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])
            else:
                base_sql += " ORDER BY a.create_time DESC"

            rows = conn.execute(base_sql, params).fetchall()
            transcripts_dir = get_transcripts_path()

            items: list[dict] = []
            local_count = 0
            missing_count = 0
            for r in rows:
                item = dict(r)
                path = item.get("transcript_path") or ""
                full = resolve_safe_path(transcripts_dir, path) if path else None
                exists = bool(full and full.is_file())
                item["file_exists"] = exists
                item["availability"] = "local" if exists else "missing"
                if exists:
                    local_count += 1
                else:
                    missing_count += 1
                if avail == "local" and not exists:
                    continue
                if avail == "missing" and exists:
                    continue
                items.append(item)

            if avail != "all":
                # 简单切片分页（在过滤后）
                total_filtered = len(items)
                items = items[offset : offset + limit]
                return {
                    "items": items,
                    "total": total_filtered,
                    "limit": limit,
                    "offset": offset,
                    "stats": {
                        "local": local_count,
                        "missing": missing_count,
                        "scanned": len(rows),
                    },
                }

            count_base = """
                SELECT COUNT(*) FROM media_assets a
                WHERE LOWER(a.transcript_status) = 'completed'
                  AND a.transcript_path IS NOT NULL
                  AND a.transcript_path != ''
            """
            count_params: list = []
            if status == "unread":
                count_base += " AND (a.is_read = 0 OR a.is_read IS NULL)"
            elif status == "starred":
                count_base += " AND a.is_starred = 1"

            total = conn.execute(count_base, count_params).fetchone()[0]

            return {
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset,
                "stats": {
                    "local": local_count,
                    "missing": missing_count,
                    "page": len(items),
                },
            }
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, RuntimeError) as e:
        logger.exception("list_transcripts failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
def list_assets(
    creator_uid: str | None = Query(None),
    transcript_status: str | None = Query(
        default=None,
        description="按转写状态过滤：completed / pending / none / failed；支持逗号分隔多个",
        max_length=200,
    ),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int | None = Query(default=None, ge=0),
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
    if len(asset_ids) > 200:
        raise HTTPException(status_code=400, detail="最多导出 200 个文稿")

    transcripts_dir = get_transcripts_path()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        used_filenames: set[str] = set()
        rows = AssetRepository.find_by_ids_for_export(asset_ids)
        for row in rows:
            transcript_file = resolve_safe_path(transcripts_dir, row["transcript_path"])
            if transcript_file and transcript_file.exists():
                suffix = transcript_file.suffix or ".md"
                stem = f"{row['title'] or row['asset_id']}"
                # 清理文件名
                stem = "".join(c for c in stem if c not in '<>:"/\\|?*').strip() or str(row["asset_id"])
                filename = f"{stem}{suffix}"
                if filename in used_filenames:
                    filename = f"{stem}-{row['asset_id']}{suffix}"
                used_filenames.add(filename)
                zf.writestr(filename, transcript_file.read_bytes())

    buffer.seek(0)
    return StreamingResponse(
        buffer, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=transcripts.zip"}
    )


@router.get("/{asset_id}/transcript")
def get_transcript(asset_id: str = Path(..., min_length=1, max_length=128)):
    try:
        transcript_path = AssetRepository.get_transcript_path(asset_id)

        if not transcript_path:
            raise HTTPException(status_code=404, detail="Transcript not found in database")

        transcripts_dir = get_transcripts_path()
        transcript_file = resolve_safe_path(transcripts_dir, transcript_path)

        if not transcript_file or not transcript_file.exists():
            raise HTTPException(status_code=404, detail="Transcript file not found on disk")

        suffix = transcript_file.suffix.lower()
        if suffix == ".docx" or suffix == ".pdf":
            from media_tools.transcribe.preview import extract_transcript_text

            content = extract_transcript_text(transcript_file)
        else:
            content = transcript_file.read_text(encoding="utf-8", errors="replace")

        return {
            "content": content,
            "format": "markdown" if suffix == ".md" else "text",
            "file_path": str(transcript_file.relative_to(transcripts_dir)) if transcript_file else None,
        }

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
        disposition = (
            "inline"
            if media_type in ("application/pdf", "image/png", "image/jpeg", "image/webp", "text/plain", "text/markdown")
            else "attachment"
        )

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
                files.append(
                    {
                        "name": entry.name,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "suffix": entry.suffix.lower(),
                    }
                )

        return {
            "path": str(target_dir.relative_to(transcripts_dir)),
            "files": files,
        }
    except HTTPException:
        raise
    except (OSError, ValueError, RuntimeError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{asset_id}")
def delete_asset(asset_id: str = Path(..., min_length=1, max_length=128)):
    try:
        with get_db_connection() as conn:
            # 开启事务，文件删除失败可回滚
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = AssetRepository.find_for_deletion(asset_id)
                if not row:
                    conn.rollback()
                    raise HTTPException(status_code=404, detail="Asset not found")

                failed = delete_asset_files(
                    row["creator_uid"], row["source_url"], row["video_path"], row["transcript_path"]
                )
                if failed:
                    conn.rollback()
                    raise HTTPException(status_code=500, detail=f"删除文件失败: {failed[0]}")

                # Phase 3: Delete from database (后删DB)
                AssetRepository.delete_with_fts(asset_id, conn=conn)
                conn.commit()

                return {"status": "success", "message": f"Asset {asset_id} deleted successfully"}
            except HTTPException:
                conn.rollback()
                raise
            except (OSError, sqlite3.Error, RuntimeError) as e:
                conn.rollback()
                raise HTTPException(status_code=500, detail=str(e))

    except HTTPException:
        raise


class AssetMarkRequest(BaseModel):
    is_read: bool | None = None
    is_starred: bool | None = None


@router.patch("/{asset_id}/mark")
def mark_asset(asset_id: str, req: AssetMarkRequest):
    """标记素材为已读/收藏"""
    if req.is_read is None and req.is_starred is None:
        raise HTTPException(status_code=400, detail="No fields to update")

    rowcount = AssetRepository.mark_asset(asset_id, is_read=req.is_read, is_starred=req.is_starred)
    if rowcount == 0:
        raise HTTPException(status_code=404, detail="Asset not found")
    return {"status": "success"}


class BulkAssetMarkRequest(BaseModel):
    ids: list[str]
    is_read: bool | None = None
    is_starred: bool | None = None

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

    updated = AssetRepository.bulk_mark(req.ids, is_read=req.is_read, is_starred=req.is_starred)
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
            row["creator_uid"],
            row["source_url"],
            row["video_path"],
            row["transcript_path"],
            download_dir=download_dir,
            transcripts_dir=transcripts_dir,
        )
        if failed:
            failed_deletions.extend(failed)
    if failed_deletions:
        logger.warning(f"bulk_delete: {len(failed_deletions)} files failed to delete; sample={failed_deletions[:5]}")

    return {
        "status": "success",
        "deleted": deleted,
        "file_cleanup_failed": len(failed_deletions),
        # 返回具体路径让前端可以提示用户手动清理（DB 行已无，否则会形成孤儿文件泄漏磁盘空间）
        "failed_paths": failed_deletions,
    }


@router.post("/cleanup")
def cleanup_missing_assets():
    """清理不存在的素材（视频文件已被删除的记录）"""
    download_dir = get_download_path()
    transcripts_dir = get_transcripts_path()

    with get_db_connection() as conn:
        rows = AssetRepository.list_all_for_cleanup()

        ids_to_delete: list[str] = []
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

            # 如果视频和转写都不存在，纳入待删
            if not video_exists and not transcript_exists:
                ids_to_delete.append(asset_id)

        # 走 bulk_delete_with_fts 同步删 assets_fts，否则搜索栏会出现已删素材的幽灵命中（点入 404）
        deleted = AssetRepository.bulk_delete_with_fts(ids_to_delete, conn=conn)
        conn.commit()
    return {"status": "success", "deleted": deleted}


@router.post("/gc")
def gc_stale_assets():
    with get_db_connection() as conn:
        result = cleanup_stale_assets(conn)
    return {"status": "success", **result}

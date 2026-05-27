from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
import uuid as _uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from media_tools.assets.file_ops import _resolve_asset_video_file, get_source_url_column
from media_tools.common.paths import get_download_path, get_transcripts_path
from media_tools.core.config import get_runtime_setting_bool
from media_tools.scheduler.base import BaseWorker, register_worker
from media_tools.scheduler.repository import TaskRepository
from media_tools.services.cleanup import cleanup_paths_allowlist, cleanup_task_cache_dir
from media_tools.store.db import get_db_connection
from media_tools.transcribe.worker import run_local_transcribe

logger = logging.getLogger(__name__)


def _normalize_stem(value: str) -> str:
    return re.sub(r"_[0-9]+$", "", value or "")


def _safe_creator_folder_name(value: str) -> str:
    name = (value or "").strip()
    if not name:
        return "unknown"
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"[\s_]+", "_", name).strip("_")
    return name or "unknown"


def _derive_creator_folder(file_paths: list[str], downloads_root: Path, uid: str) -> str:
    if file_paths:
        try:
            rel = Path(file_paths[0]).resolve().relative_to(downloads_root.resolve())
            if rel.parts:
                return _safe_creator_folder_name(rel.parts[0])
        except (OSError, ValueError):
            pass
    return _safe_creator_folder_name(uid)


def _build_cleanup_candidates(video_path: Path) -> list[Path]:
    suffixes = [".wav", ".m4a", ".aac", ".mp3", ".tmp", ".part"]
    base = [video_path]
    siblings = [video_path.with_suffix(s) for s in suffixes]
    unique: list[Path] = []
    seen: set[str] = set()
    for p in base + siblings:
        if not p.exists():
            continue
        try:
            rp = str(p.resolve())
        except OSError:
            rp = str(p)
        if rp in seen:
            continue
        seen.add(rp)
        unique.append(p)
    return unique


def _discover_creator_files(uid: str) -> tuple[list[str], list[str]]:
    download_dir = get_download_path()
    file_paths: list[str] = []
    not_found: list[str] = []

    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            source_url_select = get_source_url_column(conn)
            cursor = conn.execute(
                f"""SELECT asset_id, creator_uid, {source_url_select} video_path
                    FROM media_assets
                    WHERE creator_uid = ?
                      AND video_status IN ('downloaded', 'pending')
                      AND transcript_status IN ('pending', 'none', 'failed')
                    """,
                (uid,),
            )
            for row in cursor.fetchall():
                resolved = _resolve_asset_video_file(
                    creator_uid=row["creator_uid"],
                    source_url=row["source_url"],
                    video_path=row["video_path"],
                    download_dir=download_dir,
                )
                if resolved and resolved.exists():
                    file_paths.append(str(resolved))
                    continue

                video_path = row["video_path"] or ""
                filename = Path(video_path).name if video_path else ""
                if not filename:
                    continue

                found = None
                stem = Path(filename).stem
                for match in download_dir.rglob(f"{stem}*.mp4"):
                    if match.is_file():
                        found = match
                        break
                if not found:
                    for match in download_dir.rglob(f"{stem}*"):
                        if match.is_file() and match.suffix.lower() in (".mp4", ".webm", ".mkv", ".avi", ".mov"):
                            found = match
                            break

                if found:
                    file_paths.append(str(found))
                    try:
                        new_rel = str(found.relative_to(download_dir))
                        conn.execute(
                            "UPDATE media_assets SET video_path = ? WHERE asset_id = ?",
                            (new_rel, row["asset_id"]),
                        )
                    except (ValueError, sqlite3.Error):
                        pass
                else:
                    not_found.append(filename)
    except (sqlite3.Error, OSError) as e:
        raise RuntimeError(f"查询待转写素材失败: {e}") from e

    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT DISTINCT folder_path FROM media_assets WHERE creator_uid = ? AND folder_path IS NOT NULL",
                (uid,),
            )
            folder_names = [row["folder_path"] for row in cursor.fetchall() if row["folder_path"]]

            cursor2 = conn.execute("SELECT nickname FROM creators WHERE uid = ?", (uid,))
            nickname_row = cursor2.fetchone()
            if nickname_row and nickname_row["nickname"]:
                folder_names.append(nickname_row["nickname"])

            cursor3 = conn.execute(
                "SELECT video_path FROM media_assets WHERE creator_uid = ? AND video_path IS NOT NULL AND video_path != ''",
                (uid,),
            )
            completed_stems: set[str] = set()
            for row in cursor3.fetchall():
                vp = row["video_path"] or ""
                if vp:
                    completed_stems.add(_normalize_stem(Path(vp).stem))

            for folder_name in folder_names:
                folder = download_dir / folder_name
                if not folder.is_dir():
                    continue
                for f in folder.glob("*.mp4"):
                    if _normalize_stem(f.stem) in completed_stems:
                        continue
                    file_paths.append(str(f))
                    try:
                        asset_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, str(f.resolve())))
                        now = datetime.now().isoformat()
                        conn.execute(
                            """INSERT OR IGNORE INTO media_assets
                               (asset_id, creator_uid, title, video_path, video_status, transcript_status, folder_path, create_time, update_time)
                               VALUES (?, ?, ?, ?, 'downloaded', 'pending', ?, ?, ?)""",
                            (
                                asset_id,
                                uid,
                                f.stem,
                                str(f.relative_to(download_dir)),
                                folder_name,
                                now,
                                now,
                            ),
                        )
                    except (sqlite3.Error, OSError, ValueError):
                        pass

            if file_paths:
                conn.execute(
                    """UPDATE media_assets SET transcript_status = 'pending'
                       WHERE creator_uid = ? AND transcript_status = 'none'
                          AND video_status IN ('downloaded', 'pending')""",
                    (uid,),
                )
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"扫描下载目录失败: {e}")

    return file_paths, not_found


@register_worker("creator_transcribe")
class CreatorTranscribeWorker(BaseWorker):
    """创作者转写 Worker：扫描创作者待转写文件并批量转写。"""

    task_type = "creator_transcribe"

    def _get_task_context_kwargs(self, **run_kwargs: Any) -> dict[str, Any]:
        return {"creator_uid": run_kwargs.get("uid", "")}

    async def run(
        self,
        task_id: str,
        *,
        uid: str,
        delete_after: bool | None = None,
    ) -> None:
        # Phase 1: 扫描（在 heartbeat 内执行，与旧行为一致）
        await self.report_progress(0.01, "正在扫描待转写文件...", stage="scanning")
        file_paths, not_found = await asyncio.to_thread(_discover_creator_files, uid)

        if not file_paths:
            message = (
                f"该博主有 {len(not_found)} 个待转写素材，但视频文件在磁盘上找不到"
                if not_found
                else "该博主没有待转写的素材"
            )
            await self.finalize_failure(message)
            return

        TaskRepository.patch_payload(task_id, {"creator_uid": uid, "file_paths": file_paths})
        await self.report_progress(
            0.02,
            f"扫描完成，准备转写 {len(file_paths)} 个文件",
            stage="queued",
            pipeline_progress={"transcribe": {"done": 0, "total": int(len(file_paths) or 0)}},
        )

        downloads_root = get_download_path().resolve()
        transcripts_root = get_transcripts_path().resolve()
        creator_folder = _derive_creator_folder(file_paths, downloads_root, uid)
        cache_dir = transcripts_root / creator_folder / ".cache" / task_id
        cache_dir.mkdir(parents=True, exist_ok=True)
        TaskRepository.patch_payload(task_id, {"cleanup_cache_dir": str(cache_dir)})

        should_delete = delete_after if delete_after is not None else get_runtime_setting_bool("auto_delete", True)
        result = await run_local_transcribe(file_paths, self._progress_fn, delete_after=False, task_id=task_id)
        s_count = int(result.get("success_count", 0) or 0)
        f_count = int(result.get("failed_count", 0) or 0)
        total = int(result.get("total", s_count + f_count) or (s_count + f_count))
        success_paths = [Path(p) for p in (result.get("success_paths") or []) if isinstance(p, str)]

        deleted_count = 0
        failed_paths: list[Path] = []

        if should_delete:
            await self.report_progress(
                0.95,
                "转写完成，开始清理源文件与临时文件...",
                stage="cleanup",
            )
            cleanup_candidates: list[Path] = []
            for sp in success_paths:
                cleanup_candidates.extend(_build_cleanup_candidates(sp))

            outcome = cleanup_paths_allowlist(
                cleanup_candidates,
                downloads_root=downloads_root,
                transcripts_root=transcripts_root,
            )
            deleted_count = outcome.deleted_count
            failed_paths = list(outcome.failed_paths)

            cache_outcome = cleanup_task_cache_dir(cache_dir)
            deleted_count += cache_outcome.deleted_count
            failed_paths = [*failed_paths, *cache_outcome.failed_paths]

            TaskRepository.patch_payload(
                task_id,
                {
                    "cleanup_deleted_count": deleted_count,
                    "cleanup_failed_count": len(failed_paths),
                    "cleanup_failed_paths": [{"path": fp.path, "reason": fp.reason} for fp in failed_paths],
                    "cleanup_cache_dir": str(cache_dir),
                },
            )
        else:
            cache_outcome = cleanup_task_cache_dir(cache_dir)
            TaskRepository.patch_payload(
                task_id,
                {
                    "cleanup_deleted_count": cache_outcome.deleted_count,
                    "cleanup_failed_count": len(cache_outcome.failed_paths),
                    "cleanup_cache_dir": str(cache_dir),
                },
            )

        msg = (
            "没有找到有效的音视频文件"
            if total == 0
            else (
                f"转写完成：成功 {s_count} 个，失败 {f_count} 个；"
                f"清理：已删除 {deleted_count} 个，失败 {len(failed_paths)} 个"
                if should_delete
                else f"转写完成：成功 {s_count} 个，失败 {f_count} 个"
            )
        )
        await self.report_progress(
            1.0,
            msg,
            stage="done",
            pipeline_progress={"transcribe": {"done": int(total or 0), "total": int(total or 0)}},
        )
        result_summary = {
            "success": int(s_count or 0),
            "failed": int(f_count or 0),
            "total": int(total or 0),
        }
        subtasks = result.get("subtasks") if isinstance(result, dict) else None
        if f_count == 0:
            await self.finalize_success(msg, result_summary=result_summary, subtasks=subtasks)
        elif s_count > 0:
            await self.finalize_partial(
                msg,
                error_msg=f"转写失败 {f_count} 个文件",
                result_summary=result_summary,
                subtasks=subtasks,
            )
        else:
            await self.finalize_failure(
                msg,
                error_msg=f"转写失败 {f_count} 个文件",
                result_summary=result_summary,
                subtasks=subtasks,
            )

    async def _progress_fn(self, p: float, m: str, stage: str = "", pipeline_progress: dict | None = None) -> None:
        await self.report_progress(p, m, stage=stage, pipeline_progress=pipeline_progress)

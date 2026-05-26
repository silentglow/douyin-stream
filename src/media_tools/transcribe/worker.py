from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any, Optional
from media_tools.logger import get_logger
from media_tools.store.db import local_asset_id
from media_tools.transcribe.task_helpers import call_progress, create_managed_task, filter_supported_media_paths

logger = get_logger('pipeline')


async def run_local_transcribe(file_paths: list[str], update_progress_fn=None, delete_after: bool = False, task_id: Optional[str] = None):
    """转写本地视频文件（不经过下载步骤）"""
    from media_tools.core.config import load_pipeline_config
    from media_tools.transcribe.service import create_orchestrator

    valid_paths = filter_supported_media_paths(file_paths)

    if not valid_paths:
        return {"success_count": 0, "failed_count": 0, "total": 0, "success_paths": [], "failed_paths": []}

    valid_paths, split_registry = await _prepare_split_paths(valid_paths, update_progress_fn)

    if not valid_paths:
        return {"success_count": 0, "failed_count": 0, "total": 0, "success_paths": [], "failed_paths": []}

    config = load_pipeline_config()
    orchestrator = create_orchestrator(config)
    if hasattr(orchestrator, '_account_pool_service'):
        orchestrator._account_pool_service.resolve_accounts()
        effective_concurrency = orchestrator._account_pool_service.effective_concurrency or config.concurrency
    else:
        effective_concurrency = config.concurrency

    total = len(valid_paths)
    await call_progress(
        update_progress_fn,
        0.02,
        f"准备转写 {total} 个文件（并发 {effective_concurrency}）",
        stage="transcribe",
        pipeline_progress={"transcribe": {"done": 0, "total": total}},
    )
    from media_tools.store.db import get_db_connection
    from media_tools.transcribe.preview import extract_transcript_preview, extract_transcript_text

    subtasks: list[dict[str, Any]] = []
    success_paths: list[str] = []
    failed_paths: list[str] = []

    _pb_done = 0

    def _progress_callback(current: int, total_cb: int, video_path: Path, status: str, account_id: Optional[str] = None):
        nonlocal _pb_done
        if current == 1 and total_cb == 1:
            _pb_done += 1
        progress = 0.02 + 0.93 * (_pb_done / total) if total > 0 else 0.02
        transcribe_info: dict[str, Any] = {"done": _pb_done, "total": total}
        if account_id:
            transcribe_info["account_id"] = account_id
        create_managed_task(
            call_progress(
                update_progress_fn,
                progress,
                status,
                stage="transcribe",
                pipeline_progress={"transcribe": transcribe_info},
            )
        )

    orchestrator.on_progress = _progress_callback

    report = await orchestrator.transcribe_batch(valid_paths, resume=False)

    if split_registry:
        _cleanup_split_parts(split_registry, report)

    # 批量处理额外 DB 更新（preview / text / FTS）和删除
    for item in report.results:
        video_path_str = item.get("video_path", "")
        success = item.get("success", False)
        video_path = Path(video_path_str) if video_path_str else None

        if success and video_path:
            transcript_path = item.get("transcript_path")
            if transcript_path:
                tp = Path(transcript_path)
                preview = extract_transcript_preview(str(tp))
                full_text = extract_transcript_text(str(tp))
                try:
                    with get_db_connection() as conn:
                        asset_id = local_asset_id(video_path)
                        conn.execute(
                            """
                            UPDATE media_assets
                            SET transcript_preview = ?, transcript_text = ?, update_time = CURRENT_TIMESTAMP
                            WHERE asset_id = ?
                            """,
                            (preview, full_text, asset_id),
                        )
                        try:
                            title_row = conn.execute(
                                "SELECT title FROM media_assets WHERE asset_id = ?",
                                (asset_id,),
                            ).fetchone()
                            conn.execute(
                                "INSERT OR REPLACE INTO assets_fts(asset_id, title, transcript_text) VALUES (?, ?, ?)",
                                (asset_id, title_row["title"] if title_row else "", full_text or ""),
                            )
                        except sqlite3.Error as fts_err:
                            logger.error(f"FTS索引更新失败 (asset={asset_id}): {fts_err}")
                        conn.commit()
                except sqlite3.Error as db_err:
                    logger.error(f"DB更新失败 (asset={local_asset_id(video_path)}): {db_err}")

            success_paths.append(str(video_path))
            subtasks.append({"title": video_path.stem, "status": "completed"})

            if delete_after and video_path.exists():
                if transcript_path and Path(transcript_path).exists():
                    from media_tools.assets.service import MediaAssetService
                    MediaAssetService.mark_archived(video_path)
                    try:
                        video_path.unlink()
                    except FileNotFoundError:
                        pass
                    except OSError as e:
                        logger.error(f"删除视频失败: {video_path}, {e}")
                else:
                    logger.warning(f"跳过删除源视频：转录文件不存在或已丢失 ({transcript_path})")
        else:
            if video_path:
                failed_paths.append(str(video_path))
            err_type = item.get("error_type", "")
            err_msg = item.get("error")
            attempts = item.get("attempts")
            error_text = ""
            if err_type and err_type != "unknown":
                error_text = f"{err_type}: {err_msg}" if err_msg else err_type
            else:
                error_text = str(err_msg) if err_msg else "unknown"
            if attempts and isinstance(attempts, int) and attempts > 1:
                error_text = f"{error_text} (attempts={attempts})"
            subtasks.append({
                "title": video_path.stem if video_path else "未知",
                "status": "failed",
                "error": error_text,
                "error_type": err_type or None,
                "attempts": attempts,
                "video_path": str(video_path) if video_path else None,
            })

    await call_progress(
        update_progress_fn,
        0.98,
        f"转写完成，正在汇总 {total} 个结果...",
        stage="transcribe",
        pipeline_progress={"transcribe": {"done": total, "total": total}},
    )

    return {
        "success_count": report.success,
        "failed_count": report.failed,
        "total": total,
        "subtasks": subtasks,
        "success_paths": success_paths,
        "failed_paths": failed_paths,
    }


def _build_progress_callback(update_progress_fn, base_progress: float):
    """构建转写进度回调，将单视频完成事件聚合为批量进度。"""
    _pb_done = 0

    def _progress_callback(current: int, total: int, video_path: Path, status: str, account_id: Optional[str] = None):
        nonlocal _pb_done
        if current == 1 and total == 1:
            _pb_done += 1
        progress = base_progress + (1.0 - base_progress) * (_pb_done / total) if total > 0 else base_progress
        transcribe_info: dict[str, Any] = {"done": _pb_done, "total": total}
        if account_id:
            transcribe_info["account_id"] = account_id
        pp = {"transcribe": transcribe_info}
        try:
            result = update_progress_fn(progress, status, "transcribe", pp)
        except TypeError:
            try:
                result = update_progress_fn(progress, status, "transcribe")
            except TypeError:
                result = update_progress_fn(progress, status)
        if inspect.isawaitable(result):
            create_managed_task(result)
        elif result is not None:
            logger.warning(f"update_progress_fn 返回非协程: {type(result)}")
        return None

    return _progress_callback


def _extract_export_file(report) -> Optional[str]:
    """从转写报告中提取最后一个成功的导出文件路径。"""
    for item in reversed(getattr(report, "results", []) or []):
        transcript_path = item.get("transcript_path") if isinstance(item, dict) else None
        if isinstance(transcript_path, str) and transcript_path.strip():
            return transcript_path.strip()
    return None


def _extract_successful_paths(report) -> set[str]:
    """从转写报告中提取所有成功转写的视频路径（绝对路径字符串）。"""
    return {
        str(Path(item["video_path"]).resolve())
        for item in getattr(report, "results", [])
        if item.get("success") and item.get("video_path")
    }


async def _prepare_split_paths(
    paths: list[Path],
    update_progress_fn,
) -> tuple[list[Path], dict[Path, list[Path]]]:
    """检测 paths 中 > 6GB 的源文件，用 ffmpeg `-c copy` 切分成多个 ≤ 6GB 的 part。
    返回 (展开后的 paths 列表, 原文件 -> part 列表 映射)。

    切分失败的源文件会被剔除并记 ERROR 日志，避免把它丢给云端再失败一次浪费时间。
    """
    from media_tools.transcribe import splitter

    to_split = [p for p in paths if splitter.needs_split(p)]
    if not to_split:
        return paths, {}

    await call_progress(
        update_progress_fn,
        0.01,
        f"检测到 {len(to_split)} 个 > 6GB 文件，正在切分...",
        stage="transcribe",
    )

    new_paths: list[Path] = []
    registry: dict[Path, list[Path]] = {}

    for p in paths:
        if not splitter.needs_split(p):
            new_paths.append(p)
            continue
        try:
            parts = await asyncio.to_thread(splitter.split_video, p)
            logger.info(f"文件已切分: {p.name} -> {len(parts)} part(s)")
            new_paths.extend(parts)
            registry[p] = parts
        except splitter.SplitError as e:
            logger.error(f"文件切分失败，跳过该文件: {p} - {e}")

    return new_paths, registry


def _cleanup_split_parts(registry: dict[Path, list[Path]], report) -> None:
    """根据 transcribe_batch 报告清理已成功转写的 part 文件；失败的 part 保留供排查。"""
    from media_tools.transcribe import splitter

    successful = _extract_successful_paths(report)

    for source, parts in registry.items():
        for part in parts:
            if str(Path(part).resolve()) in successful:
                splitter.cleanup_part(part)
        splitter.cleanup_cache_dir_if_empty(source)


def _delete_transcribed_videos(video_paths: list[Path], successful_paths: set[str]) -> None:
    """删除已成功转写的视频文件，并将 media_assets.video_status 标记为 archived。"""
    from media_tools.assets.service import MediaAssetService
    for path in video_paths:
        if str(path.resolve()) not in successful_paths:
            continue
        MediaAssetService.mark_archived(path)
        if path.exists():
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as e:
                logger.error(f"删除视频失败 (DB已更新): {path}, {e}")


def _build_subtasks(video_paths: list[Path], report) -> list[dict[str, Any]]:
    """从转写报告构建子任务列表（O(N) Map 查找）。"""
    result_by_path: dict[str, dict] = {}
    for r in getattr(report, "results", []) or []:
        vp = r.get("video_path", "") if isinstance(r, dict) else ""
        if vp:
            result_by_path[str(Path(vp).resolve())] = r

    subtasks: list[dict[str, Any]] = []
    for video_path in video_paths:
        result_item = result_by_path.get(str(video_path.resolve()))
        status = "completed" if result_item and result_item.get("success") else "failed"
        error = result_item.get("error") if result_item else None
        transcript_path = result_item.get("transcript_path") if result_item and result_item.get("success") else None
        transcript_path = transcript_path if isinstance(transcript_path, str) and transcript_path.strip() else None
        sub: dict[str, Any] = {
            "title": video_path.stem,
            "status": status,
            "error": error,
        }
        if transcript_path:
            sub["transcript_path"] = transcript_path
        # 失败的子任务必须带 video_path，否则 /tasks/{id}/retry-failed 无法找到路径，
        # 前端 failedRetryableCount 也会算成 0，"只重试失败" 按钮不显示。
        if status == "failed":
            sub["video_path"] = str(video_path)
        subtasks.append(sub)
    return subtasks


def _find_existing_videos_for_pipeline(url: str, platform: str) -> list[str]:
    """Pipeline 重试时：下载阶段返回空，尝试从数据库查找已下载的本地视频。"""
    from media_tools.common.paths import get_download_path

    downloads_path = get_download_path()
    existing: list[str] = []

    if platform == "bilibili":
        from media_tools.bilibili.core.url_parser import normalize_bilibili_url, BilibiliUrlKind
        normalized = normalize_bilibili_url(url)

        if normalized.kind == BilibiliUrlKind.SPACE and normalized.mid:
            creator_uid = f"bilibili_{normalized.mid}"
            rows = _query_media_assets(creator_uid=creator_uid, platform="bilibili")
            existing = _collect_existing_paths(rows, downloads_path)
            if existing:
                logger.info(f"B 站 pipeline 重试：从数据库找到 {len(existing)} 个已下载视频 (creator={creator_uid})")

        elif normalized.kind == BilibiliUrlKind.VIDEO and normalized.bvid:
            # 单个视频：通过 asset_id 或 source_url 匹配
            rows = _query_media_assets(
                asset_id_prefix=f"bilibili_{normalized.bvid}",
                source_url_pattern=f"%{normalized.bvid}%",
                platform="bilibili",
            )
            existing = _collect_existing_paths(rows, downloads_path)
            if existing:
                logger.info(f"B 站 pipeline 重试：从数据库找到单个已下载视频 (bvid={normalized.bvid})")
            else:
                # 兜底：数据库没有记录时，扫描下载目录按 bvid 匹配文件名
                # 兼容旧路径 bilibili/全部投稿 和新路径 <nickname>/全部投稿
                scan_dirs = [downloads_path / "bilibili" / "全部投稿"]
                for d in downloads_path.iterdir():
                    if d.is_dir() and d.name != "bilibili":
                        sub = d / "全部投稿"
                        if sub.exists():
                            scan_dirs.append(sub)
                mp4_files = []
                for scan_dir in scan_dirs:
                    if scan_dir.exists():
                        mp4_files.extend(
                            f for f in scan_dir.glob("*.mp4")
                            if f.stat().st_size > 10240
                        )
                # 优先匹配文件名中包含 bvid 的视频
                matched = [f for f in mp4_files if normalized.bvid in f.name]
                candidates = matched if matched else mp4_files
                if candidates:
                    candidates = sorted(candidates, key=lambda f: f.stat().st_mtime, reverse=True)
                    existing.append(str(candidates[0]))
                    logger.info(f"B 站 pipeline 兜底：扫描目录找到视频 {candidates[0].name}")

    return existing


def _query_media_assets(
    *,
    creator_uid: str | None = None,
    asset_id_prefix: str | None = None,
    source_url_pattern: str | None = None,
    platform: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """根据条件查询 media_assets 表中的视频记录。"""
    import sqlite3
    from media_tools.store.db import get_db_connection

    clauses: list[str] = ["video_status IN ('downloaded', 'pending', 'archived')"]
    params: list = []

    if creator_uid:
        clauses.append("creator_uid = ?")
        params.append(creator_uid)
    if asset_id_prefix:
        clauses.append("asset_id LIKE ?")
        params.append(f"{asset_id_prefix}%")
    if source_url_pattern:
        clauses.append("source_url LIKE ?")
        params.append(source_url_pattern)
    if platform:
        clauses.append("source_platform = ?")
        params.append(platform)

    sql = f"""
        SELECT video_path FROM media_assets
        WHERE {' AND '.join(clauses)}
        ORDER BY update_time DESC
        LIMIT ?
    """
    params.append(limit)

    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as e:
        logger.warning(f"查询 media_assets 失败: {e}")
        return []


def _collect_existing_paths(rows: list[dict], downloads_path) -> list[str]:
    """从查询结果中收集磁盘上确实存在的视频路径。"""
    existing: list[str] = []
    for row in rows:
        vp = row.get("video_path")
        if not vp:
            continue
        p = downloads_path / vp
        if p.exists():
            existing.append(str(p))
    return existing


async def run_pipeline_for_user(url: str, max_counts: int, update_progress_fn, delete_after: bool = True, task_id: Optional[str] = None):
    from media_tools.download.service import download_by_url as download_router
    from media_tools.download.service import resolve_platform
    from media_tools.core.config import load_pipeline_config
    from media_tools.transcribe.service import create_orchestrator

    await call_progress(update_progress_fn, 0.1, "正在下载视频...", stage="download",
                        pipeline_progress={"download": {"done": 0, "total": max_counts or 0}})

    # 1. Download - 使用 router（会自动选择 yt-dlp 或回退到 F2）
    platform = resolve_platform(url)

    try:
        if platform == "bilibili":
            # B站使用 yt-dlp
            from media_tools.platform.bilibili import download_up_by_url as bilibili_download
            dl_result = await asyncio.wait_for(
                asyncio.to_thread(bilibili_download, url, max_counts, True, None, task_id),
                timeout=600,
            )
        else:
            # 抖音使用 download_router（会自动选择 yt-dlp 视频或回退到 F2 用户主页）
            # disable_auto_transcribe=True：pipeline 模式由 run_pipeline_for_user 自己控制转写
            dl_result = await asyncio.wait_for(
                asyncio.to_thread(download_router, url, max_counts, True, True, task_id),
                timeout=600,
            )
    except asyncio.TimeoutError:
        logger.error(f"下载超时 (task_id={task_id}): {url}")
        await call_progress(update_progress_fn, 1.0, "下载超时，请检查网络或链接是否可用", stage="failed")
        return {"success_count": 0, "failed_count": 0, "error": "下载超时"}
    except asyncio.CancelledError:
        logger.info(f"下载任务被取消 (task_id={task_id})")
        raise

    # 检查是否被取消（下载完成后）
    if (hasattr(dl_result, 'raw') and isinstance(dl_result.raw, dict) and dl_result.raw.get("cancelled")) or \
       (isinstance(dl_result, dict) and dl_result.get("cancelled")):
        await call_progress(update_progress_fn, 1.0, "任务已取消", stage="failed")
        return {"success_count": 0, "failed_count": 0, "cancelled": True}

    if hasattr(dl_result, 'new_files'):
        new_files = list(dl_result.new_files) if dl_result.new_files else []
    elif isinstance(dl_result, dict):
        new_files = dl_result.get('new_files', [])
    else:
        new_files = []

    # 没有新下载的视频时，尝试查找已存在的本地视频（重试场景）
    if not new_files:
        new_files = _find_existing_videos_for_pipeline(url, platform)

    if not new_files:
        await call_progress(update_progress_fn, 1.0, "没有下载到新视频", stage="done")
        return {"success_count": 0, "failed_count": 0}

    await call_progress(update_progress_fn, 0.4, f"下载完成，准备转写 {len(new_files)} 个视频...", stage="transcribe",
                        pipeline_progress={"download": {"done": len(new_files), "total": len(new_files)}})

    # 2. Transcribe (并发批量转写)
    config = load_pipeline_config()
    orchestrator = create_orchestrator(config)

    total = len(new_files)

    # 使用批量并发转写
    # _fire_progress 在 transcribe_with_retry 内按单视频语义上报 (current=0/1, total=1)，
    # 但前端需要批量进度。闭包内自己维护 done 计数，按 "current==1 and total==1"
    # 识别单个视频完成，从而把进度平滑推进到 0.4→1.0。
    orchestrator.on_progress = _build_progress_callback(update_progress_fn, 0.4)

    # 转换为 Path 对象
    video_paths = [Path(f) for f in new_files]

    # 并发执行批量转写
    report = await orchestrator.transcribe_batch(video_paths, resume=False)

    success_count = report.success
    failed_count = report.failed
    export_file = _extract_export_file(report)
    successful_paths = _extract_successful_paths(report)

    # 删除已转写的视频（如果配置了 delete_after）
    if delete_after:
        _delete_transcribed_videos(video_paths, successful_paths)

    await call_progress(update_progress_fn, 1.0, f"流水线完成: 成功 {success_count}, 失败 {failed_count}", stage="done")

    subtasks = _build_subtasks(video_paths, report)

    return {
        "success_count": success_count,
        "failed_count": failed_count,
        "total": total,
        "subtasks": subtasks,
        **({"export_file": export_file} if export_file else {}),
    }

async def run_batch_pipeline(video_urls: list[str], update_progress_fn, delete_after: bool = True, task_id: Optional[str] = None):
    from media_tools.download.service import download_by_url as download_router
    from media_tools.core.config import load_pipeline_config
    from media_tools.transcribe.service import create_orchestrator

    total = len(video_urls)
    if total == 0:
        return {"success_count": 0, "failed_count": 0}

    new_files = []

    # Download phase
    for i, url in enumerate(video_urls):
        await call_progress(update_progress_fn, 0.4 * (i / total), f"正在下载 ({i+1}/{total})", stage="download")
        try:
            dl_result = await asyncio.wait_for(
                asyncio.to_thread(download_router, url, 1, True, True, task_id),
                timeout=300,
            )
        except asyncio.TimeoutError:
            logger.error(f"批量下载超时: {url}")
            continue
        if hasattr(dl_result, 'new_files') and dl_result.new_files:
            new_files.extend(dl_result.new_files)
        elif isinstance(dl_result, dict) and dl_result.get('new_files'):
            new_files.extend(dl_result['new_files'])

    if not new_files:
        return {"success_count": 0, "failed_count": total}

    # Transcribe phase (并发批量转写)
    config = load_pipeline_config()
    orchestrator = create_orchestrator(config)

    total = len(new_files)

    # 使用批量并发转写
    # 与 run_pipeline_for_user 同理：_fire_progress 按单视频语义上报，
    # 闭包内维护 done 计数，把进度平滑推进。
    orchestrator.on_progress = _build_progress_callback(update_progress_fn, 0.4)

    video_paths = [Path(f) for f in new_files]
    report = await orchestrator.transcribe_batch(video_paths, resume=False)

    success_count = report.success
    failed_count = report.failed
    export_file = _extract_export_file(report)
    successful_paths = _extract_successful_paths(report)

    # 删除已转写的视频
    if delete_after:
        _delete_transcribed_videos(video_paths, successful_paths)

    await call_progress(update_progress_fn, 1.0, f"批量流水线完成: 成功 {success_count}, 失败 {failed_count}", stage="done")

    subtasks = _build_subtasks(video_paths, report)

    return {
        "success_count": success_count,
        "failed_count": failed_count,
        "total": len(video_paths),
        "subtasks": subtasks,
        **({"export_file": export_file} if export_file else {}),
    }


async def run_download_only(video_urls: list[str], update_progress_fn, task_id: Optional[str] = None):
    """仅下载视频，不转写"""
    from media_tools.download.service import download_by_url as download_router, DownloadResult

    total = len(video_urls)
    if total == 0:
        return {"success_count": 0, "failed_count": 0}

    success_count = 0
    failed_count = 0

    for i, url in enumerate(video_urls):
        await call_progress(update_progress_fn, i / total, f"正在下载 ({i+1}/{total})", stage="download")
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(download_router, url, 1, True, True, task_id),
                timeout=300,
            )
            if isinstance(result, DownloadResult) and result.success:
                success_count += 1
            elif isinstance(result, dict) and result.get("success"):
                success_count += 1
            else:
                failed_count += 1
        except asyncio.TimeoutError:
            logger.error(f"下载超时 {url}")
            failed_count += 1
        except (OSError, RuntimeError, ValueError) as exc:
            logger.error(f"下载失败 {url}: {exc}")
            failed_count += 1

    # 下载循环结束，报告最终进度，确保前端和状态机能看到完成状态
    await call_progress(
        update_progress_fn,
        1.0,
        f"全部下载完成！共 {success_count} 个视频",
        stage="done",
    )
    return {"success_count": success_count, "failed_count": failed_count}

import asyncio
import inspect
import sqlite3
from pathlib import Path
from typing import Any, Optional, Union
from media_tools.logger import get_logger
from media_tools.db.core import local_asset_id
from media_tools.pipeline.task_helpers import call_progress, create_managed_task, filter_supported_media_paths

logger = get_logger('pipeline')


async def run_local_transcribe(file_paths: list[str], update_progress_fn=None, delete_after: bool = False):
    """转写本地视频文件（不经过下载步骤）"""
    from media_tools.pipeline.config import load_pipeline_config
    from media_tools.pipeline.orchestrator import create_orchestrator

    valid_paths = filter_supported_media_paths(file_paths)

    if not valid_paths:
        return {"success_count": 0, "failed_count": 0, "total": 0, "success_paths": [], "failed_paths": []}

    config = load_pipeline_config()
    orchestrator = create_orchestrator(config)
    if hasattr(orchestrator, '_resolve_qwen_execution_accounts'):
        orchestrator._resolve_qwen_execution_accounts()
    output_root = Path(config.output_dir).resolve()

    success_count = 0
    failed_count = 0
    total = len(valid_paths)

    effective_concurrency = getattr(orchestrator, '_effective_concurrency', config.concurrency)
    await call_progress(
        update_progress_fn,
        0.02,
        f"准备转写 {total} 个文件（并发 {effective_concurrency}）",
        stage="transcribe",
        pipeline_progress={"transcribe": {"done": 0, "total": total}},
    )
    from media_tools.db.core import get_db_connection
    from media_tools.pipeline.preview import extract_transcript_preview, extract_transcript_text

    subtasks: list[dict[str, Any]] = []
    success_paths: list[str] = []
    failed_paths: list[str] = []

    semaphore = asyncio.Semaphore(effective_concurrency)
    completed_count = 0

    async def _run_one(video_path: Path):
        title = video_path.stem[:60]
        async with semaphore:
            # 拿到并发槽时再报当前进度，避免一次创建 N 个任务时全部上报 (0/total)
            started = completed_count
            progress = 0.02 + 0.93 * (started / total) if total > 0 else 0.02
            create_managed_task(
                call_progress(
                    update_progress_fn,
                    progress,
                    f"正在转写 ({started}/{total}) · {title}",
                    stage="transcribe",
                    pipeline_progress={"transcribe": {"done": int(started), "total": int(total), "current_title": title}},
                )
            )
            return await orchestrator.transcribe_with_retry(video_path)

    tasks = [asyncio.create_task(_run_one(p)) for p in valid_paths]

    try:
        for finished in asyncio.as_completed(tasks):
            title = ""
            try:
                r = await finished
                video_path = r.video_path if getattr(r, "video_path", None) else Path("")
                title = video_path.stem[:60] if video_path else ""

                if getattr(r, "success", False):
                    success_count += 1
                    transcript_path = getattr(r, "transcript_path", None)
                    transcript_name = ""
                    preview = ""
                    full_text = ""
                    if transcript_path:
                        tp = Path(transcript_path)
                        try:
                            transcript_name = str(tp.resolve().relative_to(output_root))
                        except ValueError:
                            transcript_name = str(tp.name)
                        preview = extract_transcript_preview(str(tp))
                        full_text = extract_transcript_text(str(tp))
                    try:
                        with get_db_connection() as conn:
                            asset_id = local_asset_id(video_path)
                            conn.execute(
                                """
                                UPDATE media_assets
                                SET transcript_path = ?, transcript_status = 'completed', transcript_preview = ?, transcript_text = ?, update_time = CURRENT_TIMESTAMP
                                WHERE asset_id = ?
                                """,
                                (transcript_name, preview, full_text, asset_id),
                            )
                            # 在同一连接里同步 FTS，避免主事务回滚时 FTS 索引漂移
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
                    subtasks.append({"title": title or "未知", "status": "completed"})

                    if delete_after and video_path and video_path.exists():
                        transcript_path = getattr(r, "transcript_path", None)
                        if transcript_path and Path(transcript_path).exists():
                            try:
                                video_path.unlink()
                            except FileNotFoundError:
                                pass
                            except OSError as e:
                                logger.error(f"删除视频失败 (DB已更新): {video_path}, {e}")
                        else:
                            logger.warning(f"跳过删除源视频：转录文件不存在或已丢失 ({transcript_path})")
                else:
                    failed_count += 1
                    failed_paths.append(str(video_path))
                    err_type = getattr(getattr(r, "error_type", None), "value", "") or ""
                    err_msg = getattr(r, "error", None)
                    attempts = getattr(r, "attempts", None)
                    error_text = ""
                    if err_type and err_type != "unknown":
                        error_text = f"{err_type}: {err_msg}" if err_msg else err_type
                    else:
                        error_text = str(err_msg) if err_msg else "unknown"
                    if attempts and isinstance(attempts, int) and attempts > 1:
                        error_text = f"{error_text} (attempts={attempts})"
                    subtasks.append(
                        {
                            "title": title or "未知",
                            "status": "failed",
                            "error": error_text,
                            "error_type": err_type or None,
                            "attempts": attempts,
                            "video_path": str(video_path) if video_path else None,
                        }
                    )
            except Exception as exc:
                failed_count += 1
                subtasks.append({"title": title or "未知", "status": "failed", "error": f"exception: {type(exc).__name__}: {exc}"})

            completed = success_count + failed_count
            completed_count = completed
            progress = 0.02 + 0.93 * (completed / total) if total > 0 else 0.02
            msg = f"正在转写 ({completed}/{total}) · {title}" if title else f"正在转写 ({completed}/{total})"
            await call_progress(
                update_progress_fn,
                progress,
                msg,
                stage="transcribe",
                pipeline_progress={"transcribe": {"done": int(completed), "total": int(total), "current_title": title}},
            )
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    await call_progress(
        update_progress_fn,
        0.98,
        f"转写完成，正在汇总 {total} 个结果...",
        stage="transcribe",
        pipeline_progress={"transcribe": {"done": int(success_count + failed_count), "total": int(total)}},
    )

    return {
        "success_count": success_count,
        "failed_count": failed_count,
        "total": total,
        "subtasks": subtasks,
        "success_paths": success_paths,
        "failed_paths": failed_paths,
    }


async def run_pipeline_for_user(url: str, max_counts: int, update_progress_fn, delete_after: bool = True, task_id: Optional[str] = None):
    from media_tools.pipeline.download_router import download_by_url as download_router
    from media_tools.pipeline.download_router import resolve_platform
    from media_tools.pipeline.config import load_pipeline_config
    from media_tools.pipeline.orchestrator import create_orchestrator

    await call_progress(update_progress_fn, 0.1, "正在下载视频...", stage="download",
                        pipeline_progress={"download": {"done": 0, "total": max_counts or 0}})

    # 1. Download - 使用 router（会自动选择 yt-dlp 或回退到 F2）
    platform = resolve_platform(url)

    try:
        if platform == "bilibili":
            # B站使用 yt-dlp
            from media_tools.bilibili.core.downloader import download_up_by_url as bilibili_download
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
    if isinstance(dl_result, dict) and dl_result.get("cancelled"):
        await call_progress(update_progress_fn, 1.0, "任务已取消", stage="failed")
        return {"success_count": 0, "failed_count": 0, "cancelled": True}

    new_files = dl_result.get('new_files', []) if isinstance(dl_result, dict) else []

    if not new_files:
        await call_progress(update_progress_fn, 1.0, "没有下载到新视频", stage="done")
        return {"success_count": 0, "failed_count": 0}

    await call_progress(update_progress_fn, 0.4, f"下载完成，准备转写 {len(new_files)} 个视频...", stage="transcribe",
                        pipeline_progress={"download": {"done": len(new_files), "total": len(new_files)}})

    # 2. Transcribe (并发批量转写)
    config = load_pipeline_config()
    from media_tools.core.config import get_project_root
    state_file = get_project_root() / f".pipeline_state_{task_id or 'default'}.json"
    orchestrator = create_orchestrator(config, state_file=state_file)

    total = len(new_files)

    # 使用批量并发转写
    def _progress_callback(current: int, total: int, video_path: Path, status: str, account_id: Optional[str] = None):
        progress = 0.4 + 0.6 * (current / total) if total > 0 else 0.4
        transcribe_info: dict[str, Any] = {"done": current, "total": total}
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

    orchestrator.on_progress = _progress_callback

    # 转换为 Path 对象
    video_paths = [Path(f) for f in new_files]

    # 并发执行批量转写
    report = await orchestrator.transcribe_batch(video_paths, resume=False)

    success_count = report.success
    failed_count = report.failed
    export_file: Optional[str] = None
    for item in reversed(getattr(report, "results", []) or []):
        transcript_path = item.get("transcript_path") if isinstance(item, dict) else None
        if isinstance(transcript_path, str) and transcript_path.strip():
            export_file = transcript_path.strip()
            break
    successful_paths = {
        str(Path(item["video_path"]).resolve())
        for item in getattr(report, "results", [])
        if item.get("success") and item.get("video_path")
    }

    # 删除已转写的视频（如果配置了 delete_after）
    if delete_after:
        for path in video_paths:
            if str(path.resolve()) not in successful_paths:
                continue
            if path.exists():
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as e:
                    logger.error(f"删除视频失败 (DB已更新): {path}, {e}")

    await call_progress(update_progress_fn, 1.0, f"流水线完成: 成功 {success_count}, 失败 {failed_count}", stage="done")

    # 构建子任务列表（O(N) Map 查找替代 O(N*M) 双重循环）
    subtasks = []
    total = len(new_files)
    result_by_path: dict[str, dict] = {}
    for r in report.results:
        vp = r.get("video_path", "")
        if vp:
            result_by_path[str(Path(vp).resolve())] = r

    for video_path in video_paths:
        result_item = result_by_path.get(str(video_path.resolve()))
        status = "completed" if result_item and result_item.get("success") else "failed"
        error = result_item.get("error") if result_item else None
        transcript_path = result_item.get("transcript_path") if result_item and result_item.get("success") else None
        transcript_path = transcript_path if isinstance(transcript_path, str) and transcript_path.strip() else None
        subtasks.append({
            "title": video_path.stem,
            "status": status,
            "error": error,
            **({"transcript_path": transcript_path} if transcript_path else {}),
        })

    return {
        "success_count": success_count,
        "failed_count": failed_count,
        "total": total,
        "subtasks": subtasks,
        **({"export_file": export_file} if export_file else {}),
    }

async def run_batch_pipeline(video_urls: list[str], update_progress_fn, delete_after: bool = True, task_id: Optional[str] = None):
    from media_tools.pipeline.download_router import download_by_url as download_router
    from media_tools.pipeline.config import load_pipeline_config
    from media_tools.pipeline.orchestrator import create_orchestrator

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
        if isinstance(dl_result, dict) and dl_result.get('new_files'):
            new_files.extend(dl_result['new_files'])

    if not new_files:
        return {"success_count": 0, "failed_count": total}

    # Transcribe phase (并发批量转写)
    config = load_pipeline_config()
    from media_tools.core.config import get_project_root
    state_file = get_project_root() / f".pipeline_state_{task_id or 'batch_default'}.json"
    orchestrator = create_orchestrator(config, state_file=state_file)

    # 使用批量并发转写
    def _progress_callback(current: int, total: int, video_path: Path, status: str, account_id: Optional[str] = None):
        progress = 0.4 + 0.6 * (current / total) if total > 0 else 0.4
        transcribe_info: dict[str, Any] = {"done": current, "total": total}
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

    orchestrator.on_progress = _progress_callback

    video_paths = [Path(f) for f in new_files]
    report = await orchestrator.transcribe_batch(video_paths, resume=False)

    success_count = report.success
    failed_count = report.failed
    export_file: Optional[str] = None
    for item in reversed(getattr(report, "results", []) or []):
        transcript_path = item.get("transcript_path") if isinstance(item, dict) else None
        if isinstance(transcript_path, str) and transcript_path.strip():
            export_file = transcript_path.strip()
            break
    successful_paths = {
        str(Path(item["video_path"]).resolve())
        for item in getattr(report, "results", [])
        if item.get("success") and item.get("video_path")
    }

    # 删除已转写的视频
    if delete_after:
        for path in video_paths:
            if str(path.resolve()) not in successful_paths:
                continue
            if path.exists():
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as e:
                    logger.error(f"删除视频失败 (DB已更新): {path}, {e}")

    await call_progress(update_progress_fn, 1.0, f"批量流水线完成: 成功 {success_count}, 失败 {failed_count}", stage="done")

    subtasks: list[dict[str, object]] = []
    result_by_path: dict[str, dict] = {}
    for r in getattr(report, "results", []) or []:
        vp = r.get("video_path", "") if isinstance(r, dict) else ""
        if vp:
            result_by_path[str(Path(vp).resolve())] = r

    for video_path in video_paths:
        result_item = result_by_path.get(str(video_path.resolve()))
        status = "completed" if result_item and result_item.get("success") else "failed"
        error = result_item.get("error") if result_item else None
        transcript_path = result_item.get("transcript_path") if result_item and result_item.get("success") else None
        transcript_path = transcript_path if isinstance(transcript_path, str) and transcript_path.strip() else None
        subtasks.append({
            "title": video_path.stem,
            "status": status,
            "error": error,
            **({"transcript_path": transcript_path} if transcript_path else {}),
        })

    return {
        "success_count": success_count,
        "failed_count": failed_count,
        "total": len(video_paths),
        "subtasks": subtasks,
        **({"export_file": export_file} if export_file else {}),
    }


async def run_download_only(video_urls: list[str], update_progress_fn, task_id: Optional[str] = None):
    """仅下载视频，不转写"""
    from media_tools.pipeline.download_router import download_by_url as download_router, DownloadResult

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

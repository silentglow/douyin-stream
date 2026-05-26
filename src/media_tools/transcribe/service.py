from __future__ import annotations
"""Pipeline 流程编排器 V2 - 增强版

在原有基础上提供：
- 失败自动重试机制（可配置次数和指数退避延迟）
- 断点续传支持（状态持久化到 JSON 文件）
- 实时进度追踪（进度回调函数）
- 批量操作汇总报告（详细执行报告）
- 更好的错误处理（区分网络、配额、认证等错误类型）
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional, Callable, Any

from media_tools.transcribe.flow import run_real_flow
from media_tools.common.runtime import get_export_config
from media_tools.transcribe.config import load_config as load_transcribe_config
from media_tools.core.config import load_pipeline_config
from media_tools.core.config import AppConfig
from media_tools.transcribe.helpers import _lookup_video_title, _lookup_creator_folder
from media_tools.transcribe.errors import ErrorType, classify_error
from media_tools.transcribe.models import RetryConfig, PipelineResultV2, BatchReport

# 配置日志记录器
logger = logging.getLogger(__name__)


# 进度回调类型定义（最后一位可选参数为当前转写账户ID）
ProgressCallback = Callable[..., None]


class OrchestratorV2:
    """增强版 Pipeline 编排器

    支持：
    - 自动重试（指数退避）
    - 断点续传
    - 实时进度回调
    - 详细执行报告
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        auth_state_path: Optional[Path] = None,
        retry_config: Optional[RetryConfig] = None,
        on_progress: Optional[ProgressCallback] = None,
        creator_folder_override: Optional[str] = None,
    ):
        self.config = config or load_pipeline_config()
        self.auth_state_path = auth_state_path
        self.retry_config = retry_config or RetryConfig()
        self.on_progress = on_progress
        self._creator_folder_override = creator_folder_override
        from media_tools.accounts.service import get_account_pool_service
        # 进程内单例:所有 orchestrator 共享同一个 _upload_locks dict,
        # 避免同账号多文件并发上传(平台只允许 1)。详见 accounts/service.py 末尾说明。
        self._account_pool_service = get_account_pool_service(
            auth_state_path=self.auth_state_path,
            default_account_id=self.config.pipeline_account_id,
        )

        if self.auth_state_path is None:
            try:
                transcribe_config = load_transcribe_config()
                self.auth_state_path = transcribe_config.paths.auth_state_path
                self._account_pool_service._auth_state_path = self.auth_state_path
            except (OSError, TypeError, ValueError) as e:
                logger.warning(f"无法加载认证配置，将使用默认路径: {e}")

    def _fire_progress(
        self,
        current: int,
        total: int,
        video_path: Path,
        status: str,
        account_id: Optional[str] = None,
    ) -> None:
        """触发进度回调

        Args:
            current: 当前完成数
            total: 总数
            video_path: 当前视频路径
            status: 状态描述
            account_id: 当前使用的账号（避免并发覆盖实例变量）
        """
        if self.on_progress:
            try:
                self.on_progress(current, total, video_path, status, account_id)
            except (RuntimeError, TypeError, ValueError) as e:
                logger.warning(f"进度回调执行失败: {e}")

    async def _transcribe_single_video(
        self,
        video_path: Path,
        account_id: Optional[str] = None,
    ) -> PipelineResultV2:
        """对单个视频执行转写（内部方法，不含重试）

        Args:
            video_path: 视频文件路径

        Returns:
            PipelineResultV2: 执行结果
        """
        start_time = time.time()

        # 检查文件是否存在
        if not video_path.exists():
            return PipelineResultV2(
                success=False,
                video_path=video_path,
                error=f"视频文件不存在: {video_path}",
                error_type=ErrorType.FILE_NOT_FOUND,
            )

        # 准备导出配置
        export_config = get_export_config(self.config.export_format)

        try:
            # 从数据库查询视频标题
            video_title = _lookup_video_title(video_path)

            # 确定创作者子目录
            creator_folder = self._creator_folder_override or _lookup_creator_folder(video_path) or "未分类"
            output_dir_path = Path(self.config.output_dir).resolve()
            target_dir = (output_dir_path / creator_folder).resolve()
            if not target_dir.is_relative_to(output_dir_path):
                logger.warning(f"Creator folder traversal blocked: {creator_folder} -> {target_dir}")
                target_dir = output_dir_path / "未分类"
            output_dir = str(target_dir)
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            last_error: Optional[Exception] = None
            last_error_type: ErrorType = ErrorType.UNKNOWN

            # 初始化账号池（如果尚未初始化）
            pool = self._account_pool_service.account_pool
            if pool is None:
                self._account_pool_service.resolve_accounts()
                pool = self._account_pool_service.account_pool

            # 单个视频固定在同一账号内重试；只有认证失效才切换账号。
            accounts_tried = set()
            max_attempts = pool.available_count if pool else 1
            preferred_account_id = account_id
            current_account_id: Optional[str] = None

            # 第三阶段：解析 asset_id，三段式 fallback；找不到也允许继续跑（只是没续传能力）
            from media_tools.assets.service import MediaAssetService
            asset_id_for_run = MediaAssetService.find_asset_id_for_video_path(video_path)

            # 将 asset_id 嵌入输出标题，防止不同视频因标题截断后互相覆盖
            if asset_id_for_run and video_title:
                short_id = asset_id_for_run[-8:] if len(asset_id_for_run) >= 8 else asset_id_for_run
                video_title = f"{video_title} [{short_id}]"

            # DB 级断点续传：检查该 asset 是否已有成功的 run（跨账号去重）
            if asset_id_for_run:
                from media_tools.transcribe.run_service import TranscribeRunService
                from media_tools.assets.service import AssetUpdateService
                saved = TranscribeRunService.check_saved(asset_id_for_run)
                if saved:
                    saved_path, saved_account_id = saved
                    logger.info(f"命中缓存转写，跳过: {video_path}")
                    AssetUpdateService.mark_transcribe_completed(video_path, saved_path, Path(self.config.output_dir))
                    return PipelineResultV2(
                        success=True,
                        video_path=video_path,
                        transcript_path=saved_path,
                        duration=0.0,
                        account_id=saved_account_id,
                        video_deleted=False,
                    )

            for _ in range(max_attempts):
                pool = self._account_pool_service.account_pool
                if pool is None:
                    break

                account = await pool.acquire(preferred_account_id)
                if account is None:
                    break

                current_account_id = str(account.get("account_id", "") or "")
                if current_account_id in accounts_tried:
                    pool.release(current_account_id)
                    break
                accounts_tried.add(current_account_id)

                auth_state_path = account.get("auth_state_path")
                if auth_state_path is None:
                    pool.release(current_account_id)
                    break

                # 第三阶段：为这次尝试创建 run。失败时即便 mark_failed 也不影响主流程。
                run_id: Optional[str] = None
                resumable_run: Optional[dict[str, Any]] = None
                if asset_id_for_run:
                    run_id, resumable_run = TranscribeRunService.find_or_create_run(
                        asset_id=asset_id_for_run,
                        video_path=str(video_path),
                        account_id=current_account_id,
                    )

                try:
                    # 把 find_resumable 的字典转成 ResumeState 给 flow
                    from media_tools.transcribe.flow import ResumeState
                    resume_state = None
                    if resumable_run:
                        resume_state = ResumeState(
                            stage=str(resumable_run.get("stage") or "queued"),
                            record_id=resumable_run.get("record_id"),
                            gen_record_id=resumable_run.get("gen_record_id"),
                            batch_id=resumable_run.get("batch_id"),
                            export_url=resumable_run.get("export_url"),
                        )

                    account_upload_lock = await self._account_pool_service.get_upload_lock(current_account_id)
                    result = await run_real_flow(
                        file_path=video_path,
                        auth_state_path=auth_state_path,
                        download_dir=output_dir,
                        export_config=export_config,
                        should_delete=self.config.delete_after_export,
                        account_id=current_account_id,
                        title=video_title,
                        account_upload_lock=account_upload_lock,
                        run_id=run_id,
                        resume_state=resume_state,
                    )
                    self._account_pool_service.mark_used(current_account_id)

                    # 第三阶段：流程跑通后把 run 标为 saved；后续重试可以靠 find_saved_for_asset
                    # 跨账号识别"这个 asset 已经成功过"
                    if run_id:
                        TranscribeRunService.mark_saved(run_id, str(result.export_path))

                    duration = time.time() - start_time
                    return PipelineResultV2(
                        success=True,
                        video_path=video_path,
                        transcript_path=result.export_path,
                        duration=duration,
                        account_id=current_account_id,
                        video_deleted=False,
                    )
                except BaseException as e:  # classify_error 设计为处理任意异常类型
                    if not isinstance(e, Exception):
                        raise
                    last_error = e
                    last_error_type = classify_error(e)

                    # 第三阶段：把失败 stage 写入 transcribe_runs
                    if run_id:
                        TranscribeRunService.mark_failed(run_id, last_error_type.value, str(e))

                    # 判断是否需要切换账号重试
                    if current_account_id and self._should_switch_account(e, last_error_type):
                        status = "expired" if last_error_type == ErrorType.AUTH else "rate_limited"
                        self._account_pool_service.mark_status(current_account_id, status)
                        preferred_account_id = None
                        suggestion = getattr(getattr(e, "error_info", None), "suggestion", "")
                        msg = f"账号 {current_account_id} {last_error_type.value}，尝试下一个账号"
                        if suggestion:
                            msg += f": {suggestion}"
                        logger.warning(msg)
                        continue
                    logger.warning(f"转写失败 [{last_error_type.value}]，保留在账号 {current_account_id} 的重试链路: {e}")
                    break
                finally:
                    pool = self._account_pool_service.account_pool
                    if pool:
                        pool.release(current_account_id)

            duration = time.time() - start_time
            return PipelineResultV2(
                success=False,
                video_path=video_path,
                error=str(last_error) if last_error else "no available account",
                error_type=last_error_type,
                duration=duration,
                account_id=current_account_id,
            )

        except asyncio.CancelledError:
            # CancelledError 必须再抛，保证上层 cancel_task 能拿到 t.cancelled()=True
            # 并触发 worker finally 的 _mark_task_cancelled。
            raise

        except BaseException as e:  # classify_error 设计为处理任意异常类型
            if not isinstance(e, Exception):
                raise
            duration = time.time() - start_time
            error_type = classify_error(e)
            logger.error(f"转写失败 [{error_type.value}]: {video_path} - {e}")
            return PipelineResultV2(
                success=False,
                video_path=video_path,
                error=str(e),
                error_type=error_type,
                duration=duration,
            )

    def _should_switch_account(self, exc: Exception, error_type: ErrorType) -> bool:
        """判断失败后是否应该切换账号重试。"""
        # SERVICE_UNAVAILABLE 是平台级问题（如 recordStatus=40），切换账号无意义
        if error_type == ErrorType.SERVICE_UNAVAILABLE:
            return False
        if error_type not in (ErrorType.AUTH, ErrorType.QUOTA):
            return False
        from media_tools.transcribe.errors import TranscribeError
        if isinstance(exc, TranscribeError):
            return exc.error_info.retryable
        return error_type == ErrorType.AUTH

    async def transcribe_with_retry(
        self,
        video_path: Path,
    ) -> PipelineResultV2:
        """对单个视频执行转写（带重试机制）

        Args:
            video_path: 视频文件路径

        Returns:
            PipelineResultV2: 最终执行结果
        """
        max_attempts = self.retry_config.max_retries + 1  # 首次 + 重试次数
        execution_account_id: Optional[str] = None

        for attempt in range(1, max_attempts + 1):
            # 外层重试前重置账号排除状态，给所有账号新的尝试机会
            # （指数退避期间平台可能已经恢复）
            if attempt > 1:
                pool = self._account_pool_service.account_pool
                if pool:
                    pool.reset_excluded()

            self._fire_progress(
                0, 1, video_path,
                f"处理中 (尝试 {attempt}/{max_attempts})",
                account_id=execution_account_id,
            )

            result = await self._transcribe_single_video(video_path, execution_account_id)
            execution_account_id = result.account_id
            result.attempts = attempt

            if result.success:
                # 同步更新数据库
                from media_tools.assets.service import AssetUpdateService
                AssetUpdateService.mark_transcribe_completed(
                    video_path, result.transcript_path, Path(self.config.output_dir)
                )

                self._fire_progress(1, 1, video_path, "成功", account_id=result.account_id)
                logger.info(f"视频处理成功: {video_path} (尝试 {attempt} 次, 耗时 {result.duration:.1f}s)")
                return result

            # 失败：判断是否可重试
            if attempt < max_attempts and result.error_type in self.retry_config.retryable_errors:
                # 计算延迟（指数退避）
                delay = min(
                    self.retry_config.base_delay * (2 ** (attempt - 1)),
                    self.retry_config.max_delay,
                )
                logger.warning(
                    f"视频处理失败，将在 {delay:.1f}s 后重试 ({attempt}/{max_attempts}): "
                    f"[{result.error_type.value}] {result.error}"
                )
                self._fire_progress(
                    0, 1, video_path,
                    f"失败，{delay:.0f}s 后重试 ({attempt}/{max_attempts})",
                    account_id=result.account_id,
                )
                await asyncio.sleep(delay)
            else:
                # 不可重试或已达最大次数
                # 同步把失败信息写回 media_assets，让 UI/查询能基于 DB 真相源
                from media_tools.assets.service import AssetUpdateService
                from media_tools.assets.gc import CloudCleanupService
                AssetUpdateService.mark_transcribe_failed(
                    video_path,
                    result.error_type.value,
                    result.error or "",
                )
                # 清理云端残留的失败转写记录
                await CloudCleanupService.cleanup(
                    video_path, account_id=result.account_id
                )
                self._fire_progress(
                    0, 1, video_path,
                    f"失败 [{result.error_type.value}] (已达最大尝试次数)",
                    account_id=result.account_id,
                )
                if attempt < max_attempts:
                    logger.error(
                        f"视频处理失败且不可重试 [{result.error_type.value}]: "
                        f"{video_path} - {result.error}"
                    )
                else:
                    logger.error(
                        f"视频处理失败，已达最大尝试次数 ({max_attempts}): "
                        f"{video_path} - {result.error}"
                    )
                return result

        # 理论上不会到这里，但加上保险
        return PipelineResultV2(
            success=False,
            video_path=video_path,
            error=f"已达最大尝试次数 ({max_attempts})",
            error_type=ErrorType.UNKNOWN,
            attempts=max_attempts,
        )

    async def transcribe_batch(
        self,
        video_paths: list[Path],
        resume: bool = True,
    ) -> BatchReport:
        """批量转写多个视频

        Args:
            video_paths: 视频文件路径列表
            resume: 是否启用断点续传（默认True）

        Returns:
            BatchReport: 批量执行报告
        """
        start_time = time.time()
        report = BatchReport(
            total=len(video_paths),
            started_at=start_time,
        )

        pending_paths = list(video_paths)
        logger.info(f"批量处理: 共 {len(pending_paths)} 个视频")

        # 并发控制：跟随账号数（= 2×n）。account_pool 还没初始化的话先解析一次，
        # 否则 effective_concurrency 拿不到值，会退回 config.concurrency（旧值不准）。
        if self._account_pool_service.account_pool is None:
            self._account_pool_service.resolve_accounts()
        effective = self._account_pool_service.effective_concurrency or self.config.concurrency
        semaphore = asyncio.Semaphore(max(1, effective))
        completed_count = 0

        async def _process_with_semaphore(video_path: Path) -> PipelineResultV2:
            nonlocal completed_count
            async with semaphore:
                result = await self.transcribe_with_retry(video_path)
                completed_count += 1
                return result

        # 并发执行所有待处理视频
        tasks = [_process_with_semaphore(path) for path in pending_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 汇总结果 - 使用 zip 保持结果与原始路径的一一对应
        for video_path, result in zip(pending_paths, results):
            pipeline_result: PipelineResultV2

            # Python 3.11+ 中 asyncio.gather(return_exceptions=True) 不会收集 CancelledError，
            # 它会直接向上传播。KeyboardInterrupt / SystemExit 仍可能被收集，这里统一重新
            # 抛出所有 BaseException（非 Exception 子类），避免吞掉中断信号。
            if isinstance(result, BaseException) and not isinstance(result, Exception):
                raise result

            if isinstance(result, Exception):
                # 异常情况 - 正确归因到具体 video_path
                error_type = classify_error(result)
                pipeline_result = PipelineResultV2(
                    success=False,
                    video_path=video_path,  # 正确的错误归因
                    error=str(result),
                    error_type=error_type,
                )
                # transcribe_with_retry 抛出异常时（理论上不会，但兜底）也要写回 DB
                from media_tools.assets.service import AssetUpdateService
                AssetUpdateService.mark_transcribe_failed(
                    video_path,
                    error_type.value,
                    str(result),
                )
                logger.error(f"视频转写异常: video_path={video_path}, error={result}")
            else:
                # 结果校验：确保返回的 path 属于当前任务
                if result.video_path != video_path:
                    logger.warning(
                        f"结果路径不匹配: expected={video_path}, got={result.video_path}, "
                        "使用原始路径"
                    )
                    # 使用原始路径，保持一致性
                    result.video_path = video_path
                pipeline_result = result

            # 添加到报告
            result_dict = {
                "video_path": str(pipeline_result.video_path),
                "success": pipeline_result.success,
                "transcript_path": str(pipeline_result.transcript_path) if pipeline_result.transcript_path else None,
                "error": pipeline_result.error,
                "error_type": pipeline_result.error_type.value,
                "attempts": pipeline_result.attempts,
                "duration": round(pipeline_result.duration, 2),
                "account_id": pipeline_result.account_id,
            }
            report.results.append(result_dict)

            if pipeline_result.success:
                report.success += 1
            else:
                report.failed += 1
                # 统计错误类型
                err_type = pipeline_result.error_type.value
                report.error_summary[err_type] = report.error_summary.get(err_type, 0) + 1

        # 计算总耗时
        end_time = time.time()
        report.completed_at = end_time
        report.total_duration = end_time - start_time
        processed = report.success + report.failed
        report.avg_duration = report.total_duration / processed if processed > 0 else 0.0

        logger.info(
            f"批量处理完成: 成功 {report.success}, 失败 {report.failed}, "
            f"跳过 {report.skipped}, 总耗时 {report.total_duration:.1f}s"
        )

        return report


def create_orchestrator(
    config: Optional[AppConfig] = None,
    auth_state_path: Optional[Path] = None,
    retry_config: Optional[RetryConfig] = None,
    on_progress: Optional[ProgressCallback] = None,
    creator_folder_override: Optional[str] = None,
) -> OrchestratorV2:
    return OrchestratorV2(
        config=config,
        auth_state_path=auth_state_path,
        retry_config=retry_config,
        on_progress=on_progress,
        creator_folder_override=creator_folder_override,
    )


def run_pipeline_interactive() -> None:
    return

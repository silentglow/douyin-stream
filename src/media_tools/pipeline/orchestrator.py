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
import json
import logging
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional, Callable, Awaitable, Any, Union

from ..transcribe.flow import run_real_flow
from ..transcribe.runtime import get_export_config, ensure_dir, now_stamp
from ..transcribe.config import load_config as load_transcribe_config
from .config import PipelineConfig, load_pipeline_config
from .helpers import _clean_title_for_export, _lookup_video_title, _lookup_creator_folder
from .error_types import ErrorType, classify_error
from .models import AccountPool, RetryConfig, VideoState, PipelineResultV2, BatchReport
from .state_manager import PipelineStateManager, DEFAULT_STATE_FILE
from ..db.core import get_db_connection

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
        config: Optional[PipelineConfig] = None,
        auth_state_path: Optional[Path] = None,
        retry_config: Optional[RetryConfig] = None,
        state_file: Path | str = DEFAULT_STATE_FILE,
        on_progress: Optional[ProgressCallback] = None,
        creator_folder_override: Optional[str] = None,
        export_gate: Optional[asyncio.Semaphore] = None,
        upload_gate: Optional[asyncio.Semaphore] = None,
    ):
        self.config = config or load_pipeline_config()
        self.auth_state_path = auth_state_path
        self.retry_config = retry_config or RetryConfig()
        self.state_manager = PipelineStateManager(state_file)
        self.on_progress = on_progress
        self._creator_folder_override = creator_folder_override
        self._account_pool: AccountPool | None = None
        self._current_account_id: Optional[str] = None
        self._export_gate = export_gate or asyncio.Semaphore(
            getattr(self.config, 'export_concurrency', 2)
        )
        self._upload_gate = upload_gate

        if self.auth_state_path is None:
            try:
                transcribe_config = load_transcribe_config()
                self.auth_state_path = transcribe_config.paths.auth_state_path
            except (OSError, TypeError, ValueError) as e:
                logger.warning(f"无法加载认证配置，将使用默认路径: {e}")

    def _fire_progress(
        self,
        current: int,
        total: int,
        video_path: Path,
        status: str,
    ) -> None:
        """触发进度回调

        Args:
            current: 当前完成数
            total: 总数
            video_path: 当前视频路径
            status: 状态描述
        """
        if self.on_progress:
            try:
                self.on_progress(current, total, video_path, status, self._current_account_id)
            except (RuntimeError, TypeError, ValueError) as e:
                logger.warning(f"进度回调执行失败: {e}")

    def _resolve_qwen_execution_accounts(self) -> list[dict[str, Any]]:
        try:
            from media_tools.db.core import get_db_connection
            from media_tools.transcribe.db_account_pool import (
                build_qwen_auth_state_path_for_account,
                load_qwen_accounts_from_db,
            )
            from media_tools.transcribe.quota import get_daily_quota_record, number_value

            accounts = [a for a in load_qwen_accounts_from_db() if a.status == "active"]

            def _score(account_id: str) -> int:
                record = get_daily_quota_record(account_id)
                candidates = (
                    record.get("lastAfterRemaining"),
                    record.get("lastEquityAfterRemaining"),
                    record.get("lastBeforeRemaining"),
                    record.get("lastEquityBeforeRemaining"),
                )
                return max((number_value(v) for v in candidates), default=0)

            accounts.sort(key=lambda a: _score(a.account_id), reverse=True)

            resolved: list[dict[str, Any]] = []
            balances: list[int] = []
            for account in accounts:
                path = (
                    Path(account.auth_state_path)
                    if str(account.auth_state_path).strip()
                    else build_qwen_auth_state_path_for_account(account.account_id)
                )
                resolved.append({"account_id": account.account_id, "auth_state_path": path})
                balances.append(_score(account.account_id))

            if resolved:
                self._account_pool = AccountPool(resolved, balances)
                logger.info(f"账号池初始化: {[(a['account_id'], b) for a, b in zip(resolved, balances)]}")
                self._adjust_gates_to_account_pool()
                return resolved
        except (sqlite3.Error, OSError, TypeError, ValueError) as e:
            logger.warning(f"加载账号池失败: {e}")

        if self.auth_state_path is None:
            return []

        single_account = [{"account_id": self.config.account_id, "auth_state_path": Path(self.auth_state_path)}]
        self._account_pool = AccountPool(single_account, [0])
        self._adjust_gates_to_account_pool()
        return single_account

    def _adjust_gates_to_account_pool(self) -> None:
        if self._account_pool is None:
            return
        n_accounts = self._account_pool.account_count
        if self._upload_gate is None:
            self._upload_gate = asyncio.Semaphore(n_accounts)
            logger.info(f"上传信号量初始化: {n_accounts}（= 活跃账号数）")
        export_concurrency = min(2 * n_accounts, 8)
        current_export = self._export_gate._value if hasattr(self._export_gate, '_value') else 2
        if export_concurrency != current_export:
            self._export_gate = asyncio.Semaphore(export_concurrency)
            logger.info(f"导出信号量动态调整: {current_export} → {export_concurrency}（= min(2×{n_accounts}, 8)）")

    def _mark_qwen_account_status(self, account_id: str, status: str) -> None:
        if not account_id:
            return
        try:
            from media_tools.core.cookie_manager import get_cookie_manager
            get_cookie_manager().mark_account_status("qwen", account_id, status)
            if status in ("expired", "rate_limited") and self._account_pool:
                self._account_pool.exclude(account_id)
        except Exception as e:
            logger.warning(f"标记Qwen账号状态失败: {e}")
            return

    def _mark_qwen_account_used(self, account_id: str) -> None:
        if not account_id:
            return
        try:
            from media_tools.core.cookie_manager import get_cookie_manager
            get_cookie_manager().mark_account_used("qwen", account_id)
        except Exception as e:
            logger.warning(f"标记Qwen账号使用失败: {e}")
            return

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
            if not str(target_dir).startswith(str(output_dir_path) + os.sep) and str(target_dir) != str(output_dir_path):
                logger.warning(f"Creator folder traversal blocked: {creator_folder} -> {target_dir}")
                target_dir = output_dir_path / "未分类"
            output_dir = str(target_dir)
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            last_error: Optional[Exception] = None
            last_error_type: ErrorType = ErrorType.UNKNOWN

            # 初始化账号池（如果尚未初始化）
            if self._account_pool is None:
                resolved_accounts = self._resolve_qwen_execution_accounts()
                if self._account_pool is None and resolved_accounts:
                    self._account_pool = AccountPool(resolved_accounts, [0] * len(resolved_accounts))

            # 单个视频固定在同一账号内重试；只有认证失效才切换账号。
            accounts_tried = set()
            max_attempts = self._account_pool.available_count if self._account_pool else 1
            preferred_account_id = account_id

            # 第三阶段：解析 asset_id，三段式 fallback；找不到也允许继续跑（只是没续传能力）
            from media_tools.services.media_asset_service import MediaAssetService
            from media_tools.repositories.transcribe_run_repository import TranscribeRunRepository
            asset_id_for_run = MediaAssetService.find_asset_id_for_video_path(video_path)

            for _ in range(max_attempts):
                if self._account_pool is None:
                    break

                account = await self._account_pool.acquire(preferred_account_id)
                if account is None:
                    break

                current_account_id = str(account.get("account_id", "") or "")
                if current_account_id in accounts_tried:
                    self._account_pool.release(current_account_id)
                    break
                accounts_tried.add(current_account_id)
                self._current_account_id = current_account_id

                auth_state_path = account.get("auth_state_path")
                if auth_state_path is None:
                    self._account_pool.release(current_account_id)
                    break

                # 第三阶段：为这次尝试创建 run。失败时即便 mark_failed 也不影响主流程。
                run_id: Optional[str] = None
                resumable_run: Optional[Dict[str, Any]] = None
                if asset_id_for_run:
                    # 先看这个 (asset, account) 组合是否有可续传的 run（上传过但失败）
                    try:
                        resumable_run = TranscribeRunRepository.find_resumable(
                            asset_id_for_run, current_account_id
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(f"transcribe_runs.find_resumable 失败 (asset={asset_id_for_run}): {exc}")
                        resumable_run = None

                    if resumable_run:
                        run_id = resumable_run["run_id"]
                        logger.info(
                            f"发现可续传 run: asset={asset_id_for_run} account={current_account_id} "
                            f"stage={resumable_run.get('stage')} gen_record_id={resumable_run.get('gen_record_id')} "
                            f"export_url={'有' if resumable_run.get('export_url') else '无'} "
                            f"(Step 12: 仅记录，未复用)"
                        )
                    else:
                        try:
                            run_id = TranscribeRunRepository.create(
                                asset_id=asset_id_for_run,
                                video_path=str(video_path),
                                account_id=current_account_id,
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(f"transcribe_runs.create 失败 (asset={asset_id_for_run}): {exc}")
                            run_id = None

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

                    result = await run_real_flow(
                        file_path=video_path,
                        auth_state_path=auth_state_path,
                        download_dir=output_dir,
                        export_config=export_config,
                        should_delete=self.config.delete_after_export,
                        account_id=current_account_id,
                        title=video_title,
                        export_gate=self._export_gate,
                        upload_gate=self._upload_gate,
                        run_id=run_id,
                        resume_state=resume_state,
                    )
                    self._mark_qwen_account_used(current_account_id)

                    # 第三阶段：流程跑通后把 run 标为 saved；后续重试可以靠 find_saved_for_asset
                    # 跨账号识别"这个 asset 已经成功过"
                    if run_id:
                        try:
                            TranscribeRunRepository.mark_saved(run_id, str(result.export_path))
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(f"transcribe_runs.mark_saved 失败 (run_id={run_id}): {exc}")

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

                    # 第三阶段：把失败 stage 写入 transcribe_runs。当前 stage 由 flow 最近
                    # 一次打卡决定，所以这里直接读回，比硬猜更准。
                    if run_id:
                        try:
                            current_run = TranscribeRunRepository.get(run_id) or {}
                            current_stage = str(current_run.get("stage") or "queued")
                            TranscribeRunRepository.mark_failed(
                                run_id,
                                error_stage=current_stage,
                                error_type=last_error_type.value,
                                last_error=str(e),
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(f"transcribe_runs.mark_failed 失败 (run_id={run_id}): {exc}")

                    from media_tools.transcribe.error_classifier import TranscribeError
                    if isinstance(e, TranscribeError) and e.error_info.retryable:
                        if last_error_type in (ErrorType.AUTH, ErrorType.QUOTA, ErrorType.SERVICE_UNAVAILABLE) and current_account_id:
                            if last_error_type == ErrorType.AUTH:
                                self._mark_qwen_account_status(current_account_id, "expired")
                            elif last_error_type == ErrorType.SERVICE_UNAVAILABLE:
                                self._mark_qwen_account_status(current_account_id, "rate_limited")
                            else:
                                self._mark_qwen_account_status(current_account_id, "rate_limited")
                            preferred_account_id = None
                            logger.warning(f"账号 {current_account_id} {last_error_type.value}，尝试下一个账号: {e.error_info.suggestion}")
                            continue
                    elif last_error_type == ErrorType.AUTH and current_account_id:
                        self._mark_qwen_account_status(current_account_id, "expired")
                        preferred_account_id = None
                        logger.warning(f"账号 {current_account_id} 认证过期，尝试下一个账号")
                        continue
                    elif last_error_type == ErrorType.SERVICE_UNAVAILABLE and current_account_id:
                        self._mark_qwen_account_status(current_account_id, "rate_limited")
                        preferred_account_id = None
                        logger.warning(f"账号 {current_account_id} 服务不可用，尝试下一个账号")
                        continue
                    logger.warning(f"转写失败 [{last_error_type.value}]，保留在账号 {current_account_id} 的重试链路: {e}")
                    break
                finally:
                    self._account_pool.release(current_account_id)

            duration = time.time() - start_time
            return PipelineResultV2(
                success=False,
                video_path=video_path,
                error=str(last_error) if last_error else "no available account",
                error_type=last_error_type,
                duration=duration,
                account_id=self._current_account_id,
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

    def _update_media_asset_transcript(
        self,
        video_path: Path,
        transcript_path: Optional[Path],
    ) -> None:
        """同步更新 media_assets 表的转写状态（成功路径）。"""
        try:
            from media_tools.pipeline.preview import extract_transcript_preview, extract_transcript_text
            from media_tools.services.media_asset_service import MediaAssetService

            preview = extract_transcript_preview(transcript_path) if transcript_path else ""
            full_text = extract_transcript_text(transcript_path) if transcript_path else ""
            MediaAssetService.mark_transcribe_completed(
                video_path=video_path,
                transcript_path=transcript_path,
                output_dir=Path(self.config.output_dir),
                preview=preview,
                full_text=full_text,
            )
        except (OSError, ValueError) as e:
            logger.warning(f"更新 media_assets 转写状态失败: {e}")

    def _mark_media_asset_transcript_failed(
        self,
        video_path: Path,
        error_type: str,
        error_message: str,
    ) -> None:
        """同步把转写失败信息写回 media_assets 表（失败路径）。"""
        try:
            from media_tools.services.media_asset_service import MediaAssetService
            MediaAssetService.mark_transcribe_failed(
                video_path=video_path,
                error_type=error_type,
                error_message=error_message,
            )
        except (OSError, ValueError) as e:
            logger.warning(f"写回 media_assets 失败状态失败: {e}")

    async def _cleanup_failed_cloud_records(self, video_path: Path) -> None:
        """转写最终失败后，清理云端残留的转写记录。

        当所有重试和账号切换都失败后，已上传到千问平台的文件仍会占用云端存储。
        此方法查找该视频所有失败 run 的 record_id，并调用删除 API 清理。
        """
        from media_tools.repositories.transcribe_run_repository import TranscribeRunRepository
        from media_tools.services.media_asset_service import MediaAssetService

        asset_id = MediaAssetService.find_asset_id_for_video_path(video_path)

        record_ids: list[str] = []
        if asset_id:
            record_ids = TranscribeRunRepository.find_failed_record_ids(asset_id)
        if not record_ids:
            record_ids = TranscribeRunRepository.find_failed_record_ids_for_video(str(video_path))

        if not record_ids:
            return

        try:
            from media_tools.transcribe.auth_state import resolve_qwen_cookie_string
            from media_tools.transcribe.flow import delete_record
            from media_tools.transcribe.http import RequestsApiContext

            cookie_string = resolve_qwen_cookie_string(
                auth_state_path="",
                account_id=self._current_account_id or "",
            )
            if not cookie_string.strip():
                logger.warning("云端清理跳过：无法获取有效 cookie")
                return

            api = RequestsApiContext(cookie_string=cookie_string)
            try:
                deleted = await delete_record(api, record_ids)
                if deleted:
                    logger.info(f"云端清理成功：已删除 {len(record_ids)} 条失败记录 ({video_path})")
                else:
                    logger.warning(f"云端清理返回失败：{len(record_ids)} 条记录 ({video_path})")
            finally:
                await api.dispose()
        except Exception as e:
            logger.warning(f"云端清理异常（不影响主流程）: {video_path} - {e}")

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
        state = self.state_manager.get_state(video_path)

        # 如果已成功且无重试需求，检查缓存的转录文件是否实际存在
        if state.status == "success" and state.transcript_path:
            cached_path = Path(state.transcript_path)
            if cached_path.exists():
                logger.info(f"跳过已成功的视频: {video_path}")
                self._update_media_asset_transcript(video_path, cached_path)
                return PipelineResultV2(
                    success=True,
                    video_path=video_path,
                    transcript_path=cached_path,
                    attempts=state.attempt,
                    duration=state.duration,
                )
            logger.warning(f"缓存的转录文件已丢失，重新转录: {video_path}")
            self.state_manager.update_state(
                video_path,
                status="pending",
                transcript_path="",
            )
            state = self.state_manager.get_state(video_path)

        max_attempts = self.retry_config.max_retries + 1  # 首次 + 重试次数
        state.max_attempts = max_attempts
        total_attempts = 0
        execution_account_id: Optional[str] = None

        for attempt in range(1, max_attempts + 1):
            total_attempts = attempt
            state.attempt = attempt

            # 标记为运行中
            self.state_manager.update_state(
                video_path,
                status="running",
                attempt=attempt,
                max_attempts=max_attempts,
            )
            self._fire_progress(
                0, 1, video_path,
                f"处理中 (尝试 {attempt}/{max_attempts})"
            )

            result = await self._transcribe_single_video(video_path, execution_account_id)
            execution_account_id = result.account_id
            result.attempts = attempt

            if result.success:
                # 成功：更新状态
                self.state_manager.update_state(
                    video_path,
                    status="success",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    transcript_path=str(result.transcript_path) if result.transcript_path else "",
                )

                # 同步更新数据库
                self._update_media_asset_transcript(video_path, result.transcript_path)

                self._fire_progress(1, 1, video_path, "成功")
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
                self.state_manager.update_state(
                    video_path,
                    status="failed",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error_type=result.error_type.value,
                    error_message=result.error or "",
                )
                self._fire_progress(
                    0, 1, video_path,
                    f"失败，{delay:.0f}s 后重试 ({attempt}/{max_attempts})"
                )
                await asyncio.sleep(delay)
            else:
                # 不可重试或已达最大次数
                self.state_manager.update_state(
                    video_path,
                    status="failed",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error_type=result.error_type.value,
                    error_message=result.error or "",
                )
                # 同步把失败信息写回 media_assets，让 UI/查询能基于 DB 真相源
                self._mark_media_asset_transcript_failed(
                    video_path,
                    result.error_type.value,
                    result.error or "",
                )
                # 清理云端残留的失败转写记录
                await self._cleanup_failed_cloud_records(video_path)
                self._fire_progress(
                    0, 1, video_path,
                    f"失败 [{result.error_type.value}] (已达最大尝试次数)"
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
            attempts=total_attempts,
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

        # 断点续传：过滤已成功/运行中的
        if resume:
            pending_paths = self.state_manager.get_pending_videos(video_paths)
            skipped_count = len(video_paths) - len(pending_paths)
            report.skipped = skipped_count
            logger.info(
                f"批量处理: 总计 {len(video_paths)} 个视频，"
                f"跳过 {skipped_count} 个（已成功/运行中），"
                f"待处理 {len(pending_paths)} 个"
            )
        else:
            pending_paths = list(video_paths)
            logger.info(f"批量处理: 共 {len(pending_paths)} 个视频（不启用断点续传）")

        # 如果无需处理任何视频
        if not pending_paths:
            report.completed_at = time.time()
            report.total_duration = report.completed_at - report.started_at
            logger.info("所有视频已处理完成，无需执行")
            return report

        # 并发控制
        semaphore = asyncio.Semaphore(self.config.concurrency)
        completed_count = 0
        total_pending = len(pending_paths)

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
                self._mark_media_asset_transcript_failed(
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
    config: Optional[PipelineConfig] = None,
    auth_state_path: Optional[Path] = None,
    retry_config: Optional[RetryConfig] = None,
    state_file: Path | str = DEFAULT_STATE_FILE,
    on_progress: Optional[ProgressCallback] = None,
    creator_folder_override: Optional[str] = None,
    upload_gate: Optional[asyncio.Semaphore] = None,
) -> OrchestratorV2:
    return OrchestratorV2(
        config=config,
        auth_state_path=auth_state_path,
        retry_config=retry_config,
        state_file=state_file,
        on_progress=on_progress,
        creator_folder_override=creator_folder_override,
        upload_gate=upload_gate,
    )


async def run_enhanced_pipeline(
    video_paths: list[Path],
    config: Optional[PipelineConfig] = None,
    auth_state_path: Optional[Path] = None,
    retry_config: Optional[RetryConfig] = None,
    state_file: Path | str = DEFAULT_STATE_FILE,
    on_progress: Optional[ProgressCallback] = None,
    resume: bool = True,
    report_path: Optional[Path] = None,
) -> BatchReport:
    """便捷函数：一键运行增强版 Pipeline

    Args:
        video_paths: 视频文件路径列表
        config: Pipeline 配置
        auth_state_path: 认证状态文件路径
        retry_config: 重试配置
        state_file: 状态持久化文件路径
        on_progress: 进度回调函数
        resume: 是否启用断点续传
        report_path: 报告保存路径（None则不保存）

    Returns:
        BatchReport: 执行报告

    Example:
        >>> report = await run_enhanced_pipeline(
        ...     video_paths=[Path("video1.mp4"), Path("video2.mp4")],
        ...     on_progress=lambda c, t, p, s: logger.info(f"{c}/{t}: {s}"),
        ...     report_path=Path("report.json"),
        ... )
        >>> logger.info(f"成功: {report.success}/{report.total}")
    """
    orchestrator = create_orchestrator(
        config=config,
        auth_state_path=auth_state_path,
        retry_config=retry_config,
        state_file=state_file,
        on_progress=on_progress,
    )
    report = await orchestrator.transcribe_batch(video_paths, resume=resume)

    # 可选：保存报告
    if report_path:
        report.save_to_file(report_path)

    return report


def print_enhanced_summary(report: BatchReport) -> None:
    """打印增强版执行摘要

    Args:
        report: 批量执行报告
    """
    logger.info("\n" + "=" * 60)
    logger.info("📊 Pipeline 增强版执行摘要")
    logger.info("=" * 60)
    logger.info(f"总计: {report.total}")
    logger.info(f"✅ 成功: {report.success}")
    logger.info(f"❌ 失败: {report.failed}")
    logger.info(f"⏭️  跳过: {report.skipped}")
    logger.info(f"⏱️  总耗时: {report.total_duration:.1f}s")
    if report.success + report.failed > 0:
        logger.info(f"📈 平均耗时: {report.avg_duration:.1f}s/视频")
    logger.info("=" * 60)

    if report.error_summary:
        logger.info("\n错误类型统计:")
        for err_type, count in report.error_summary.items():
            logger.info(f"  - [{err_type}]: {count} 次")

    if report.failed > 0:
        logger.info("\n失败详情:")
        for r in report.results:
            if not r["success"]:
                logger.info(f"  - {Path(r['video_path']).name}: [{r['error_type']}] {r['error']}")
                if r.get("attempts", 1) > 1:
                    logger.info(f"    (尝试了 {r['attempts']} 次)")

    logger.info("=" * 60)


def run_pipeline_batch(
    video_paths: list[Path],
    config: Optional[PipelineConfig] = None,
    auth_state_path: Optional[Path] = None,
) -> list:
    """同步包装器：批量转写（兼容原 orchestrator.py V1 接口）

    downloader.py 通过此函数在同步上下文中调用异步流水线。
    若当前已有运行中的事件循环，则在新线程中运行以避免 RuntimeError。
    """
    coro = run_enhanced_pipeline(video_paths, config=config, auth_state_path=auth_state_path)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            report = executor.submit(asyncio.run, coro).result()
    else:
        report = asyncio.run(coro)

    class _Compat:
        """Lightweight shim: r.success / r.video_path / r.transcript_path / r.error"""
        def __init__(self, d: dict):
            self.success = d.get("success", False)
            self.video_path = Path(d["video_path"])
            self.transcript_path = Path(d["transcript_path"]) if d.get("transcript_path") else None
            self.error = d.get("error")

    return [_Compat(r) for r in report.results]


def run_pipeline_interactive() -> None:
    return

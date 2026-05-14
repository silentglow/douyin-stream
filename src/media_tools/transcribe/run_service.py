from __future__ import annotations
"""转写 run 服务 - 封装 transcribe_runs 表的高级操作。"""

from pathlib import Path
from typing import Any, Optional, Dict

from media_tools.logger import get_logger
from media_tools.repositories.transcribe_run_repository import TranscribeRunRepository

logger = get_logger(__name__)


class TranscribeRunService:
    """transcribe_runs 的高级操作服务。

    把 orchestrator 中分散的"查询-判断-创建-标记"复合逻辑封装为原子操作，
    减少调用方的认知负担和重复代码。
    """

    @staticmethod
    def check_saved(asset_id: str) -> Optional[tuple[Path, str]]:
        """检查 asset 是否已有成功且非空的缓存转写文件。

        Returns:
            (文件路径, account_id) 或 None
        """
        if not asset_id:
            return None
        try:
            saved_run = TranscribeRunRepository.find_saved_for_asset(asset_id)
            if not saved_run:
                return None
            saved_path = Path(saved_run.get("transcript_path", ""))
            account_id = str(saved_run.get("account_id", ""))
            if saved_path.exists() and saved_path.stat().st_size > 0:
                logger.info(
                    f"命中缓存转写 (run_id={saved_run.get('run_id')}, "
                    f"size={saved_path.stat().st_size})"
                )
                return saved_path, account_id
            if saved_path.exists() and saved_path.stat().st_size == 0:
                logger.warning("缓存的转录文件为空，重新转录")
            else:
                logger.warning("缓存的转录文件已丢失，重新转录")
        except (OSError, ValueError) as exc:
            logger.warning(f"find_saved_for_asset 失败 (asset={asset_id}): {exc}")
        return None

    @staticmethod
    def find_or_create_run(
        asset_id: str,
        video_path: str,
        account_id: str,
    ) -> tuple[Optional[str], Optional[dict[str, Any]]]:
        """查找可续传的 run 或创建新 run。

        Returns:
            (run_id, resumable_run_dict)。run_id 为 None 表示创建失败。
        """
        if not asset_id:
            return None, None

        # 先查可续传 run
        resumable_run: Optional[dict[str, Any]] = None
        try:
            resumable_run = TranscribeRunRepository.find_resumable(asset_id, account_id)
        except (OSError, ValueError) as exc:
            logger.warning(f"transcribe_runs.find_resumable 失败 (asset={asset_id}): {exc}")

        if resumable_run:
            run_id = resumable_run["run_id"]
            logger.info(
                f"发现可续传 run: asset={asset_id} account={account_id} "
                f"stage={resumable_run.get('stage')} gen_record_id={resumable_run.get('gen_record_id')} "
                f"export_url={'有' if resumable_run.get('export_url') else '无'}"
            )
            return run_id, resumable_run

        # 无可续传，创建新 run
        try:
            run_id = TranscribeRunRepository.create(
                asset_id=asset_id,
                video_path=video_path,
                account_id=account_id,
            )
            return run_id, None
        except (OSError, ValueError) as exc:
            logger.warning(f"transcribe_runs.create 失败 (asset={asset_id}): {exc}")
            return None, None

    @staticmethod
    def mark_saved(run_id: str, transcript_path: str) -> None:
        """标记 run 为 saved。"""
        if not run_id:
            return
        try:
            TranscribeRunRepository.mark_saved(run_id, transcript_path)
        except (OSError, ValueError) as exc:
            logger.warning(f"transcribe_runs.mark_saved 失败 (run_id={run_id}): {exc}")

    @staticmethod
    def mark_failed(run_id: str, error_type: str, error: str) -> None:
        """标记 run 为 failed，自动读取当前 stage。"""
        if not run_id:
            return
        try:
            current_run = TranscribeRunRepository.get(run_id) or {}
            current_stage = str(current_run.get("stage") or "queued")
            TranscribeRunRepository.mark_failed(
                run_id,
                error_stage=current_stage,
                error_type=error_type,
                last_error=error,
            )
        except (OSError, ValueError) as exc:
            logger.warning(f"transcribe_runs.mark_failed 失败 (run_id={run_id}): {exc}")

    @staticmethod
    def get_failed_record_ids(
        asset_id: Optional[str],
        video_path: str,
        account_id: str = "",
    ) -> list[str]:
        """获取失败 run 的 record_id 列表，用于云端清理。"""
        if asset_id:
            try:
                record_ids = TranscribeRunRepository.find_failed_record_ids(asset_id, account_id=account_id)
                if record_ids:
                    return record_ids
            except (OSError, ValueError) as exc:
                logger.warning(f"find_failed_record_ids 失败: {exc}")

        try:
            return TranscribeRunRepository.find_failed_record_ids_for_video(video_path, account_id=account_id)
        except (OSError, ValueError) as exc:
            logger.warning(f"find_failed_record_ids_for_video 失败: {exc}")
            return []

from __future__ import annotations
"""素材状态更新服务 - 封装 media_assets 表的转写状态更新。"""

from pathlib import Path
from typing import Optional

from media_tools.logger import get_logger

logger = get_logger(__name__)


class AssetUpdateService:
    """media_assets 转写状态的统一更新入口。

    把 orchestrator 中的"成功路径更新"和"失败路径更新"封装为原子操作，
    避免 orchestrator 直接依赖 preview 提取等细节。
    """

    @staticmethod
    def mark_transcribe_completed(
        video_path: Path,
        transcript_path: Optional[Path],
        output_dir: Path,
    ) -> None:
        """转写成功后更新 media_assets 表。"""
        try:
            from media_tools.pipeline.preview import extract_transcript_preview, extract_transcript_text
            from media_tools.services.media_asset_service import MediaAssetService

            preview = extract_transcript_preview(transcript_path) if transcript_path else ""
            full_text = extract_transcript_text(transcript_path) if transcript_path else ""
            MediaAssetService.mark_transcribe_completed(
                video_path=video_path,
                transcript_path=transcript_path,
                output_dir=output_dir,
                preview=preview,
                full_text=full_text,
            )
        except (OSError, ValueError) as e:
            logger.warning(f"更新 media_assets 转写状态失败: {e}")

    @staticmethod
    def mark_transcribe_failed(
        video_path: Path,
        error_type: str,
        error_message: str,
    ) -> None:
        """转写失败后把失败信息写回 media_assets 表。"""
        try:
            from media_tools.services.media_asset_service import MediaAssetService
            MediaAssetService.mark_transcribe_failed(
                video_path=video_path,
                error_type=error_type,
                error_message=error_message,
            )
        except (OSError, ValueError) as e:
            logger.warning(f"写回 media_assets 失败状态失败: {e}")

from __future__ import annotations
"""云端清理服务 - 转写失败后清理千问平台残留记录。"""

from pathlib import Path
from typing import Optional

from media_tools.logger import get_logger
from media_tools.services.media_asset_service import MediaAssetService
from media_tools.services.transcribe_run_service import TranscribeRunService

logger = get_logger(__name__)


class CloudCleanupService:
    """清理云端残留的失败转写记录。

    当所有重试和账号切换都失败后，已上传到千问平台的文件仍会占用云端存储。
    此服务查找该视频所有失败 run 的 record_id，并调用删除 API 清理。

    注意：record_ids 可能来自多个账号（视频曾在不同账号上重试），
    但当前实现只尝试用传入的 account_id 对应的 cookie 删除。
    跨账号孤儿记录由后续健康检查脚本兜底。
    """

    @staticmethod
    async def cleanup(video_path: Path, *, account_id: Optional[str] = None) -> None:
        """清理指定视频的云端失败记录。"""
        asset_id = MediaAssetService.find_asset_id_for_video_path(video_path)

        record_ids = TranscribeRunService.get_failed_record_ids(
            asset_id=asset_id,
            video_path=str(video_path),
            account_id=account_id or "",
        )
        if not record_ids:
            return

        try:
            from media_tools.transcribe.auth_state import resolve_qwen_cookie_string
            from media_tools.transcribe.flow import delete_record
            from media_tools.transcribe.http import RequestsApiContext

            cookie_string = resolve_qwen_cookie_string(
                auth_state_path="",
                account_id=account_id or "",
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

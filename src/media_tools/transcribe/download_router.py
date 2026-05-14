from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Union


@dataclass
class DownloadResult:
    """下载结果标准化容器，统一三个下载器的返回格式"""
    success: bool = True
    new_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    error: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_raw(raw: dict[str, Any]) -> DownloadResult:
        """从原始返回值构造，兼容各种下载器的返回格式"""
        if not isinstance(raw, dict):
            return DownloadResult(success=False, error=f"无效的下载结果: {type(raw).__name__}")
        return DownloadResult(
            success=bool(raw.get("success", True)),
            new_files=raw.get("new_files") or raw.get("downloaded_files") or [],
            skipped_files=raw.get("skipped_files") or raw.get("skipped") or [],
            error=str(raw.get("error", "")),
            raw=raw,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "new_files": self.new_files,
            "skipped_files": self.skipped_files,
            "error": self.error,
            "success_count": len(self.new_files),
            "failed_count": 0 if self.success else 1,
            **self.raw,
        }


def resolve_platform(url: str) -> str:
    value = (url or "").lower()
    if "bilibili.com" in value or "b23.tv" in value:
        return "bilibili"
    return "douyin"


def is_aweme_url(url: str) -> bool:
    """判断是否为抖音单个视频链接（/video/xxx），而非用户主页链接（/user/xxx）"""
    return bool(re.search(r'douyin\.com/video/\d+', url))


def download_by_url(url: str, max_counts: Optional[int], disable_auto_transcribe: bool, skip_existing: bool, task_id: Optional[str] = None) -> DownloadResult:
    platform = resolve_platform(url)
    raw: dict[str, Any]
    if platform == "bilibili":
        from media_tools.bilibili.core.downloader import download_up_by_url
        raw = download_up_by_url(url, max_counts=max_counts, skip_existing=skip_existing, task_id=task_id, disable_auto_transcribe=disable_auto_transcribe)
    else:
        if is_aweme_url(url):
            from media_tools.douyin.core.downloader import download_aweme_by_url
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    raw = pool.submit(asyncio.run, download_aweme_by_url(url)).result()
            else:
                raw = asyncio.run(download_aweme_by_url(url))
        else:
            from media_tools.douyin.core.downloader import download_by_url as douyin_download
            raw = douyin_download(url, max_counts, disable_auto_transcribe, skip_existing, task_id=task_id)
    return DownloadResult.from_raw(raw)
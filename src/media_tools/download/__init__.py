from __future__ import annotations

"""下载域：统一视频下载调度与 Worker。"""

from .service import DownloadResult, download_by_url, is_aweme_url, resolve_platform
from .worker import DownloadWorker

__all__ = [
    "download_by_url",
    "DownloadResult",
    "resolve_platform",
    "is_aweme_url",
    "DownloadWorker",
]

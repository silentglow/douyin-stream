#!/usr/bin/env python3
"""
CLI 核心模块

导出接口：
- VideoInfo, VideoFetcher, VideoStorage, VideoMetadataStore, Downloader
"""

from .interface import (
    Downloader,
    VideoFetcher,
    VideoInfo,
    VideoMetadataStore,
    VideoStorage,
)

__all__ = [
    # 接口定义
    "VideoInfo",
    "VideoFetcher",
    "VideoStorage",
    "VideoMetadataStore",
    "Downloader",
]

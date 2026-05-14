#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI 核心模块

导出接口：
- VideoInfo, VideoFetcher, VideoStorage, VideoMetadataStore, Downloader
"""

from .interface import (
    VideoInfo,
    VideoFetcher,
    VideoStorage,
    VideoMetadataStore,
    Downloader,
)

__all__ = [
    # 接口定义
    "VideoInfo",
    "VideoFetcher",
    "VideoStorage",
    "VideoMetadataStore",
    "Downloader",
]

from __future__ import annotations
"""下载器模块接口定义 - 定义视频下载相关的抽象接口"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional


class VideoInfo:
    """视频信息数据类"""
    
    def __init__(
        self,
        aweme_id: str,
        title: str,
        url: str,
        author: str,
        author_id: str,
        duration: int = 0,
        cover_url: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ):
        self.aweme_id = aweme_id
        self.title = title
        self.url = url
        self.author = author
        self.author_id = author_id
        self.duration = duration
        self.cover_url = cover_url
        self.metadata = metadata or {}


class VideoFetcher(ABC):
    """视频数据获取器接口"""
    
    @abstractmethod
    async def fetch_video_list(
        self,
        uid: str,
        max_counts: int = 50,
        interval: Optional[str] = None,
    ) -> list[VideoInfo]:
        """获取用户视频列表"""
        pass
    
    @abstractmethod
    async def fetch_video_by_url(self, url: str) -> VideoInfo:
        """根据 URL 获取视频信息"""
        pass
    
    @abstractmethod
    async def download_video(self, video_info: VideoInfo, save_path: Path) -> bool:
        """下载视频文件到指定路径"""
        pass


class VideoStorage(ABC):
    """视频存储管理器接口"""
    
    @abstractmethod
    def get_download_path(self, author_id: str, author_name: str) -> Path:
        """获取作者视频下载目录"""
        pass
    
    @abstractmethod
    def save_video(self, video_info: VideoInfo, content: bytes) -> Path:
        """保存视频文件"""
        pass
    
    @abstractmethod
    def exists(self, aweme_id: str, author_id: str) -> bool:
        """检查视频是否已存在"""
        pass
    
    @abstractmethod
    def list_existing(self, author_id: str) -> list[str]:
        """列出已存在的视频 ID"""
        pass
    
    @abstractmethod
    def validate_file(self, file_path: Path) -> bool:
        """验证视频文件完整性"""
        pass


class VideoMetadataStore(ABC):
    """视频元数据存储接口"""
    
    @abstractmethod
    def save_metadata(self, video_info: VideoInfo, file_path: Path) -> None:
        """保存视频元数据"""
        pass
    
    @abstractmethod
    def get_metadata(self, aweme_id: str) -> Optional[dict[str, Any]]:
        """获取视频元数据"""
        pass
    
    @abstractmethod
    def update_download_time(self, author_id: str) -> None:
        """更新下载时间"""
        pass


class Downloader(ABC):
    """下载器接口 - 协调视频下载流程"""
    
    @abstractmethod
    async def download_by_url(
        self,
        url: str,
        skip_existing: bool = True,
        task_id: Optional[str] = None,
    ) -> Tuple[int, int]:
        """根据 URL 下载视频"""
        pass
    
    @abstractmethod
    async def download_by_uid(
        self,
        uid: str,
        max_counts: int = 50,
        skip_existing: bool = True,
        task_id: Optional[str] = None,
        interval: Optional[str] = None,
    ) -> Tuple[int, int]:
        """根据用户 ID 下载视频"""
        pass
    
    @abstractmethod
    def get_progress(self, task_id: str) -> Optional[dict[str, Any]]:
        """获取下载进度"""
        pass

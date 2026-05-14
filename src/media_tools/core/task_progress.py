from __future__ import annotations
"""任务进度模型 — 被 pipeline、downloader、API 路由共享。

原位于 pipeline/models.py，因 douyin 下载器也需要使用而提取到 core，
消除 douyin → pipeline 的反向依赖。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Stage(str, Enum):
    """任务阶段枚举"""

    CREATED = "created"
    FETCHING = "fetching"
    AUDITING = "auditing"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def from_string(cls, value: str) -> Stage:
        """从字符串转换为 Stage 枚举"""
        value = value.strip().lower()
        mapping = {
            "initializing": cls.FETCHING,
            "scanning": cls.FETCHING,
            "queued": cls.CREATED,
            "listing": cls.FETCHING,
            "fetching": cls.FETCHING,
            "auditing": cls.AUDITING,
            "reconcile": cls.AUDITING,
            "downloading": cls.DOWNLOADING,
            "download": cls.DOWNLOADING,
            "transcribing": cls.TRANSCRIBING,
            "transcribe": cls.TRANSCRIBING,
            "exporting": cls.EXPORTING,
            "export": cls.EXPORTING,
            "completed": cls.COMPLETED,
            "success": cls.COMPLETED,
            "done": cls.COMPLETED,
            "failed": cls.FAILED,
            "error": cls.FAILED,
            "cancelled": cls.CANCELLED,
            "canceled": cls.CANCELLED,
        }
        return mapping.get(value, cls.DOWNLOADING)


@dataclass
class DownloadProgress:
    """下载阶段进度"""

    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    total: int = 0
    current_video: str = ""
    current_video_progress: float = 0.0
    current_index: int = 0

    def to_dict(self) -> dict:
        return {
            "downloaded": self.downloaded,
            "skipped": self.skipped,
            "failed": self.failed,
            "total": self.total,
            "current_video": self.current_video,
            "current_video_progress": self.current_video_progress,
            "current_index": self.current_index,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> Optional[DownloadProgress]:
        if not data:
            return None
        return cls(
            downloaded=int(data.get("downloaded", 0)),
            skipped=int(data.get("skipped", 0)),
            failed=int(data.get("failed", 0)),
            total=int(data.get("total", 0)),
            current_video=str(data.get("current_video", "")),
            current_video_progress=float(data.get("current_video_progress", 0.0)),
            current_index=int(data.get("current_index", 0)),
        )


@dataclass
class TranscribeProgress:
    """转写阶段进度"""

    done: int = 0
    skipped: int = 0
    failed: int = 0
    total: int = 0
    current_video: str = ""
    current_account: str = ""

    def to_dict(self) -> dict:
        return {
            "done": self.done,
            "skipped": self.skipped,
            "failed": self.failed,
            "total": self.total,
            "current_video": self.current_video,
            "current_account": self.current_account,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> Optional[TranscribeProgress]:
        if not data:
            return None
        return cls(
            done=int(data.get("done", 0)),
            skipped=int(data.get("skipped", 0)),
            failed=int(data.get("failed", 0)),
            total=int(data.get("total", 0)),
            current_video=str(data.get("current_video", "")),
            current_account=str(data.get("current_account", "")),
        )


@dataclass
class TaskProgress:
    """完整任务进度"""

    stage: Stage = field(default_factory=lambda: Stage.CREATED)
    overall_percent: float = 0.0
    download_progress: Optional[DownloadProgress] = None
    transcribe_progress: Optional[TranscribeProgress] = None
    error_count: int = 0
    errors: list = field(default_factory=list)
    details: list = field(default_factory=list)
    start_time: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "stage": self.stage.value,
            "overall_percent": self.overall_percent,
            "download_progress": self.download_progress.to_dict() if self.download_progress else None,
            "transcribe_progress": self.transcribe_progress.to_dict() if self.transcribe_progress else None,
            "error_count": self.error_count,
            "errors": self.errors,
            "details": self.details,
            "start_time": self.start_time,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> Optional[TaskProgress]:
        if not data:
            return None
        stage_str = data.get("stage", "created")
        try:
            stage = Stage(stage_str)
        except ValueError:
            stage = Stage.from_string(stage_str)
        return cls(
            stage=stage,
            overall_percent=float(data.get("overall_percent", 0.0)),
            download_progress=DownloadProgress.from_dict(data.get("download_progress")),
            transcribe_progress=TranscribeProgress.from_dict(data.get("transcribe_progress")),
            error_count=int(data.get("error_count", 0)),
            errors=list(data.get("errors", [])),
            details=list(data.get("details", [])),
            start_time=data.get("start_time"),
        )

from __future__ import annotations
"""Pipeline 数据模型"""

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional, Union

from media_tools.pipeline.error_types import ErrorType
from media_tools.transcribe.runtime import ensure_dir

logger = logging.getLogger(__name__)


class AccountPool:
    """Qwen 账号池。

    Qwen 平台约束：同账号同时只允许 1 个文件上传。orchestrator 用
    `_upload_locks: dict[account_id, asyncio.Lock]` 在客户端强制 per-account
    互斥；账号池 acquire 时优先返回 upload 锁空闲的账号，避免把视频压到忙账号
    的等待队列。失败/限流时 exclude 该账号，acquire 后续会跳过。
    """

    def __init__(self, accounts: list[dict[str, Any]]):
        self._accounts = accounts
        self._cursor = 0
        self._excluded: set[str] = set()
        # orchestrator 在创建账号池后注入 upload_locks 引用，acquire 用它判断空闲
        self._upload_locks_view: dict[str, asyncio.Lock] = {}
        logger.info(f"初始化账号池：{len(accounts)} 个账号")

    def set_upload_locks_view(self, locks: dict[str, asyncio.Lock]) -> None:
        """orchestrator 注入 upload_locks dict 引用（共享对象，按需更新）。"""
        self._upload_locks_view = locks

    @property
    def account_count(self) -> int:
        return len(self._accounts)

    @property
    def available_count(self) -> int:
        return len(self._accounts) - len(self._excluded)

    def _is_idle(self, account_id: str) -> bool:
        lock = self._upload_locks_view.get(account_id)
        return lock is None or not lock.locked()

    async def acquire(self, preferred_account_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """选一个可用账号。preferred 命中直接返回；否则空闲账号优先 + round-robin。

        acquire 后调用方还要 await upload_lock，hint 是空闲不保证拿到——但减少
        多个视频挤到同一账号 lock 队列的概率。
        """
        if preferred_account_id and preferred_account_id not in self._excluded:
            for account in self._accounts:
                if str(account.get("account_id", "")) == preferred_account_id:
                    return account

        available = [a for a in self._accounts if str(a.get("account_id", "")) not in self._excluded]
        if not available:
            return None

        idle = [a for a in available if self._is_idle(str(a.get("account_id", "")))]
        candidates = idle if idle else available

        selected = candidates[self._cursor % len(candidates)]
        self._cursor += 1
        return selected

    def release(self, account_id: str) -> None:
        """no-op：上传 lock 退出 with 块时已自动释放，账号池无需 counting。

        保留接口避免大量调用方改动；逻辑上空操作。
        """
        return

    def exclude(self, account_id: str) -> None:
        if account_id and account_id not in self._excluded:
            self._excluded.add(account_id)
            logger.warning(f"账号已排除: {account_id}")

    def get_stats(self) -> dict[str, Any]:
        active = sum(
            1 for a in self._accounts
            if str(a.get("account_id", "")) not in self._excluded
            and not self._is_idle(str(a.get("account_id", "")))
        )
        return {
            "total_accounts": len(self._accounts),
            "available_accounts": self.available_count,
            "active_uploads": active,
            "excluded": sorted(self._excluded),
        }


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    retryable_errors: list[ErrorType] = field(default_factory=lambda: [
        ErrorType.NETWORK,
        ErrorType.TIMEOUT,
        ErrorType.QUOTA,
        ErrorType.SERVICE_UNAVAILABLE,
        ErrorType.UNKNOWN,
    ])


@dataclass
class VideoState:
    """单个视频的处理状态"""
    video_path: str
    status: str = "pending"
    attempt: int = 0
    max_attempts: int = 3
    error_type: str = ""
    error_message: str = ""
    transcript_path: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    last_error_time: float = 0.0

    @property
    def can_retry(self) -> bool:
        return self.status == "failed" and self.attempt < self.max_attempts

    @property
    def duration(self) -> float:
        if self.completed_at > 0 and self.started_at > 0:
            return self.completed_at - self.started_at
        return 0.0


@dataclass
class PipelineResultV2:
    """Pipeline 执行结果 V2"""
    success: bool
    video_path: Path
    transcript_path: Optional[Path] = None
    error: Optional[str] = None
    error_type: ErrorType = ErrorType.UNKNOWN
    attempts: int = 1
    duration: float = 0.0
    account_id: Optional[str] = None
    video_deleted: bool = False

    def __str__(self) -> str:
        if self.success:
            return f"转写成功: {self.transcript_path} (耗时: {self.duration:.1f}s, 尝试: {self.attempts}次)"
        return f"转写失败 [{self.error_type.value}]: {self.error} (尝试: {self.attempts}次)"


@dataclass
class BatchReport:
    """批量执行汇总报告"""
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    total_duration: float = 0.0
    avg_duration: float = 0.0
    results: list[dict] = field(default_factory=list)
    error_summary: dict[str, int] = field(default_factory=dict)
    started_at: float = 0.0
    completed_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "summary": {
                "total": self.total,
                "success": self.success,
                "failed": self.failed,
                "skipped": self.skipped,
                "total_duration_sec": round(self.total_duration, 2),
                "avg_duration_sec": round(self.avg_duration, 2),
                "started_at": self.started_at,
                "completed_at": self.completed_at,
            },
            "error_summary": self.error_summary,
            "results": self.results,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


# ---------------------------------------------------------------------------
# 任务进度模型（从 domain/entities/task.py 迁移，原 DDD 目录已被清理）
# ---------------------------------------------------------------------------
from enum import Enum


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
    def from_string(cls, value: str) -> "Stage":
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
    def from_dict(cls, data: Optional[dict]) -> Optional["DownloadProgress"]:
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
    def from_dict(cls, data: Optional[dict]) -> Optional["TranscribeProgress"]:
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
    def from_dict(cls, data: Optional[dict]) -> Optional["TaskProgress"]:
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

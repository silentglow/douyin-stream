from __future__ import annotations
"""Pipeline 数据模型"""

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional, Union

from .error_types import ErrorType
from ..transcribe.runtime import ensure_dir

logger = logging.getLogger(__name__)


class AccountPool:
    """账号轮换池 - 按余额权重分配任务，余额多的分配更多

    Qwen 平台约束：同一账号同一时刻仅允许一个上传操作，
    多余请求会被服务端排队挂起。因此上传并发数 = 活跃账号数。

    转写轮询（poll_until_done）仅读取状态，不占用上传资源，
    可与上传并行，因此每账号允许的并发槽位 > 1 仍有意义。
    """

    DEFAULT_MAX_CONCURRENT = 10
    DEFAULT_UPLOAD_CONCURRENT = 1

    def __init__(
        self,
        accounts: list[dict[str, Any]],
        balances: list[int] | None = None,
        max_concurrent_per_account: Optional[int] = None,
        upload_concurrent_per_account: Optional[int] = None,
    ):
        self._accounts = accounts
        self._balances = balances or [0] * len(accounts)
        self._current = 0
        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition(self._lock)
        self._max_concurrent = max_concurrent_per_account or self.DEFAULT_MAX_CONCURRENT
        self._upload_concurrent = upload_concurrent_per_account or self.DEFAULT_UPLOAD_CONCURRENT
        self._active_count: dict[str, int] = {}
        self._upload_active_count: dict[str, int] = {}
        self._excluded: set[str] = set()
        logger.info(
            f"初始化加权账号池，共 {len(accounts)} 个账号，"
            f"总余额 {sum(self._balances)}，每账号最大并发 {self._max_concurrent}，"
            f"每账号上传并发 {self._upload_concurrent}"
        )

    @property
    def account_count(self) -> int:
        return len(self._accounts)

    @property
    def max_upload_concurrency(self) -> int:
        return self._upload_concurrent * len(self._accounts)

    def _pick_account(self) -> Optional[Dict[str, Any]]:
        import random

        if not self._accounts:
            return None

        available = [
            (i, a) for i, a in enumerate(self._accounts)
            if self._active_count.get(str(a.get("account_id", "")), 0) < self._max_concurrent
            and str(a.get("account_id", "")) not in self._excluded
        ]

        if not available:
            return None

        indices, accounts = zip(*available)
        balances = [self._balances[i] for i in indices]
        total = sum(balances)

        if total > 0:
            safe_balances = [max(b, 1) for b in balances]
            selected = random.choices(accounts, weights=safe_balances, k=1)[0]
        else:
            selected = accounts[self._current % len(accounts)]
            self._current = (self._current + 1) % len(accounts)

        return selected

    def _pick_upload_account(self) -> Optional[Dict[str, Any]]:
        import random

        if not self._accounts:
            return None

        available = [
            (i, a) for i, a in enumerate(self._accounts)
            if self._upload_active_count.get(str(a.get("account_id", "")), 0) < self._upload_concurrent
            and str(a.get("account_id", "")) not in self._excluded
        ]

        if not available:
            return None

        indices, accounts = zip(*available)
        balances = [self._balances[i] for i in indices]
        total = sum(balances)

        if total > 0:
            safe_balances = [max(b, 1) for b in balances]
            selected = random.choices(accounts, weights=safe_balances, k=1)[0]
        else:
            selected = accounts[self._current % len(accounts)]
            self._current = (self._current + 1) % len(accounts)

        return selected

    async def acquire(self, preferred_account_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        async with self._condition:
            while True:
                selected = None
                if preferred_account_id and preferred_account_id not in self._excluded:
                    for account in self._accounts:
                        account_id = str(account.get("account_id", ""))
                        if account_id == preferred_account_id and self._active_count.get(account_id, 0) < self._max_concurrent:
                            selected = account
                            break
                if selected is None:
                    selected = self._pick_account()

                if selected is not None:
                    account_id = str(selected.get("account_id", ""))
                    self._active_count[account_id] = self._active_count.get(account_id, 0) + 1
                    return selected

                await self._condition.wait()

    def release(self, account_id: str) -> None:
        """释放一个并发槽位并通知等待者"""
        cur = self._active_count.get(account_id, 0)
        if cur > 1:
            self._active_count[account_id] = cur - 1
        else:
            self._active_count.pop(account_id, None)
        self._notify_waiters_sync()

    async def acquire_upload_slot(self, preferred_account_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        async with self._condition:
            while True:
                selected = None
                if preferred_account_id and preferred_account_id not in self._excluded:
                    for account in self._accounts:
                        account_id = str(account.get("account_id", ""))
                        if account_id == preferred_account_id and self._upload_active_count.get(account_id, 0) < self._upload_concurrent:
                            selected = account
                            break
                if selected is None:
                    selected = self._pick_upload_account()

                if selected is not None:
                    account_id = str(selected.get("account_id", ""))
                    self._upload_active_count[account_id] = self._upload_active_count.get(account_id, 0) + 1
                    return selected

                await self._condition.wait()

    def release_upload_slot(self, account_id: str) -> None:
        """释放一个上传槽位并通知等待者"""
        cur = self._upload_active_count.get(account_id, 0)
        if cur > 1:
            self._upload_active_count[account_id] = cur - 1
        else:
            self._upload_active_count.pop(account_id, None)
        self._notify_waiters_sync()

    def exclude(self, account_id: str) -> None:
        self._excluded.add(account_id)
        self._notify_waiters_sync()

    @property
    def available_count(self) -> int:
        return len(self._accounts) - len(self._excluded)

    def _notify_waiters_sync(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon(self._do_notify)
        except RuntimeError:
            pass

    def _do_notify(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            if loop.is_closed():
                return
            async def _inner():
                async with self._condition:
                    self._condition.notify_all()
            asyncio.ensure_future(_inner(), loop=loop)
        except RuntimeError:
            pass

    def remaining(self) -> int:
        return sum(
            1 for a in self._accounts
            if self._active_count.get(str(a.get("account_id", "")), 0) < self._max_concurrent
        )

    def upload_remaining(self) -> int:
        return sum(
            1 for a in self._accounts
            if self._upload_active_count.get(str(a.get("account_id", "")), 0) < self._upload_concurrent
        )

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_accounts": len(self._accounts),
            "upload_concurrency_per_account": self._upload_concurrent,
            "max_concurrency_per_account": self._max_concurrent,
            "max_upload_concurrency": self.max_upload_concurrency,
            "upload_available_slots": self.upload_remaining(),
            "task_available_slots": self.remaining(),
            "active_uploads": dict(self._upload_active_count),
            "active_tasks": dict(self._active_count),
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

    def save_to_file(self, path: Path) -> None:
        ensure_dir(path.parent)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())
        logger.info(f"报告已保存到: {path}")

from __future__ import annotations
"""Pipeline 数据模型"""

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional, Union

from media_tools.transcribe.errors import ErrorType
from media_tools.transcribe.runtime import ensure_dir

logger = logging.getLogger(__name__)


class AccountPool:
    """Qwen 账号池。

    Qwen 平台约束：同账号同时只允许 1 个文件上传。orchestrator 用
    `_upload_locks: dict[account_id, asyncio.Lock]` 在客户端强制 per-account
    互斥；账号池 acquire 时优先返回 upload 锁空闲的账号，避免把视频压到忙账号
    的等待队列。失败/限流时 exclude 该账号，acquire 后续会跳过。

    分配策略 (v2026-05-26 改进)：在 idle 优先的前提下，按 use_count（当前进程
    内每个账号被派发的次数）升序选——即 LRU。替代之前的 `cursor % len`
    方案，后者在 `candidates` 大小随并发 idle 数变化时容易把首位账号反复打。
    """

    def __init__(self, accounts: list[dict[str, Any]]):
        self._accounts = accounts
        # account_id -> 被 acquire 选中的次数，用于 LRU 排序
        self._use_count: dict[str, int] = {}
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
        """选一个可用账号。preferred 命中直接返回；否则空闲 + 用过次数最少（LRU）优先。

        acquire 后调用方还要 await upload_lock，hint 是空闲不保证拿到——但减少
        多个视频挤到同一账号 lock 队列的概率。
        """
        if preferred_account_id and preferred_account_id not in self._excluded:
            for account in self._accounts:
                if str(account.get("account_id", "")) == preferred_account_id:
                    self._use_count[preferred_account_id] = (
                        self._use_count.get(preferred_account_id, 0) + 1
                    )
                    return account

        available = [a for a in self._accounts if str(a.get("account_id", "")) not in self._excluded]
        if not available:
            return None

        # 排序键：(0 if idle else 1, use_count asc) → idle 账号在前，同 idle 状态下用过最少的在前
        def _key(account: dict[str, Any]) -> tuple[int, int]:
            acc_id = str(account.get("account_id", ""))
            return (
                0 if self._is_idle(acc_id) else 1,
                self._use_count.get(acc_id, 0),
            )

        available.sort(key=_key)
        selected = available[0]
        selected_id = str(selected.get("account_id", ""))
        self._use_count[selected_id] = self._use_count.get(selected_id, 0) + 1
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

    def reset_excluded(self) -> None:
        """重置排除状态，在外层重试前调用，给所有账号新的尝试机会。"""
        if self._excluded:
            logger.info(f"重置账号排除状态，恢复 {len(self._excluded)} 个账号")
            self._excluded.clear()

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
            "use_count": dict(self._use_count),
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
# 任务进度模型 — 从 core/task_progress.py 重新导出（兼容层）
# ---------------------------------------------------------------------------
from media_tools.core.task_progress import (
    Stage,
    DownloadProgress,
    TranscribeProgress,
    TaskProgress,
)

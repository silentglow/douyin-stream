from __future__ import annotations
"""Qwen 账号池服务 - 封装账号加载、上传锁管理与状态标记。"""

import asyncio
import sqlite3
from pathlib import Path
from typing import Any, Optional

from media_tools.logger import get_logger
from media_tools.pipeline.models import AccountPool

logger = get_logger(__name__)


class AccountPoolService:
    """Qwen 账号池服务。

    职责：
    1. 从数据库加载活跃账号，构建 AccountPool
    2. 管理 per-account 上传锁（Qwen 平台约束：同账号同时只允许 1 个文件上传）
    3. 标记账号状态（过期、限流）和使用记录
    4. 根据账号数调整入口并发门控
    """

    def __init__(
        self,
        auth_state_path: Optional[Path] = None,
        default_account_id: str = "",
    ):
        self._auth_state_path = auth_state_path
        self._default_account_id = default_account_id
        self._account_pool: AccountPool | None = None
        self._upload_locks: dict[str, asyncio.Lock] = {}
        self._upload_locks_guard: asyncio.Lock | None = None
        self._effective_concurrency: int = 1

    @property
    def account_pool(self) -> AccountPool | None:
        return self._account_pool

    @property
    def effective_concurrency(self) -> int:
        return self._effective_concurrency

    def resolve_accounts(self) -> list[dict[str, Any]]:
        """从数据库加载活跃 Qwen 账号，构建账号池。

        数据库无记录时回退到单账号模式（auth_state_path）。
        """
        try:
            from media_tools.store.db import get_db_connection
            from media_tools.transcribe.db_account_pool import (
                build_qwen_auth_state_path_for_account,
                load_qwen_accounts_from_db,
            )

            accounts = [a for a in load_qwen_accounts_from_db() if a.status == "active"]

            resolved: list[dict[str, Any]] = []
            for account in accounts:
                path = (
                    Path(account.auth_state_path)
                    if str(account.auth_state_path).strip()
                    else build_qwen_auth_state_path_for_account(account.account_id)
                )
                resolved.append({"account_id": account.account_id, "auth_state_path": path})

            if resolved:
                self._account_pool = AccountPool(resolved)
                self._account_pool.set_upload_locks_view(self._upload_locks)
                logger.info(f"账号池初始化: {[a['account_id'] for a in resolved]}")
                self._adjust_gates()
                return resolved
        except (sqlite3.Error, OSError, TypeError, ValueError) as e:
            logger.warning(f"加载账号池失败: {e}")

        if self._auth_state_path is None:
            return []

        single_account = [
            {"account_id": self._default_account_id, "auth_state_path": Path(self._auth_state_path)}
        ]
        self._account_pool = AccountPool(single_account)
        self._account_pool.set_upload_locks_view(self._upload_locks)
        self._adjust_gates()
        return single_account

    def _adjust_gates(self) -> None:
        """根据账号数调整入口并发门控。"""
        if self._account_pool is None:
            return
        n_accounts = self._account_pool.account_count
        new_concurrency = max(1, 2 * n_accounts)
        old = self._effective_concurrency
        self._effective_concurrency = new_concurrency
        if old != new_concurrency:
            logger.info(f"入口闸门跟随账号数: {old} → {new_concurrency}（= 2×{n_accounts}）")

    async def get_upload_lock(self, account_id: str) -> asyncio.Lock:
        """按需为账号创建上传锁。同一账号永远拿到同一把锁，跨视频共享。"""
        if self._upload_locks_guard is None:
            self._upload_locks_guard = asyncio.Lock()
        async with self._upload_locks_guard:
            lock = self._upload_locks.get(account_id)
            if lock is None:
                lock = asyncio.Lock()
                self._upload_locks[account_id] = lock
                logger.info(f"上传锁创建: account={account_id}")
            return lock

    def mark_status(self, account_id: str, status: str) -> None:
        """标记 Qwen 账号状态（expired / rate_limited 时自动排除）。"""
        if not account_id:
            return
        try:
            from media_tools.core.cookie_manager import get_cookie_manager
            get_cookie_manager().mark_account_status("qwen", account_id, status)
            if status in ("expired", "rate_limited") and self._account_pool:
                self._account_pool.exclude(account_id)
        except (RuntimeError, OSError, ValueError) as e:
            logger.warning(f"标记Qwen账号状态失败: {e}")

    def mark_used(self, account_id: str) -> None:
        """标记 Qwen 账号已被使用。"""
        if not account_id:
            return
        try:
            from media_tools.core.cookie_manager import get_cookie_manager
            get_cookie_manager().mark_account_used("qwen", account_id)
        except (RuntimeError, OSError, ValueError) as e:
            logger.warning(f"标记Qwen账号使用失败: {e}")

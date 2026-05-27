"""AccountPoolService 单例化回归测试 (v2026-05-26)。

历史 bug: 每次 create_orchestrator() 都新建 AccountPoolService → 新 _upload_locks dict
→ 跨 orchestrator 同账号的 upload lock 互相不可见 → 千问端同账号被多文件并发上传打爆
→ OSS write timeout 大量失败。

修复: 进程内 process-wide 单例,所有 orchestrator 共享同一个 _upload_locks dict。
"""

from __future__ import annotations

import asyncio

import pytest

from media_tools.accounts.service import (
    AccountPoolService,
    get_account_pool_service,
    reset_account_pool_service,
)


@pytest.fixture(autouse=True)
def reset_singleton_between_tests():
    """每个测试前后清掉单例,避免互相污染。"""
    reset_account_pool_service()
    yield
    reset_account_pool_service()


def test_get_account_pool_service_returns_same_instance() -> None:
    """多次调用返回同一实例(不管参数是否相同)。"""
    s1 = get_account_pool_service(default_account_id="a")
    s2 = get_account_pool_service(default_account_id="a")
    s3 = get_account_pool_service(default_account_id="b")  # 不同参数也应返回同一实例
    assert s1 is s2 is s3, "get_account_pool_service 必须返回单例,实际拿到 3 个不同对象"


def test_singleton_preserves_upload_locks_across_callers() -> None:
    """关键回归:第一次 caller 创建的 upload lock,第二次 caller 拿到的是同一把。"""
    s1 = get_account_pool_service(default_account_id="acc-1")

    async def _acquire_locks():
        lock1 = await s1.get_upload_lock("acc-1")
        # 模拟另一个 orchestrator 拿单例
        s2 = get_account_pool_service(default_account_id="acc-1")
        lock2 = await s2.get_upload_lock("acc-1")
        return lock1, lock2

    lock1, lock2 = asyncio.run(_acquire_locks())
    assert lock1 is lock2, "同账号的 upload lock 跨 orchestrator 必须是同一把,否则同账号会被多文件并发上传"


def test_reset_account_pool_service_invalidates_singleton() -> None:
    """reset 后下次 get 拿到全新实例(测试隔离用)。"""
    s1 = get_account_pool_service(default_account_id="acc-A")
    reset_account_pool_service()
    s2 = get_account_pool_service(default_account_id="acc-A")
    assert s1 is not s2, "reset 之后 get_account_pool_service 应该返回新实例"


def test_direct_instantiation_still_works_for_backwards_compat() -> None:
    """AccountPoolService 类本身仍可直接实例化(测试 / 老代码兼容)。"""
    s = AccountPoolService(default_account_id="test")
    assert s.effective_concurrency == 1
    assert s.account_pool is None

"""AccountPool 分配均衡回归测试 (v2026-05-26)。

历史教训：旧 cursor 实现下，candidates 大小随并发 idle 数变化时，cursor 不能保证
账号轮转——多文件并发时第一位账号(如 guiqing)会被反复打中。

新实现：use_count LRU，多次 acquire 后所有账号被派发次数尽量平均。
"""
from __future__ import annotations

import asyncio

import pytest

from media_tools.transcribe.models import AccountPool


def _make_pool(account_ids: list[str]) -> AccountPool:
    return AccountPool([{"account_id": aid} for aid in account_ids])


@pytest.mark.asyncio
async def test_acquire_distributes_evenly_across_accounts() -> None:
    """3 个账号,acquire 9 次,每个账号应被选中 3 次(完全均衡)。"""
    pool = _make_pool(["a", "b", "c"])
    counts = {"a": 0, "b": 0, "c": 0}
    for _ in range(9):
        account = await pool.acquire()
        assert account is not None
        counts[str(account["account_id"])] += 1
    assert counts == {"a": 3, "b": 3, "c": 3}, f"分配应该完全均衡,实际 {counts}"


@pytest.mark.asyncio
async def test_acquire_lru_prefers_least_used_account() -> None:
    """每次 acquire 后 use_count 增加,下次该账号排到最后。"""
    pool = _make_pool(["a", "b", "c"])
    # 第一次 acquire — 任意一个(都没用过)
    first = await pool.acquire()
    assert first is not None
    first_id = str(first["account_id"])
    # 第二次 acquire — 不应该再是 first_id(它已经 use_count=1,其他还是 0)
    second = await pool.acquire()
    assert second is not None
    assert str(second["account_id"]) != first_id, (
        f"LRU 应该挑没用过的账号,但又选了 {first_id}"
    )


@pytest.mark.asyncio
async def test_preferred_account_id_honored_when_available() -> None:
    """preferred 命中时直接返回该账号(resume / 同任务重试的粘性)。"""
    pool = _make_pool(["a", "b", "c"])
    # 先消耗几次 acquire 把 use_count 拉开
    for _ in range(3):
        await pool.acquire()
    # 即使 a 已经被用过,preferred='a' 也应返回 a
    account = await pool.acquire(preferred_account_id="a")
    assert account is not None
    assert str(account["account_id"]) == "a"


@pytest.mark.asyncio
async def test_excluded_account_not_returned_even_if_least_used() -> None:
    """exclude 后即使 use_count=0 也不会被选中。"""
    pool = _make_pool(["a", "b", "c"])
    pool.exclude("a")  # a 从未被用过但被排除
    seen = set()
    for _ in range(6):
        account = await pool.acquire()
        assert account is not None
        seen.add(str(account["account_id"]))
    assert "a" not in seen, "被 exclude 的账号 a 不应出现"
    assert seen == {"b", "c"}


@pytest.mark.asyncio
async def test_idle_preference_overrides_lru() -> None:
    """upload lock 持有的账号(忙)会被排到 idle 账号之后,即使它 use_count 更低。"""
    pool = _make_pool(["a", "b", "c"])
    locks: dict[str, asyncio.Lock] = {"a": asyncio.Lock(), "b": asyncio.Lock(), "c": asyncio.Lock()}
    pool.set_upload_locks_view(locks)

    # 先 acquire 几次让 b, c 的 use_count 拉到 2,a 仍是 0
    for _ in range(2):
        for _ in range(2):
            account = await pool.acquire()
            # 跳过 a (我们模拟一下场景:a 拉低)
            if str(account["account_id"]) == "a":
                # 把 a 再 acquire 一次让它不是最低,简化测试用直接操作 use_count
                pass

    # 直接控制状态便于断言:重设 pool
    pool = _make_pool(["a", "b", "c"])
    pool.set_upload_locks_view(locks)
    # 模拟 a 正在上传(lock 持有)
    await locks["a"].acquire()
    try:
        # 即使 a 的 use_count 还是 0(理论上 LRU 应优先选 a),但 a 忙了应该跳过
        first = await pool.acquire()
        assert first is not None
        assert str(first["account_id"]) != "a", (
            "a 的 upload lock 被持有,acquire 不应返回它"
        )
    finally:
        locks["a"].release()

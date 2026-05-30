from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from media_tools.accounts.auth_state import resolve_qwen_cookie_string
from media_tools.common.http import RequestsApiContext, api_json
from media_tools.common.runtime import ensure_dir
from media_tools.transcribe.config import load_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QuotaSnapshot:
    raw: Any
    used_upload: int
    total_upload: int
    remaining_upload: int
    gratis_upload: bool
    free: bool


@dataclass(frozen=True)
class ClaimEquityResult:
    claimed: bool
    skipped: bool
    reason: str
    before_snapshot: QuotaSnapshot | None
    after_snapshot: QuotaSnapshot | None


def number_value(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed


def remaining_hours_from_snapshot(snapshot: QuotaSnapshot) -> int:
    return max(0, number_value(snapshot.remaining_upload) // 60)


def today_key() -> str:
    return datetime.now().astimezone().date().isoformat()


def quota_state_path() -> Path:
    return load_config().paths.quota_state_file


def _read_quota_state() -> tuple[Path, dict[str, Any]]:
    file_path = quota_state_path()
    try:
        parsed = json.loads(file_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return file_path, {}
    return file_path, parsed if isinstance(parsed, dict) else {}


def _write_quota_state(records: dict[str, Any]) -> Path:
    file_path = quota_state_path()
    ensure_dir(file_path.parent)
    tmp_path = file_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    import os

    os.replace(str(tmp_path), str(file_path))
    return file_path


def account_key(account_id: str) -> str:
    return account_id or "__default__"


def build_daily_record(record: Any) -> dict[str, Any]:
    source = record if isinstance(record, dict) else {}
    return {
        "consumedMinutes": number_value(source.get("consumedMinutes")),
        "lastBeforeRemaining": source.get("lastBeforeRemaining"),
        "lastAfterRemaining": source.get("lastAfterRemaining"),
        "lastEquityClaimAt": str(source.get("lastEquityClaimAt", "")),
        "lastEquityBeforeRemaining": source.get("lastEquityBeforeRemaining"),
        "lastEquityAfterRemaining": source.get("lastEquityAfterRemaining"),
        "updatedAt": str(source.get("updatedAt", "")),
    }


def merge_consumption_record(
    current_record: dict[str, Any],
    *,
    consumed_minutes: int,
    before_remaining: int,
    after_remaining: int,
    updated_at: str,
) -> dict[str, Any]:
    current_day = build_daily_record(current_record)
    return {
        **current_day,
        "consumedMinutes": number_value(current_day.get("consumedMinutes")) + max(0, number_value(consumed_minutes)),
        "lastBeforeRemaining": before_remaining,
        "lastAfterRemaining": after_remaining,
        "updatedAt": updated_at,
    }


def merge_equity_claim_record(
    current_record: dict[str, Any],
    *,
    before_remaining: int,
    after_remaining: int,
    claimed_at: str,
) -> dict[str, Any]:
    current_day = build_daily_record(current_record)
    return {
        **current_day,
        "lastEquityClaimAt": claimed_at,
        "lastEquityBeforeRemaining": before_remaining,
        "lastEquityAfterRemaining": after_remaining,
        "updatedAt": claimed_at,
    }


async def get_quota_snapshot(
    *,
    auth_state_path: str | Path,
    account_id: str = "",
    cookie_string: str = "",
    referer: str = "https://www.qianwen.com/discover/audioread",
) -> QuotaSnapshot:
    headers = {
        "referer": referer,
        "platform": "QIANWEN",
        "request-id": str(uuid.uuid4()),
        "bx-v": "2.5.36",
    }

    quota_json: Any
    resolved_cookie = cookie_string.strip() or resolve_qwen_cookie_string(
        auth_state_path=auth_state_path,
        account_id=account_id,
    )
    api = RequestsApiContext(cookie_string=resolved_cookie)
    try:
        quota_json = await api_json(
            api,
            "https://api.qianwen.com/growth/user/benefit/base",
            {"requestId": str(uuid.uuid4())},
            headers,
        )
    finally:
        await api.dispose()

    # API 返回登录错误时直接抛出，让上层识别为 AUTH 错误
    if isinstance(quota_json, dict) and quota_json.get("errorCode") == "NOT_LOGIN":
        from media_tools.transcribe.errors import TranscribeErrorClassifier

        error_info = TranscribeErrorClassifier.classify("账号权限不足")
        raise RuntimeError(f"{error_info.message}: {quota_json.get('errorMsg', '未登录')}")

    data = quota_json.get("data", []) if isinstance(quota_json, dict) else []
    tingwu_benefit = {}
    if isinstance(data, list):
        tingwu_benefit = next(
            (
                item
                for item in data
                if isinstance(item, dict) and item.get("benefitType") == "TINGWU_TRANSCRIPTION_DURATION"
            ),
            {},
        )

    if not tingwu_benefit:
        return QuotaSnapshot(
            raw=quota_json,
            used_upload=0,
            total_upload=0,
            remaining_upload=0,
            gratis_upload=False,
            free=False,
        )

    used_hours = number_value(tingwu_benefit.get("usageQuota"))
    remaining_hours = number_value(tingwu_benefit.get("remainingQuota"))
    total_hours = used_hours + remaining_hours

    used_minutes = used_hours * 60
    remaining_minutes = remaining_hours * 60
    total_minutes = total_hours * 60

    total_quota_str = str(tingwu_benefit.get("totalQuotaAndUnit", ""))
    total_match = re.search(r"共(\d+)小时(\d+)分钟", total_quota_str)
    if total_match:
        total_minutes = int(total_match.group(1)) * 60 + int(total_match.group(2))

    return QuotaSnapshot(
        raw=quota_json,
        used_upload=used_minutes,
        total_upload=total_minutes,
        remaining_upload=remaining_minutes,
        gratis_upload=False,
        free=bool(remaining_hours > 0),
    )


def record_quota_consumption(
    *,
    account_id: str,
    consumed_minutes: int,
    before_snapshot: QuotaSnapshot,
    after_snapshot: QuotaSnapshot,
) -> None:
    import fcntl

    minutes = max(0, number_value(consumed_minutes))
    file_path = quota_state_path()
    ensure_dir(file_path.parent)

    # 使用文件锁防止并发写入丢失数据
    lock_path = file_path.with_suffix(".lock")
    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            _, records = _read_quota_state()
            key = account_key(account_id)
            day = today_key()
            account_record = records.get(key, {})
            account_record[day] = merge_consumption_record(
                account_record.get(day, {}),
                consumed_minutes=minutes,
                before_remaining=before_snapshot.remaining_upload,
                after_remaining=after_snapshot.remaining_upload,
                updated_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
            records[key] = account_record
            _write_quota_state(records)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def get_daily_quota_record(account_id: str) -> dict[str, Any]:
    _, records = _read_quota_state()
    return build_daily_record(records.get(account_key(account_id), {}).get(today_key()))


async def trigger_equity_claim_via_api(*, cookie_string: str) -> dict[str, Any]:
    api = RequestsApiContext(cookie_string=cookie_string)
    try:
        payload = {}
        headers = {
            "referer": "https://www.qianwen.com/equity",
            "platform": "QIANWEN",
            "bx-v": "2.5.36",
        }
        center_result = await api_json(
            api,
            "https://api.qianwen.com/growth/user/task/benefit/center/list",
            payload,
            headers,
        )
        reward_result = await api_json(
            api,
            "https://api.qianwen.com/growth/user/task/reward/notice",
            payload,
            headers,
        )
    finally:
        await api.dispose()
    return {
        "center_list": center_result if isinstance(center_result, dict) else {"raw": center_result},
        "reward_notice": reward_result if isinstance(reward_result, dict) else {"raw": reward_result},
    }


def has_claimed_equity_today(account_id: str) -> bool:
    daily = get_daily_quota_record(account_id)
    return bool(daily.get("lastEquityClaimAt"))


def _write_equity_claim_record(
    *,
    account_id: str,
    before_snapshot: QuotaSnapshot,
    after_snapshot: QuotaSnapshot,
) -> None:
    import fcntl

    file_path = quota_state_path()
    ensure_dir(file_path.parent)
    lock_path = file_path.with_suffix(".lock")
    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            _, records = _read_quota_state()
            key = account_key(account_id)
            day = today_key()
            account_record = records.get(key, {})
            claimed_at = datetime.now(UTC).isoformat(timespec="seconds")
            account_record[day] = merge_equity_claim_record(
                account_record.get(day, {}),
                before_remaining=before_snapshot.remaining_upload,
                after_remaining=after_snapshot.remaining_upload,
                claimed_at=claimed_at,
            )
            records[key] = account_record
            _write_quota_state(records)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


async def claim_equity_quota(
    *,
    account_id: str,
    auth_state_path: str | Path,
    force: bool = False,
) -> ClaimEquityResult:
    if not force and has_claimed_equity_today(account_id):
        return ClaimEquityResult(
            claimed=False,
            skipped=True,
            reason="already-claimed-today",
            before_snapshot=None,
            after_snapshot=None,
        )

    cookie_string = resolve_qwen_cookie_string(auth_state_path=auth_state_path, account_id=account_id)

    before_snapshot = await get_quota_snapshot(
        auth_state_path=auth_state_path,
        account_id=account_id,
        cookie_string=cookie_string,
        referer="https://www.qianwen.com/equity",
    )

    # 浏览器点击「打卡/领取」会依次触发 center/list 与 reward/notice。
    # 即使两个接口都返回 200 也不代表真领到，因此 trigger 调用失败也不立刻 return ——
    # 让下面的 before/after 额度差兜底判定，避免依赖单次返回值。
    try:
        await trigger_equity_claim_via_api(cookie_string=cookie_string)
    except (RuntimeError, OSError, ValueError) as e:
        logger.warning(f"[额度领取] trigger 调用异常 account_id={account_id}: {e}")

    after_snapshot = await get_quota_snapshot(
        auth_state_path=auth_state_path,
        account_id=account_id,
        cookie_string=cookie_string,
        referer="https://www.qianwen.com/equity",
    )

    # 硬判定：only when 额度真的增加了，才算领到。before==after 说明 Qwen 端没发放，
    # 不写 lastEquityClaimAt，让定时任务后续仍可重试。
    delta = after_snapshot.remaining_upload - before_snapshot.remaining_upload
    if delta <= 0:
        return ClaimEquityResult(
            claimed=False,
            skipped=False,
            reason="quota-unchanged",
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
        )

    _write_equity_claim_record(
        account_id=account_id,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
    )
    return ClaimEquityResult(
        claimed=True,
        skipped=False,
        reason=f"claimed-{delta}min",
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
    )

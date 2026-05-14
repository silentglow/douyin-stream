from __future__ import annotations
"""Qwen 账户状态查询与配额领取服务"""

import logging
import sqlite3
from pathlib import Path
from typing import Any

from media_tools.store.db import get_db_connection
from media_tools.transcribe.auth_state import save_qwen_cookie_string
from media_tools.transcribe.db_account_pool import build_qwen_auth_state_path_for_account
from media_tools.transcribe.quota import (
    claim_equity_quota,
    get_quota_snapshot,
    has_claimed_equity_today,
    remaining_hours_from_snapshot,
)

logger = logging.getLogger(__name__)


async def get_qwen_account_status() -> dict:
    """获取所有 Qwen 账户的状态和剩余额度"""
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            db_rows = conn.execute(
                "SELECT account_id, remark, status, auth_state_path, cookie_data FROM Accounts_Pool WHERE platform='qwen'",
            ).fetchall()

        rows: list[dict[str, Any]] = []
        path_updates: list[tuple[str, str]] = []
        status_updates: list[tuple[str, str]] = []

        for account in db_rows:
            account_id = str(account["account_id"])
            remark = str(account["remark"] or "")
            status = str(account["status"] or "active")
            auth_state_path = str(account["auth_state_path"] or "")
            cookie_data = str(account["cookie_data"] or "")

            remaining_hours = 0
            resolved_auth_state_path = auth_state_path.strip()

            if status == "active":
                if not resolved_auth_state_path:
                    if cookie_data.strip():
                        resolved_path = build_qwen_auth_state_path_for_account(account_id)
                        try:
                            save_qwen_cookie_string(cookie_data, resolved_path, sync_db=False)
                            path_updates.append((str(resolved_path), account_id))
                            resolved_auth_state_path = str(resolved_path)
                        except (OSError, sqlite3.Error):
                            status = "invalid"
                    else:
                        status = "invalid"

            if status == "active" and resolved_auth_state_path:
                try:
                    snapshot = await get_quota_snapshot(
                        auth_state_path=Path(resolved_auth_state_path),
                        account_id=account_id,
                    )
                    remaining_hours = remaining_hours_from_snapshot(snapshot)
                except (RuntimeError, OSError, ValueError, TypeError) as e:
                    logger.warning(f"获取 Qwen 额度失败: account_id={account_id}, error={e}")
                    remaining_hours = 0

            if status != str(account["status"] or "active"):
                status_updates.append((status, account_id))

            rows.append({
                "accountId": account_id,
                "accountLabel": remark or account_id,
                "remaining_hours": remaining_hours,
                "status": status,
            })

        if path_updates or status_updates:
            with get_db_connection() as conn:
                for auth_path, acc_id in path_updates:
                    conn.execute(
                        "UPDATE Accounts_Pool SET auth_state_path=? WHERE account_id=? AND platform='qwen'",
                        (auth_path, acc_id),
                    )
                for new_status, acc_id in status_updates:
                    conn.execute(
                        "UPDATE Accounts_Pool SET status=? WHERE account_id=? AND platform='qwen'",
                        (new_status, acc_id),
                    )
                conn.commit()

        return {"status": "success", "accounts": rows}
    except (sqlite3.Error, OSError, RuntimeError) as e:
        return {"status": "unavailable", "message": str(e), "accounts": []}


async def claim_qwen_quota() -> dict:
    """手动触发领取每日 Qwen 额度（force=True，直接调 API）"""
    results = []
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        accounts = conn.execute(
            "SELECT account_id, status, auth_state_path, remark FROM Accounts_Pool WHERE platform='qwen'",
        ).fetchall()

    for account in accounts:
        account_id = str(account["account_id"])
        remark = str(account["remark"] or account_id[:8])
        status = str(account["status"] or "active")
        auth_state_path = str(account["auth_state_path"] or "")

        if status != "active":
            results.append({"accountId": account_id, "status": "skipped", "reason": f"account-{status}"})
            logger.info(f"[额度领取] {remark}: 跳过（账号状态 {status}）")
            continue

        resolved_path = Path(auth_state_path) if auth_state_path.strip() else build_qwen_auth_state_path_for_account(account_id)
        result = await claim_equity_quota(account_id=account_id, auth_state_path=resolved_path, force=True)
        if result.claimed:
            before = result.before_snapshot.remaining_upload if result.before_snapshot else "?"
            after = result.after_snapshot.remaining_upload if result.after_snapshot else "?"
            delta = (
                result.after_snapshot.remaining_upload - result.before_snapshot.remaining_upload
                if result.before_snapshot and result.after_snapshot else "?"
            )
            logger.info(f"[额度领取] {remark}: 领取成功（额度 {before} → {after}, +{delta} 分钟）")
        elif result.reason == "quota-unchanged":
            before = result.before_snapshot.remaining_upload if result.before_snapshot else "?"
            after = result.after_snapshot.remaining_upload if result.after_snapshot else "?"
            logger.warning(f"[额度领取] {remark}: 未领到（额度未变化 {before} → {after}，可能 cookie 失效或 API 已变更）")
        else:
            logger.info(f"[额度领取] {remark}: 跳过（{result.reason}）")
        results.append({
            "accountId": account_id,
            "status": "claimed" if result.claimed else "skipped",
            "reason": result.reason,
        })
    logger.info(f"[额度领取] 完成，共 {len(results)} 个账号")
    return {"status": "success", "results": results}

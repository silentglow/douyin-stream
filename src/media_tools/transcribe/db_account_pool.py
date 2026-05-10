from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from media_tools.db.core import get_db_connection


@dataclass(frozen=True)
class DbQwenAccount:
    account_id: str
    remark: str
    status: str
    cookie_data: str
    auth_state_path: str


def build_qwen_auth_state_path_for_account(account_id: str) -> Path:
    safe = str(account_id).strip()
    return Path("data/auth") / f"qwen-storage-state-{safe}.json"


def load_qwen_accounts_from_db() -> list[DbQwenAccount]:
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT account_id, remark, status, cookie_data, auth_state_path FROM Accounts_Pool WHERE platform='qwen'",
        ).fetchall()

    accounts: list[DbQwenAccount] = []
    for row in rows:
        accounts.append(
            DbQwenAccount(
                account_id=str(row["account_id"]),
                remark=str(row["remark"] or ""),
                status=str(row["status"] or "active"),
                cookie_data=str(row["cookie_data"] or ""),
                auth_state_path=str(row["auth_state_path"] or ""),
            )
        )
    return accounts


def load_qwen_cookie_data_for_account(account_id: str) -> str:
    selected = str(account_id or "").strip()
    if not selected:
        return ""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT cookie_data FROM Accounts_Pool WHERE platform='qwen' AND account_id=?",
            (selected,),
        ).fetchone()
    if not row:
        return ""
    return str(row[0] or "").strip()

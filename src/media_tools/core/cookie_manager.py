from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from media_tools.store.db import get_db_connection
from media_tools.logger import get_logger

logger = get_logger(__name__)

SUPPORTED_PLATFORMS = ("douyin", "bilibili", "qwen")


@dataclass(frozen=True)
class CookieAccount:
    account_id: str
    platform: str
    cookie_data: str
    status: str
    remark: str
    auth_state_path: str
    last_used: Optional[str]


class CookieManager:
    SUPPORTED_PLATFORMS = SUPPORTED_PLATFORMS

    def get_cookie(self, platform: str, *, account_id: str = "") -> str:
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"不支持的平台: {platform}")
        if platform == "qwen":
            return self._get_qwen_cookie(account_id=account_id)
        return self._get_pool_cookie(platform, account_id=account_id)

    def get_active_account(self, platform: str) -> Optional[CookieAccount]:
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"不支持的平台: {platform}")
        with get_db_connection() as conn:
            conn.row_factory = None
            cursor = conn.execute(
                """
                SELECT account_id, platform, cookie_data, status,
                       COALESCE(remark, '') as remark,
                       COALESCE(auth_state_path, '') as auth_state_path,
                       last_used
                FROM Accounts_Pool
                WHERE platform = ? AND status = 'active'
                  AND cookie_data IS NOT NULL AND cookie_data != ''
                ORDER BY
                    CASE WHEN last_used IS NULL THEN 0 ELSE 1 END,
                    last_used ASC,
                    create_time ASC
                LIMIT 1
                """,
                (platform,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return CookieAccount(
                account_id=str(row[0]),
                platform=str(row[1]),
                cookie_data=str(row[2]),
                status=str(row[3]),
                remark=str(row[4]),
                auth_state_path=str(row[5]),
                last_used=str(row[6]) if row[6] else None,
            )

    def mark_account_used(self, platform: str, account_id: str) -> None:
        if not account_id:
            return
        try:
            with get_db_connection() as conn:
                conn.execute(
                    "UPDATE Accounts_Pool SET last_used = CURRENT_TIMESTAMP WHERE platform = ? AND account_id = ?",
                    (platform, account_id),
                )
                conn.commit()
        except (sqlite3.Error, OSError) as e:
            logger.warning(f"标记账号使用失败: platform={platform}, account_id={account_id}, error={e}")

    def mark_account_status(self, platform: str, account_id: str, status: str) -> None:
        if not account_id:
            return
        try:
            with get_db_connection() as conn:
                conn.execute(
                    "UPDATE Accounts_Pool SET status = ? WHERE platform = ? AND account_id = ?",
                    (status, platform, account_id),
                )
                conn.commit()
        except (sqlite3.Error, OSError) as e:
            logger.warning(f"标记账号状态失败: platform={platform}, account_id={account_id}, error={e}")

    def list_accounts(self, platform: str) -> list[CookieAccount]:
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"不支持的平台: {platform}")
        with get_db_connection() as conn:
            conn.row_factory = None
            rows = conn.execute(
                """
                SELECT account_id, platform, cookie_data, status,
                       COALESCE(remark, '') as remark,
                       COALESCE(auth_state_path, '') as auth_state_path,
                       last_used
                FROM Accounts_Pool
                WHERE platform = ?
                ORDER BY create_time ASC
                """,
                (platform,),
            ).fetchall()
        accounts: list[CookieAccount] = []
        for row in rows:
            accounts.append(
                CookieAccount(
                    account_id=str(row[0]),
                    platform=str(row[1]),
                    cookie_data=str(row[2] or ""),
                    status=str(row[3] or "active"),
                    remark=str(row[4] or ""),
                    auth_state_path=str(row[5] or ""),
                    last_used=str(row[6]) if row[6] else None,
                )
            )
        return accounts

    def _get_pool_cookie(self, platform: str, *, account_id: str = "") -> str:
        if account_id:
            with get_db_connection() as conn:
                row = conn.execute(
                    "SELECT cookie_data FROM Accounts_Pool WHERE platform = ? AND account_id = ? AND status = 'active'",
                    (platform, account_id),
                ).fetchone()
                if row and row[0]:
                    self.mark_account_used(platform, account_id)
                    return str(row[0]).strip()
            return ""
        account = self.get_active_account(platform)
        if account:
            self.mark_account_used(platform, account.account_id)
            return account.cookie_data
        return ""

    def _get_qwen_cookie(self, *, account_id: str = "") -> str:
        from media_tools.transcribe.auth_state import resolve_qwen_cookie_string, default_qwen_auth_state_path
        return resolve_qwen_cookie_string(
            auth_state_path=default_qwen_auth_state_path(),
            account_id=account_id,
        )


_cookie_manager: Optional[CookieManager] = None


def get_cookie_manager() -> CookieManager:
    global _cookie_manager
    if _cookie_manager is None:
        _cookie_manager = CookieManager()
    return _cookie_manager

from __future__ import annotations
"""账号池数据访问层 - 所有 Accounts_Pool 表的操作集中在这里"""

import sqlite3
from typing import Any, Optional

from media_tools.store.db import get_db_connection


class AccountRepository:
    """账号池仓库 - Accounts_Pool 表的所有操作"""

    # ---------- READ ----------

    @staticmethod
    def list_by_platform(platform: str) -> list[dict[str, Any]]:
        """按平台查询账号列表。"""
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT account_id, status, last_used, remark, create_time FROM Accounts_Pool WHERE platform = ?",
                (platform,),
            )
            return [
                {
                    "id": row[0],
                    "status": row[1],
                    "last_used": row[2],
                    "remark": row[3] or "",
                    "create_time": row[4] or "",
                }
                for row in cursor.fetchall()
            ]

    @staticmethod
    def find_by_id(account_id: str, platform: str) -> Optional[tuple]:
        """按 ID 和平台查询账号。"""
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT account_id, status, last_used, remark, create_time FROM Accounts_Pool WHERE account_id = ? AND platform = ?",
                (account_id, platform),
            )
            row = cursor.fetchone()
            if row:
                return row
            return None

    @staticmethod
    def get_auth_state_path(account_id: str, platform: str) -> Optional[str]:
        """获取账号的 auth_state_path。"""
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT auth_state_path FROM Accounts_Pool WHERE account_id = ? AND platform = ?",
                (account_id, platform),
            )
            row = cursor.fetchone()
            return str(row[0]) if row and row[0] else None

    @staticmethod
    def list_qwen_with_cookie() -> list[dict[str, Any]]:
        """查询所有 Qwen 账号（含 cookie 和 auth_state_path）。"""
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT account_id, cookie_data, auth_state_path FROM Accounts_Pool WHERE platform = 'qwen'",
            ).fetchall()
            return [dict(row) for row in rows]

    # ---------- CREATE ----------

    @staticmethod
    def create(
        account_id: str,
        platform: str,
        cookie_data: str,
        remark: str = "",
        auth_state_path: Optional[str] = None,
        status: str = "active",
    ) -> None:
        """创建账号记录。"""
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO Accounts_Pool (account_id, platform, cookie_data, remark, auth_state_path, status) VALUES (?, ?, ?, ?, ?, ?)",
                (account_id, platform, cookie_data, remark, auth_state_path, status),
            )
            conn.commit()

    # ---------- UPDATE ----------

    @staticmethod
    def update_remark(account_id: str, platform: str, remark: str) -> int:
        """更新账号备注，返回受影响的行数。"""
        with get_db_connection() as conn:
            cursor = conn.execute(
                "UPDATE Accounts_Pool SET remark = ? WHERE account_id = ? AND platform = ?",
                (remark, account_id, platform),
            )
            conn.commit()
            return cursor.rowcount

    @staticmethod
    def update_cookie_and_status(
        account_id: str,
        platform: str,
        cookie_data: str,
        auth_state_path: Optional[str] = None,
        status: str = "active",
    ) -> int:
        """更新账号 Cookie 和状态，返回受影响的行数。"""
        with get_db_connection() as conn:
            if auth_state_path is not None:
                cursor = conn.execute(
                    "UPDATE Accounts_Pool SET cookie_data = ?, status = ?, auth_state_path = ? WHERE account_id = ? AND platform = ?",
                    (cookie_data, status, auth_state_path, account_id, platform),
                )
            else:
                cursor = conn.execute(
                    "UPDATE Accounts_Pool SET cookie_data = ?, status = ? WHERE account_id = ? AND platform = ?",
                    (cookie_data, status, account_id, platform),
                )
            conn.commit()
            return cursor.rowcount

    @staticmethod
    def update_auth_state_path(account_id: str, platform: str, auth_state_path: str, status: str = "active") -> None:
        """更新账号的 auth_state_path。"""
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE Accounts_Pool SET auth_state_path = ?, status = ? WHERE account_id = ? AND platform = ?",
                (auth_state_path, status, account_id, platform),
            )
            conn.commit()

    # ---------- DELETE ----------

    @staticmethod
    def delete(account_id: str, platform: str) -> int:
        """删除账号，返回受影响的行数。"""
        with get_db_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM Accounts_Pool WHERE account_id = ? AND platform = ?",
                (account_id, platform),
            )
            conn.commit()
            return cursor.rowcount

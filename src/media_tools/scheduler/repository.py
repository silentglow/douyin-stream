from __future__ import annotations

"""任务数据访问层 - 所有 task_queue 表的操作集中在这里"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
from typing import Any

from media_tools.core.workflow import validate_transition_by_str
from media_tools.store.db import get_db_connection


def _merge_task_payload(
    existing_payload: str | None,
    msg: str,
    result_summary: dict | None = None,
    subtasks: list | None = None,
) -> str:
    """合并任务 payload，保留现有字段并更新进度信息"""
    base_payload: dict = {}
    if existing_payload:
        try:
            parsed = json.loads(existing_payload)
            if isinstance(parsed, dict):
                base_payload = parsed
        except (json.JSONDecodeError, TypeError):
            base_payload = {}
    base_payload["msg"] = msg
    if result_summary:
        base_payload["total"] = result_summary.get("total", 0)
        base_payload["completed"] = result_summary.get("success", 0)
        base_payload["failed"] = result_summary.get("failed", 0)
        base_payload["result_summary"] = result_summary
    if subtasks:
        base_payload["subtasks"] = subtasks[-100:]
    return json.dumps(base_payload, ensure_ascii=False)


def _merge_payload_from_db(
    conn: sqlite3.Connection,
    task_id: str,
    msg: str,
    result_summary: dict | None = None,
    subtasks: list | None = None,
) -> str:
    """从数据库读取现有 payload 并合并新信息"""
    try:
        cursor = conn.execute("SELECT payload FROM task_queue WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        existing = row["payload"] if row else None
    except sqlite3.Error as e:
        logger.warning(f"读取任务payload失败: {e}")
        existing = None
    return _merge_task_payload(existing, msg, result_summary, subtasks)


class TaskRepository:
    """任务仓库 - task_queue 表的所有操作（含状态机验证）"""

    @staticmethod
    def _validate_transition(task_id: str, to_status: str) -> None:
        """验证状态转移是否合法，不合法则抛出 InvalidTransitionError。"""
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT status FROM task_queue WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            from_status = row[0] if row else "PENDING"
        validate_transition_by_str(from_status, to_status)

    # ---------- CREATE ----------

    @staticmethod
    def create(task_id: str, task_type: str, payload: dict | None = None) -> None:
        """创建新任务"""
        now = datetime.now().isoformat()
        payload_str = json.dumps(payload or {}, ensure_ascii=False)
        with get_db_connection() as conn:
            conn.execute(
                """INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time)
                   VALUES (?, ?, 'PENDING', 0.0, ?, ?, ?)""",
                (task_id, task_type, payload_str, now, now),
            )
            conn.commit()

    @staticmethod
    def create_running(task_id: str, task_type: str, payload: dict | None = None) -> None:
        """创建并标记为 RUNNING（用于 rerun）"""
        now = datetime.now().isoformat()
        payload_str = json.dumps(payload or {}, ensure_ascii=False)
        with get_db_connection() as conn:
            conn.execute(
                """INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time)
                   VALUES (?, ?, 'RUNNING', 0.0, ?, ?, ?)
                   ON CONFLICT(task_id) DO UPDATE SET
                       status = 'RUNNING',
                       progress = 0.0,
                       error_msg = NULL,
                       update_time = excluded.update_time""",
                (task_id, task_type, payload_str, now, now),
            )
            conn.commit()

    # ---------- READ ----------

    @staticmethod
    def find_by_id(task_id: str) -> dict[str, Any] | None:
        """按 ID 查询任务"""
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT * FROM task_queue WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def find_active() -> list[dict[str, Any]]:
        """查询未结束的任务（PENDING、RUNNING 或 PAUSED）。"""
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT * FROM task_queue WHERE status IN ('PENDING', 'RUNNING', 'PAUSED')")
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def find_paused_ids() -> list[str]:
        """查询暂停任务 ID，供清理历史时保留可恢复的任务。"""
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT task_id FROM task_queue WHERE status = 'PAUSED'")
            return [str(row["task_id"]) for row in cursor.fetchall()]

    @staticmethod
    def list_recent(limit: int = 50) -> list[dict[str, Any]]:
        """查询最近更新的任务"""
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM task_queue ORDER BY update_time DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_status(task_id: str) -> tuple[str | None, str | None]:
        """获取任务状态和类型"""
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT status, task_type FROM task_queue WHERE task_id = ?",
                (task_id,),
            )
            row = cursor.fetchone()
            if row:
                return row["status"], row["task_type"]
            return None, None

    @staticmethod
    def get_task_type_and_payload(task_id: str) -> tuple[str | None, str | None]:
        """获取任务类型和 payload"""
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT task_type, payload FROM task_queue WHERE task_id = ?",
                (task_id,),
            )
            row = cursor.fetchone()
            if row:
                return row["task_type"], row["payload"]
            return None, None

    @staticmethod
    def get_task_type_payload_status(task_id: str) -> tuple[str | None, str | None, str | None]:
        """获取任务类型、payload 和状态"""
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT task_type, payload, status FROM task_queue WHERE task_id = ?",
                (task_id,),
            )
            row = cursor.fetchone()
            if row:
                return row["task_type"], row["payload"], row["status"]
            return None, None, None

    @staticmethod
    def get_task_type_payload_auto_retry(task_id: str) -> tuple[str | None, str | None, bool]:
        """获取任务类型、payload 和 auto_retry"""
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT task_type, payload, auto_retry FROM task_queue WHERE task_id = ?",
                (task_id,),
            )
            row = cursor.fetchone()
            if row:
                return row["task_type"], row["payload"], bool(row["auto_retry"])
            return None, None, False

    # ---------- UPDATE ----------

    @staticmethod
    def update_progress(
        task_id: str,
        progress: float,
        msg: str,
        task_type: str = "pipeline",
        result_summary: dict | None = None,
        subtasks: list | None = None,
    ) -> None:
        """更新任务进度。

        - 不存在则插入新行（RUNNING）
        - 已存在且非终态时更新进度
        - 已是 COMPLETED / FAILED / CANCELLED 时不会被覆盖（避免 worker 晚到的进度复活终态任务）
        """
        now = datetime.now().isoformat()
        with get_db_connection() as conn:
            existing = conn.execute(
                "SELECT status FROM task_queue WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            payload_str = _merge_payload_from_db(conn, task_id, msg, result_summary, subtasks)
            if existing is None:
                conn.execute(
                    """INSERT INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time)
                       VALUES (?, ?, 'RUNNING', ?, ?, ?, ?)""",
                    (task_id, task_type, progress, payload_str, now, now),
                )
            else:
                conn.execute(
                    """UPDATE task_queue
                       SET status='RUNNING', progress=?, payload=?, update_time=?
                       WHERE task_id=? AND status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED', 'PAUSED')""",
                    (progress, payload_str, now, task_id),
                )
            conn.commit()

    @staticmethod
    def mark_running(task_id: str, progress: float = 0.0, payload: str | None = None) -> None:
        """标记任务为 RUNNING（校验+更新在同一连接中完成，避免 TOCTOU 竞态）"""
        now = datetime.now().isoformat()
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT status FROM task_queue WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            from_status = row[0] if row else "PENDING"
            validate_transition_by_str(from_status, "RUNNING")
            if payload:
                conn.execute(
                    "UPDATE task_queue SET status='RUNNING', progress=?, payload=?, update_time=? WHERE task_id=?",
                    (progress, payload, now, task_id),
                )
            else:
                conn.execute(
                    "UPDATE task_queue SET status='RUNNING', progress=?, update_time=? WHERE task_id=?",
                    (progress, now, task_id),
                )
            conn.commit()

    @staticmethod
    def mark_completed(
        task_id: str,
        msg: str,
        result_summary: dict | None = None,
        subtasks: list | None = None,
    ) -> None:
        """标记任务为 COMPLETED（校验+更新在同一连接中完成）"""
        now = datetime.now().isoformat()
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT status FROM task_queue WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            from_status = row[0] if row else "PENDING"
            validate_transition_by_str(from_status, "COMPLETED")
            payload_str = _merge_payload_from_db(conn, task_id, msg, result_summary, subtasks)
            conn.execute(
                "UPDATE task_queue SET status='COMPLETED', progress=1.0, payload=?, update_time=? WHERE task_id=?",
                (payload_str, now, task_id),
            )
            conn.commit()

    @staticmethod
    def mark_failed(task_id: str, error: str) -> None:
        """标记任务为 FAILED（校验+更新在同一连接中完成）"""
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT status FROM task_queue WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            from_status = row[0] if row else "PENDING"
            validate_transition_by_str(from_status, "FAILED")
            conn.execute(
                "UPDATE task_queue SET status='FAILED', error_msg=? WHERE task_id=?",
                (str(error), task_id),
            )
            conn.commit()

    @staticmethod
    def update_heartbeat(task_id: str) -> None:
        """更新任务心跳时间"""
        now = datetime.now().isoformat()
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE task_queue SET update_time = ? WHERE task_id = ? AND status IN ('PENDING', 'RUNNING')",
                (now, task_id),
            )
            conn.commit()

    @staticmethod
    def patch_payload(task_id: str, patch: dict[str, Any]) -> None:
        if not patch:
            return
        now = datetime.now().isoformat()
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT payload FROM task_queue WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            existing_raw = row["payload"] if row and isinstance(row, sqlite3.Row) else (row[0] if row else None)

            base: dict[str, Any] = {}
            if existing_raw:
                try:
                    parsed = json.loads(str(existing_raw))
                except (TypeError, ValueError, json.JSONDecodeError):
                    parsed = {}
                if isinstance(parsed, dict):
                    base = parsed

            base.update(patch)
            conn.execute(
                "UPDATE task_queue SET payload=?, update_time=? WHERE task_id=?",
                (json.dumps(base, ensure_ascii=False), now, task_id),
            )
            conn.commit()

    @staticmethod
    def set_auto_retry(task_id: str, enabled: bool) -> None:
        """设置自动重试"""
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE task_queue SET auto_retry = ? WHERE task_id = ?",
                (1 if enabled else 0, task_id),
            )
            conn.commit()

    @staticmethod
    def update_priority(task_id: str, priority: int) -> None:
        """更新任务优先级"""
        now = datetime.now().isoformat()
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE task_queue SET priority = ?, update_time = ? WHERE task_id = ?",
                (priority, now, task_id),
            )
            conn.commit()

    # ---------- DELETE ----------

    @staticmethod
    def delete(task_id: str) -> None:
        """删除单个任务"""
        with get_db_connection() as conn:
            conn.execute("DELETE FROM task_queue WHERE task_id = ?", (task_id,))
            conn.commit()

    @staticmethod
    def clear_history(hours: int = 2) -> None:
        """清除历史任务"""
        cutoff = datetime.now() - timedelta(hours=hours)
        with get_db_connection() as conn:
            conn.execute(
                "DELETE FROM task_queue WHERE status IN ('COMPLETED', 'FAILED', 'CANCELLED') AND update_time < ?",
                (cutoff.isoformat(),),
            )
            conn.commit()

    @staticmethod
    def clear_all_history() -> None:
        """清除所有已完成/失败/取消的任务"""
        with get_db_connection() as conn:
            conn.execute(
                "DELETE FROM task_queue WHERE status IN ('COMPLETED', 'FAILED', 'CANCELLED')",
            )
            conn.commit()

    @staticmethod
    def delete_all_except(task_ids_to_keep: set[str] | None = None) -> list[str]:
        """删除除指定 task_id 外的所有任务，返回被删除的 task_id 列表。"""
        keep = task_ids_to_keep or set()
        with get_db_connection() as conn:
            if keep:
                placeholders = ",".join(["?"] * len(keep))
                params = tuple(keep)
                rows = conn.execute(
                    f"SELECT task_id FROM task_queue WHERE task_id NOT IN ({placeholders})",
                    params,
                ).fetchall()
                conn.execute(
                    f"DELETE FROM task_queue WHERE task_id NOT IN ({placeholders})",
                    params,
                )
            else:
                rows = conn.execute("SELECT task_id FROM task_queue").fetchall()
                conn.execute("DELETE FROM task_queue")
            conn.commit()

        deleted: list[str] = []
        for row in rows:
            if isinstance(row, sqlite3.Row):
                deleted.append(str(row["task_id"]))
            else:
                deleted.append(str(row[0]))
        return deleted

    @staticmethod
    def search_by_type_or_payload(query: str, limit: int = 10) -> list[dict[str, Any]]:
        """按任务类型或 payload 搜索任务（LIKE 匹配）。"""
        pattern = f"%{query}%"
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT
                    'task' as type,
                    task_id as id,
                    task_type as title,
                    status as subtitle,
                    NULL as status
                FROM task_queue
                WHERE task_type LIKE ? OR payload LIKE ?
                ORDER BY update_time DESC
                LIMIT ?
                """,
                (pattern, pattern, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

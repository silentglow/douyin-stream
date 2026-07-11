import json
import logging
import sqlite3
from datetime import datetime, timedelta

# 架构耦合说明：scheduler 层直接依赖 api.websocket_manager 广播任务状态变更。
# 理想方案是通过事件总线解耦，但当前规模下直接调用更简单可控。
from media_tools.api.websocket_manager import manager
from media_tools.scheduler.repository import _merge_payload_from_db
from media_tools.scheduler.retry import schedule_auto_retry
from media_tools.scheduler.state import is_task_deleted
from media_tools.store.db import get_db_connection

logger = logging.getLogger(__name__)
DEFAULT_TASK_STALE_MINUTES = 20
UPLOAD_STAGE_STALE_MINUTES = 30


def get_task_stale_minutes() -> int:
    from media_tools.core.config import get_app_config

    return get_app_config().task_stale_minutes


def _extract_payload_pipeline_stage(payload: str | None) -> str:
    if not payload:
        return ""
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, TypeError, ValueError):
        return ""
    if not isinstance(parsed, dict):
        return ""
    pipeline_progress = parsed.get("pipeline_progress")
    if not isinstance(pipeline_progress, dict):
        return ""
    stage = pipeline_progress.get("stage")
    return stage.strip() if isinstance(stage, str) else ""


def _get_stale_minutes_for_stage(stage: str, default_minutes: int) -> int:
    normalized = stage.strip().lower()
    if normalized == "upload":
        return max(default_minutes, UPLOAD_STAGE_STALE_MINUTES)
    return default_minutes


SERVER_RESTART_ERROR = "服务重启导致任务中断，请点击重试恢复。"


def cleanup_stale_tasks(
    conn: sqlite3.Connection,
    stale_minutes: int | None = None,
    is_startup: bool = False,
) -> int:
    default_minutes = stale_minutes if stale_minutes is not None else get_task_stale_minutes()
    default_minutes = default_minutes if default_minutes > 0 else DEFAULT_TASK_STALE_MINUTES

    now = datetime.now()
    now_iso = now.isoformat()

    old_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT task_id, task_type, payload, update_time
            FROM task_queue
            WHERE status IN ('PENDING', 'RUNNING')
              AND update_time IS NOT NULL
            """
        ).fetchall()

        recovered_count = 0
        for row in rows:
            task_id = row["task_id"]
            update_time_raw = row["update_time"]
            try:
                last_update = datetime.fromisoformat(str(update_time_raw))
            except ValueError:
                continue

            stage = _extract_payload_pipeline_stage(row["payload"])
            minutes = _get_stale_minutes_for_stage(stage, default_minutes)
            if last_update >= (now - timedelta(minutes=minutes)):
                continue

            error_msg = SERVER_RESTART_ERROR if is_startup else "任务长时间没有更新，已自动标记为失败，请重新发起。"

            conn.execute(
                """
                UPDATE task_queue
                SET
                    status = 'FAILED',
                    progress = 0.0,
                    error_msg = CASE
                        WHEN error_msg IS NULL OR error_msg = '' THEN ?
                        ELSE error_msg
                    END,
                    update_time = ?
                WHERE task_id = ?
                  AND status IN ('PENDING', 'RUNNING')
                """,
                (error_msg, now_iso, task_id),
            )
            recovered_count += 1

        if is_startup and recovered_count > 0:
            logger.info(f"startup: marked {recovered_count} orphan task(s) as FAILED (server restart)")

        failed_cutoff = (datetime.now() - timedelta(days=1)).isoformat()
        completed_cutoff = (datetime.now() - timedelta(days=3)).isoformat()
        cancelled_cutoff = (datetime.now() - timedelta(days=1)).isoformat()
        conn.execute(
            "DELETE FROM task_queue WHERE status = 'FAILED' AND update_time < ?",
            (failed_cutoff,),
        )
        conn.execute(
            "DELETE FROM task_queue WHERE status = 'COMPLETED' AND update_time < ?",
            (completed_cutoff,),
        )
        conn.execute(
            "DELETE FROM task_queue WHERE status = 'CANCELLED' AND update_time < ?",
            (cancelled_cutoff,),
        )
        row = conn.execute("SELECT COUNT(*) as cnt FROM task_queue WHERE status = 'FAILED'").fetchone()
        if row and row["cnt"] > 50:
            excess = row["cnt"] - 50
            conn.execute(
                "DELETE FROM task_queue WHERE task_id IN ("
                "  SELECT task_id FROM task_queue WHERE status = 'FAILED'"
                "  ORDER BY update_time ASC LIMIT ?"
                ")",
                (excess,),
            )

        return recovered_count
    finally:
        conn.row_factory = old_factory


async def notify_task_update(
    task_id: str,
    progress: float,
    msg: str,
    status: str = "RUNNING",
    task_type: str = "pipeline",
    result_summary: dict | None = None,
    subtasks: list | None = None,
    stage: str = "",
    pipeline_progress: dict | None = None,
):
    payload = {
        "task_id": task_id,
        "progress": progress,
        "msg": msg,
        "status": status,
        "task_type": task_type,
        "update_time": datetime.now().isoformat(),
    }
    if stage:
        payload["stage"] = stage
    if result_summary:
        payload["result_summary"] = result_summary
    if subtasks:
        payload["subtasks"] = subtasks[-20:]
    if pipeline_progress:
        payload["pipeline_progress"] = pipeline_progress
    await manager.broadcast({"type": "task_update", "payload": payload})


# _merge_task_payload 和 _merge_payload_from_db 从 task_repository.py 导入，消除重复代码


async def update_task_progress(
    task_id: str,
    progress: float,
    msg: str,
    task_type: str = "pipeline",
    result_summary: dict | None = None,
    subtasks: list | None = None,
    stage: str = "",
    pipeline_progress: dict | None = None,
):
    if is_task_deleted(task_id):
        return
    updated = False
    try:
        now = datetime.now().isoformat()
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status FROM task_queue WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if row and row["status"] in ("COMPLETED", "FAILED", "CANCELLED", "PAUSED"):
                return

            payload_str = _merge_payload_from_db(conn, task_id, msg, result_summary, subtasks)
            if stage or pipeline_progress:
                try:
                    parsed = json.loads(payload_str) if payload_str else {}
                except (json.JSONDecodeError, TypeError, ValueError):
                    parsed = {}
                if isinstance(parsed, dict):
                    pp = parsed.get("pipeline_progress")
                    if not isinstance(pp, dict):
                        pp = {}
                    if stage:
                        pp["stage"] = stage
                    if pipeline_progress:
                        pp.update(pipeline_progress)
                    parsed["pipeline_progress"] = pp
                    payload_str = json.dumps(parsed, ensure_ascii=False)
            if row is None:
                # 用 OR IGNORE 避免与并发 INSERT 撞主键，再走 UPDATE 路径补齐进度
                conn.execute(
                    """INSERT OR IGNORE INTO task_queue (task_id, task_type, status, progress, payload, create_time, update_time)
                       VALUES (?, ?, 'RUNNING', ?, ?, ?, ?)""",
                    (task_id, task_type, progress, payload_str, now, now),
                )
                cursor = conn.execute(
                    """UPDATE task_queue
                       SET status='RUNNING', progress=?, payload=?, update_time=?
                       WHERE task_id=? AND status IN ('PENDING', 'RUNNING')""",
                    (progress, payload_str, now, task_id),
                )
                updated = cursor.rowcount > 0
            else:
                cursor = conn.execute(
                    """UPDATE task_queue
                       SET status='RUNNING', progress=?, payload=?, update_time=?
                       WHERE task_id=? AND status IN ('PENDING', 'RUNNING')""",
                    (progress, payload_str, now, task_id),
                )
                updated = cursor.rowcount > 0
    except (sqlite3.Error, OSError, RuntimeError) as e:
        logger.error(f"Error updating task: {e}")
        return
    # 仅当 DB 真正写入了 RUNNING 状态时才广播进度，避免向已转入终态的任务发送过期 RUNNING 通知
    if not updated:
        return
    await notify_task_update(
        task_id, progress, msg, "RUNNING", task_type, result_summary, subtasks, stage, pipeline_progress
    )


async def _mark_task_paused(task_id: str, task_type: str) -> bool:
    """Persist a cooperative pause without allowing late worker updates to revive it."""
    msg = "任务已暂停"
    updated = False
    progress = 0.0
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT progress FROM task_queue WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                return False
            progress = float(row["progress"] or 0.0)
            payload_str = _merge_payload_from_db(conn, task_id, msg)
            cursor = conn.execute(
                """UPDATE task_queue
                   SET status='PAUSED', payload=?, update_time=?
                   WHERE task_id=? AND status IN ('PENDING', 'RUNNING')""",
                (payload_str, datetime.now().isoformat(), task_id),
            )
            updated = cursor.rowcount > 0
    except (sqlite3.Error, OSError, RuntimeError) as e:
        logger.error(f"Failed to mark task {task_id} as paused: {e}")
        return False
    if updated:
        await notify_task_update(task_id, progress, msg, "PAUSED", task_type)
    return updated


async def _mark_task_cancelled(task_id: str, task_type: str) -> None:
    msg = "任务已取消"
    updated = False
    try:
        with get_db_connection() as conn:
            payload_str = _merge_payload_from_db(conn, task_id, msg)
            cursor = conn.execute(
                """UPDATE task_queue
                   SET status='CANCELLED', payload=?, update_time=CURRENT_TIMESTAMP
                   WHERE task_id=? AND status IN ('PENDING', 'RUNNING', 'PAUSED')""",
                (payload_str, task_id),
            )
            updated = cursor.rowcount > 0
    except (sqlite3.Error, OSError, RuntimeError) as e:
        logger.error(f"Failed to mark task {task_id} as cancelled: {e}")
        return
    # 仅在 DB 状态真正变更时广播，避免向已是终态的任务发送过期通知导致前端状态闪烁
    if updated:
        await notify_task_update(task_id, 0.0, msg, "CANCELLED", task_type)


async def _complete_task(
    task_id: str,
    task_type: str,
    msg: str,
    status: str = "COMPLETED",
    error_msg: str | None = None,
    result_summary: dict | None = None,
    subtasks: list | None = None,
) -> None:
    pipeline_progress: dict | None = None
    progress_for_notify: float = 0.0
    updated = False
    try:
        now = datetime.now().isoformat()
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            existing = conn.execute(
                "SELECT progress FROM task_queue WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            existing_progress = float(existing["progress"]) if existing and existing["progress"] is not None else 0.0
            payload_str = _merge_payload_from_db(conn, task_id, msg, result_summary, subtasks)
            try:
                parsed = json.loads(payload_str) if payload_str else {}
            except (json.JSONDecodeError, TypeError, ValueError):
                parsed = {}
            if isinstance(parsed, dict):
                pp = parsed.get("pipeline_progress")
                if isinstance(pp, dict) and pp:
                    pipeline_progress = dict(pp)
            # COMPLETED → 1.0；FAILED 保留现有进度（避免突然回退）
            new_progress = 1.0 if status == "COMPLETED" else existing_progress
            progress_for_notify = new_progress
            # 状态机：COMPLETED / CANCELLED / PARTIAL_FAILED 都是终态，不允许被覆盖。
            # 尤其 PARTIAL_FAILED：部分子任务已成功，整任务再被改成 FAILED 会触发 auto_retry
            # 重跑所有子任务（含已成功），违背 PARTIAL_FAILED 的设计语义。
            cursor = conn.execute(
                """UPDATE task_queue
                   SET status=?, progress=?, payload=?, error_msg=?, update_time=?
                   WHERE task_id=? AND status NOT IN ('COMPLETED', 'CANCELLED', 'PARTIAL_FAILED', 'PAUSED')""",
                (status, new_progress, payload_str, error_msg, now, task_id),
            )
            updated = cursor.rowcount > 0
    except (sqlite3.Error, OSError, RuntimeError) as e:
        logger.error(f"Failed to complete task {task_id} in DB: {e}")
        return
    # DB 更新被状态机拒绝（任务已是 COMPLETED/CANCELLED）时不广播，避免前端从终态闪回伪造状态
    if not updated:
        return
    await notify_task_update(
        task_id,
        progress_for_notify,
        msg,
        status,
        task_type,
        result_summary,
        subtasks,
        pipeline_progress=pipeline_progress,
    )
    if status == "FAILED":
        # PARTIAL_FAILED 不自动重试整任务（避免重跑已成功子任务）；
        # 用户可通过 UI"只重试失败子任务"入口手工重新调度。
        schedule_auto_retry(task_id)


async def _fail_task(task_id: str, task_type: str, error: str) -> None:
    updated = False
    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                """UPDATE task_queue SET status='FAILED', error_msg=?, update_time=?
                   WHERE task_id=? AND status NOT IN ('COMPLETED', 'CANCELLED', 'PARTIAL_FAILED', 'PAUSED')""",
                (str(error), datetime.now().isoformat(), task_id),
            )
            updated = cursor.rowcount > 0
    except (sqlite3.Error, OSError) as e:
        logger.error(f"Failed to fail task {task_id} in DB: {e}")
        return
    if not updated:
        return
    await notify_task_update(task_id, 0.0, str(error), "FAILED", task_type)
    schedule_auto_retry(task_id)

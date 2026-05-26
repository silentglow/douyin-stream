import sqlite3
import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from media_tools.store.db import get_db_connection, get_table_columns

router = APIRouter(prefix="/api/v1/scheduler", tags=["scheduler"], redirect_slashes=False)
logger = logging.getLogger(__name__)

# Initialize scheduler (started by startup_scheduler() on app lifespan)
scheduler = BackgroundScheduler()
SYSTEM_JOB_IDS = {"__stale_task_cleanup__", "__auto_claim_qwen_quota__"}

class ScheduleRequest(BaseModel):
    cron_expr: str  # e.g., "0 2 * * *" for 02:00 daily
    enabled: bool = True

class ToggleRequest(BaseModel):
    enabled: bool

def _run_scan_all_following():
    """The actual job executed by the scheduler"""
    logger.info("Running scheduled task: full sync all following")
    try:
        from media_tools.platform.douyin import download_all
        download_all(auto_confirm=True)
        logger.info("Scheduled task 'full sync all following' completed successfully.")
    except (OSError, RuntimeError, ImportError) as e:
        logger.error(f"Scheduled task 'full sync all following' failed: {e}")


def _register_system_jobs() -> None:
    # Register periodic stale task cleanup (every 10 minutes)
    from media_tools.scheduler.ops import cleanup_stale_tasks

    def _cleanup_job():
        try:
            with get_db_connection() as conn:
                cleanup_stale_tasks(conn, is_startup=False)
                conn.commit()
        except (sqlite3.Error, OSError) as e:
            logger.error(f"Stale task cleanup failed: {e}")

    scheduler.add_job(
        _cleanup_job,
        trigger="interval",
        minutes=10,
        id="__stale_task_cleanup__",
        replace_existing=True,
        max_instances=1,
    )

    # Auto-claim Qwen daily quota at 08:05
    def _auto_claim_qwen_quota():
        try:
            import asyncio
            from pathlib import Path
            from media_tools.transcribe.quota import claim_equity_quota, has_claimed_equity_today
            from media_tools.accounts.db_account_pool import (
                build_qwen_auth_state_path_for_account,
                load_qwen_accounts_from_db,
            )

            targets = load_qwen_accounts_from_db()
            logger.info(f"[定时额度领取] 开始，共 {len(targets)} 个账号")

            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                for target in targets:
                    account_id = target.account_id
                    remark = getattr(target, 'remark', '') or account_id[:8]
                    if target.status != "active":
                        logger.info(f"[定时额度领取] {remark}: 跳过（账号状态 {target.status}）")
                        continue
                    if has_claimed_equity_today(account_id):
                        logger.info(f"[定时额度领取] {remark}: 跳过（今日已领取）")
                        continue
                    auth_state_path = (
                        Path(target.auth_state_path)
                        if str(target.auth_state_path).strip()
                        else build_qwen_auth_state_path_for_account(account_id)
                    )
                    result = loop.run_until_complete(
                        claim_equity_quota(account_id=account_id, auth_state_path=auth_state_path)
                    )
                    if result.claimed:
                        before = result.before_snapshot.remaining_upload if result.before_snapshot else "?"
                        after = result.after_snapshot.remaining_upload if result.after_snapshot else "?"
                        delta = (
                            result.after_snapshot.remaining_upload - result.before_snapshot.remaining_upload
                            if result.before_snapshot and result.after_snapshot else "?"
                        )
                        logger.info(f"[定时额度领取] {remark}: 领取成功（额度 {before} → {after}, +{delta} 分钟）")
                    elif result.reason == "quota-unchanged":
                        before = result.before_snapshot.remaining_upload if result.before_snapshot else "?"
                        after = result.after_snapshot.remaining_upload if result.after_snapshot else "?"
                        logger.warning(f"[定时额度领取] {remark}: 未领到（额度未变化 {before} → {after}，可能 cookie 失效或 API 已变更）")
                    else:
                        logger.info(f"[定时额度领取] {remark}: 跳过（{result.reason}）")
            finally:
                asyncio.set_event_loop(None)
                try:
                    loop.close()
                except Exception:  # noqa: defensive
                    pass
            logger.info("[定时额度领取] 完成")
        except (RuntimeError, OSError, ValueError) as e:
            logger.error(f"[定时额度领取] 失败: {e}")

    scheduler.add_job(
        _auto_claim_qwen_quota,
        trigger=CronTrigger(hour=8, minute=5),
        id="__auto_claim_qwen_quota__",
        replace_existing=True,
        max_instances=1,
    )

    # 创作者自动同步（每 30 分钟扫描一次）
    def _auto_creator_sync():
        import asyncio
        from datetime import timezone, timedelta
        from media_tools.scheduler.repository import TaskRepository
        from media_tools.creators.sync import CreatorSyncWorker
        from media_tools.core import background as _bg

        # 派发到主 loop 上跑 worker，避免在 APScheduler 线程起子 loop 让
        # `_active_tasks` 注册的 Task 对象绑定在已关闭的 loop 上（用户点 cancel 时
        # 主 loop 调子 loop 的 task 行为未定义 → 静默失效）。
        main_loop = _bg.get_main_loop()
        if main_loop is None:
            logger.error("[自动同步] 主 loop 未初始化，跳过本轮")
            return

        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            creator_columns = get_table_columns(conn, "creators")
            if "auto_sync" not in creator_columns:
                return
            rows = conn.execute(
                "SELECT uid, last_fetch_time FROM creators WHERE auto_sync = 1"
            ).fetchall()

        now = datetime.now(timezone.utc)
        sync_threshold = timedelta(hours=6)
        synced_count = 0

        for row in rows:
            uid = row["uid"]
            last_fetch = row["last_fetch_time"]

            needs_sync = True
            if last_fetch:
                try:
                    fetch_dt = datetime.fromisoformat(str(last_fetch).replace("Z", "+00:00"))
                    if fetch_dt.tzinfo is None:
                        fetch_dt = fetch_dt.replace(tzinfo=timezone.utc)
                    if now - fetch_dt < sync_threshold:
                        needs_sync = False
                except (ValueError, OSError):
                    pass

            if not needs_sync:
                continue

            task_id = str(uuid.uuid4())
            try:
                TaskRepository.create_running(
                    task_id, "creator_sync_incremental", {"uid": uid, "mode": "incremental"}
                )
            except (sqlite3.Error, OSError, ValueError) as e:
                logger.error(f"[自动同步] 创建任务失败 {uid}: {e}")
                continue

            try:
                fut = asyncio.run_coroutine_threadsafe(
                    CreatorSyncWorker().execute(task_id, uid=uid, mode="incremental"),
                    main_loop,
                )
                # 同步等待单个 sync 完成，10 分钟硬上限避免 APScheduler 线程被卡住
                fut.result(timeout=600)
                synced_count += 1
            except (Exception, asyncio.CancelledError) as e:  # noqa: BLE001 - 兜底所有派发/执行异常
                logger.error(f"[自动同步] 创作者同步失败 {uid}: {e}")
                # dispatch 阶段就抛错时 worker 自身的 _handle_exception 不会跑，DB 留 RUNNING orphan，
                # 这里兜底回滚（WHERE status='RUNNING' 保护：worker 正常路径写过终态则 no-op）
                try:
                    with get_db_connection() as conn:
                        conn.execute(
                            "UPDATE task_queue SET status='FAILED', error_msg=? WHERE task_id=? AND status='RUNNING'",
                            (str(e)[:500], task_id),
                        )
                except sqlite3.Error:
                    pass

        if synced_count > 0:
            logger.info(f"[自动同步] 本轮共同步 {synced_count} 个创作者")

    scheduler.add_job(
        _auto_creator_sync,
        trigger="interval",
        minutes=30,
        id="__auto_creator_sync__",
        replace_existing=True,
        max_instances=1,
    )

def _sync_scheduler():
    """Sync jobs in DB with APScheduler"""
    for job in scheduler.get_jobs():
        if job.id not in SYSTEM_JOB_IDS:
            scheduler.remove_job(job.id)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT task_id, task_type, cron_expr, enabled FROM scheduled_tasks WHERE enabled=1")
        tasks = cursor.fetchall()

    for task in tasks:
        task_id, task_type, cron_expr, enabled = task
        if task_type == "scan_all_following":
            try:
                trigger = CronTrigger.from_crontab(cron_expr)
                scheduler.add_job(
                    _run_scan_all_following,
                    trigger=trigger,
                    id=task_id,
                    replace_existing=True
                )
            except (ValueError, TypeError) as e:
                logger.error(f"Failed to schedule task {task_id} with cron '{cron_expr}': {e}")

def startup_scheduler():
    """Called from app lifespan to sync scheduled tasks on startup."""
    if not scheduler.running:
        scheduler.start()
    _register_system_jobs()
    _sync_scheduler()

def shutdown_scheduler():
    """Called from app lifespan to shut down APScheduler."""
    if scheduler.running:
        scheduler.shutdown()

@router.get("")
def list_schedules():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT task_id, task_type, cron_expr, enabled, update_time FROM scheduled_tasks")
        tasks = []
        for row in cursor.fetchall():
            tasks.append({
                "task_id": row[0],
                "task_type": row[1],
                "cron_expr": row[2],
                "enabled": bool(row[3]),
                "update_time": row[4]
            })
    return tasks

@router.post("")
def add_schedule(req: ScheduleRequest):
    task_id = str(uuid.uuid4())
    try:
        CronTrigger.from_crontab(req.cron_expr)
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid cron expression: {e}")
    with get_db_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO scheduled_tasks (task_id, task_type, cron_expr, enabled) VALUES (?, ?, ?, ?)",
                (task_id, "scan_all_following", req.cron_expr, req.enabled)
            )
            conn.commit()
        except (sqlite3.Error, OSError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e))
    _sync_scheduler()
    return {"status": "success", "task_id": task_id}

@router.put("/{task_id}/toggle")
def toggle_schedule(task_id: str, req: ToggleRequest):
    with get_db_connection() as conn:
        try:
            if req.enabled:
                cursor = conn.execute("SELECT cron_expr FROM scheduled_tasks WHERE task_id = ?", (task_id,))
                row = cursor.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Schedule not found")
                CronTrigger.from_crontab(row[0])
            cursor = conn.execute(
                "UPDATE scheduled_tasks SET enabled = ?, update_time = CURRENT_TIMESTAMP WHERE task_id = ?",
                (req.enabled, task_id)
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Schedule not found")
            conn.commit()
        except HTTPException:
            raise
        except sqlite3.Error as e:
            raise HTTPException(status_code=400, detail=str(e))
    _sync_scheduler()
    return {"status": "success"}

@router.delete("/{task_id}")
def delete_schedule(task_id: str):
    with get_db_connection() as conn:
        try:
            cursor = conn.execute("DELETE FROM scheduled_tasks WHERE task_id = ?", (task_id,))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Schedule not found")
            conn.commit()
        except HTTPException:
            raise
        except sqlite3.Error as e:
            raise HTTPException(status_code=400, detail=str(e))
    _sync_scheduler()
    return {"status": "success"}

@router.post("/run_now")
def run_now(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_scan_all_following)
    return {"status": "success", "message": "Task triggered in background"}

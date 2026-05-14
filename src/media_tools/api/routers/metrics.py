from __future__ import annotations
"""轻量 metrics 端点：暴露任务队列、WebSocket、后台任务、DB 连接等关键指标。

不引入 Prometheus 依赖；返回 JSON 格式，方便 ops 用 curl 或简单脚本采集。
"""

import logging
import sqlite3
import time

from typing import Any

from fastapi import APIRouter

from media_tools.api.websocket_manager import manager as ws_manager
from media_tools.core import background
from media_tools.store.db import DBConnection, get_db_connection
from media_tools.scheduler.health import run_health_check

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"], redirect_slashes=False)

_KNOWN_TASK_STATUSES = ("PENDING", "RUNNING", "PAUSED", "COMPLETED", "FAILED", "PARTIAL_FAILED", "CANCELLED")
_PROCESS_START_TIME = time.monotonic()


def _collect_task_counts() -> dict[str, int]:
    counts: dict[str, int] = {s: 0 for s in _KNOWN_TASK_STATUSES}
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute("SELECT status, COUNT(*) AS c FROM task_queue GROUP BY status"):
                status = str(row["status"] or "").upper()
                if status:
                    counts[status] = counts.get(status, 0) + int(row["c"])
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"metrics: read task counts failed: {e}")
    counts["total"] = sum(v for k, v in counts.items() if k != "total")
    counts["active"] = counts.get("PENDING", 0) + counts.get("RUNNING", 0) + counts.get("PAUSED", 0)
    return counts


def _collect_account_pool_stats() -> dict:
    try:
        from media_tools.accounts.service import AccountPoolService
        from media_tools.core.config import load_pipeline_config
        config = load_pipeline_config()
        service = AccountPoolService(
            auth_state_path=None,
            default_account_id=config.pipeline_account_id,
        )
        service.resolve_accounts()
        pool = service.account_pool
        if pool is not None:
            return pool.get_stats()
    except (RuntimeError, OSError, ValueError) as e:
        logger.warning(f"metrics: collect account pool stats failed: {e}")
    return {}


def _collect_transcribe_stage_counts() -> dict[str, int]:
    stage_counts: dict[str, int] = {}
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute("SELECT stage, COUNT(*) AS c FROM transcribe_runs GROUP BY stage"):
                stage = str(row["stage"] or "unknown")
                stage_counts[stage] = int(row["c"])
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"metrics: read transcribe stage counts failed: {e}")
    return stage_counts


@router.get("")
def get_metrics():
    return {
        "uptime_seconds": int(time.monotonic() - _PROCESS_START_TIME),
        "tasks": _collect_task_counts(),
        "websocket": ws_manager.get_stats(),
        "background_tasks": {
            "active": background.active_count(),
            "total": background.total_count(),
        },
        "db_connections": DBConnection.get_stats(),
    }


@router.get("/transcribe")
def get_transcribe_metrics():
    return {
        "account_pool": _collect_account_pool_stats(),
        "transcribe_stages": _collect_transcribe_stage_counts(),
    }


@router.get("/failure-summary")
def get_failure_summary(days: int = 7):
    """转写失败原因聚合：按 (error_type, error_stage) 分桶，给运维看"为什么失败"。

    数据源是 transcribe_runs 表（每次转写尝试一行）。每次返回最近 N 天的统计。
    """
    from media_tools.transcribe.repository import TranscribeRunRepository
    days = max(1, min(days, 90))
    try:
        buckets = TranscribeRunRepository.aggregate_failures(days=days)
    except sqlite3.Error as e:
        logger.warning(f"failure_summary query failed: {e}")
        buckets = []
    return {
        "window_days": days,
        "total_failed": sum(b["count"] for b in buckets),
        "buckets": buckets,
    }


def _collect_creator_sync_status() -> dict[str, Any]:
    """创作者自动同步状态：总数、开启自动同步数、最近同步时间分布。"""
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            total = conn.execute("SELECT COUNT(*) AS c FROM creators").fetchone()["c"]
            auto_sync = conn.execute(
                "SELECT COUNT(*) AS c FROM creators WHERE auto_sync = 1"
            ).fetchone()["c"]
            stale = conn.execute(
                """SELECT COUNT(*) AS c FROM creators
                   WHERE auto_sync = 1
                   AND (last_fetch_time IS NULL
                        OR last_fetch_time < datetime('now', '-6 hours'))"""
            ).fetchone()["c"]
            return {
                "total_creators": int(total),
                "auto_sync_enabled": int(auto_sync),
                "stale_sync_count": int(stale),
            }
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"metrics: creator sync status failed: {e}")
        return {"total_creators": 0, "auto_sync_enabled": 0, "stale_sync_count": 0}


@router.get("/dashboard")
async def get_dashboard():
    """Dashboard 聚合端点：一次性返回所有观测数据。

    包括：健康检查、任务统计、转写阶段、账号池、失败汇总、额度状态、创作者同步。
    """
    health = run_health_check(sample_size=5)
    tasks_counts = _collect_task_counts()
    transcribe_stages = _collect_transcribe_stage_counts()
    account_pool = _collect_account_pool_stats()
    creator_sync = _collect_creator_sync_status()

    # failure summary (7 days)
    from media_tools.transcribe.repository import TranscribeRunRepository
    try:
        buckets = TranscribeRunRepository.aggregate_failures(days=7)
        failure_summary = {
            "window_days": 7,
            "total_failed": sum(b["count"] for b in buckets),
            "buckets": buckets,
        }
    except sqlite3.Error as e:
        logger.warning(f"dashboard: failure summary failed: {e}")
        failure_summary = {"window_days": 7, "total_failed": 0, "buckets": []}

    # quota status
    from media_tools.accounts.status import get_qwen_account_status
    try:
        quota_status = await get_qwen_account_status()
    except (RuntimeError, OSError, ValueError) as e:
        logger.warning(f"dashboard: quota status failed: {e}")
        quota_status = {"status": "unavailable", "accounts": []}

    return {
        "health": health,
        "tasks": tasks_counts,
        "transcribe_stages": transcribe_stages,
        "account_pool": account_pool,
        "failure_summary": failure_summary,
        "quota_status": quota_status,
        "creator_sync": creator_sync,
        "uptime_seconds": int(time.monotonic() - _PROCESS_START_TIME),
    }

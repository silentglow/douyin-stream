"""健康检查服务 —— 供 Dashboard API 和 CLI 脚本共用。"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from media_tools.db.core import get_db_connection

DEFAULT_SAMPLE_SIZE = 10
RUNNING_STALE_HOURS = 1
RUN_STALE_HOURS = 24


@dataclass
class CheckResult:
    name: str
    description: str
    anomaly_count: int = 0
    samples: list[dict[str, Any]] = field(default_factory=list)


def _check_completed_but_missing_file(
    conn: sqlite3.Connection, sample_size: int
) -> CheckResult:
    result = CheckResult(
        name="completed_transcript_file_missing",
        description="media_assets.transcript_status='completed' 但 transcript 文件不存在（疑似被误删）",
    )
    from media_tools.core.config import get_project_root

    transcripts_root = get_project_root() / "transcripts"
    rows = conn.execute(
        """
        SELECT asset_id, transcript_path, title
        FROM media_assets
        WHERE transcript_status = 'completed'
          AND transcript_path IS NOT NULL
          AND transcript_path != ''
        """
    ).fetchall()
    for row in rows:
        path = row["transcript_path"]
        if not path:
            continue
        full = Path(path)
        if not full.is_absolute():
            full = transcripts_root / full
        if not full.exists():
            result.anomaly_count += 1
            if len(result.samples) < sample_size:
                result.samples.append({
                    "asset_id": row["asset_id"],
                    "transcript_path": path,
                    "title": row["title"][:60] if row["title"] else None,
                })
    return result


def _check_run_saved_but_asset_not_completed(
    conn: sqlite3.Connection, sample_size: int
) -> CheckResult:
    result = CheckResult(
        name="run_saved_but_asset_status_mismatch",
        description="transcribe_runs.stage='saved' 但 media_assets.transcript_status≠'completed'（状态机断裂）",
    )
    total = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM transcribe_runs r
        LEFT JOIN media_assets m ON m.asset_id = r.asset_id
        WHERE r.stage = 'saved'
          AND (m.transcript_status IS NULL OR m.transcript_status != 'completed')
        """
    ).fetchone()["c"]
    result.anomaly_count = int(total)
    rows = conn.execute(
        """
        SELECT r.run_id, r.asset_id, r.transcript_path, m.transcript_status
        FROM transcribe_runs r
        LEFT JOIN media_assets m ON m.asset_id = r.asset_id
        WHERE r.stage = 'saved'
          AND (m.transcript_status IS NULL OR m.transcript_status != 'completed')
        LIMIT ?
        """,
        (sample_size,),
    ).fetchall()
    for row in rows:
        result.samples.append({
            "run_id": row["run_id"],
            "asset_id": row["asset_id"],
            "transcript_path": row["transcript_path"],
            "asset_transcript_status": row["transcript_status"],
        })
    return result


def _check_long_running_tasks(
    conn: sqlite3.Connection, sample_size: int
) -> CheckResult:
    result = CheckResult(
        name="task_running_too_long",
        description=f"task_queue.status='RUNNING' 持续 > {RUNNING_STALE_HOURS} 小时（孤儿任务）",
    )
    cutoff = (datetime.now() - timedelta(hours=RUNNING_STALE_HOURS)).isoformat()
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM task_queue WHERE status = 'RUNNING' AND update_time < ?",
        (cutoff,),
    ).fetchone()["c"]
    result.anomaly_count = int(total)
    rows = conn.execute(
        """
        SELECT task_id, task_type, update_time
        FROM task_queue
        WHERE status = 'RUNNING' AND update_time < ?
        ORDER BY update_time
        LIMIT ?
        """,
        (cutoff, sample_size),
    ).fetchall()
    for row in rows:
        result.samples.append({
            "task_id": row["task_id"],
            "task_type": row["task_type"],
            "update_time": row["update_time"],
        })
    return result


def _check_qwen_stuck_runs(
    conn: sqlite3.Connection, sample_size: int
) -> CheckResult:
    result = CheckResult(
        name="qwen_run_stuck",
        description=f"transcribe_runs.gen_record_id 已记录但 > {RUN_STALE_HOURS} 小时未推进 stage（Qwen 侧静默卡死）",
    )
    cutoff = (datetime.now() - timedelta(hours=RUN_STALE_HOURS)).isoformat()
    total = conn.execute(
        """
        SELECT COUNT(*) AS c FROM transcribe_runs
        WHERE gen_record_id IS NOT NULL AND gen_record_id != ''
          AND stage NOT IN ('saved', 'failed')
          AND updated_at < ?
        """,
        (cutoff,),
    ).fetchone()["c"]
    result.anomaly_count = int(total)
    rows = conn.execute(
        """
        SELECT run_id, asset_id, account_id, stage, updated_at, gen_record_id
        FROM transcribe_runs
        WHERE gen_record_id IS NOT NULL AND gen_record_id != ''
          AND stage NOT IN ('saved', 'failed')
          AND updated_at < ?
        ORDER BY updated_at
        LIMIT ?
        """,
        (cutoff, sample_size),
    ).fetchall()
    for row in rows:
        result.samples.append({
            "run_id": row["run_id"],
            "asset_id": row["asset_id"],
            "account_id": row["account_id"],
            "stage": row["stage"],
            "updated_at": row["updated_at"],
            "gen_record_id": row["gen_record_id"],
        })
    return result


def run_health_check(sample_size: int = DEFAULT_SAMPLE_SIZE) -> dict[str, Any]:
    """API 入口：返回健康检查报告 dict（不含退出码）。"""
    checks: list[CheckResult] = []
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            has_runs_table = (
                conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='transcribe_runs'"
                ).fetchone()
                is not None
            )
            checks.append(_check_completed_but_missing_file(conn, sample_size))
            if has_runs_table:
                checks.append(_check_run_saved_but_asset_not_completed(conn, sample_size))
            checks.append(_check_long_running_tasks(conn, sample_size))
            if has_runs_table:
                checks.append(_check_qwen_stuck_runs(conn, sample_size))
    except sqlite3.Error as e:
        return {
            "status": "error",
            "error": f"sqlite_error: {e}",
            "checks": [c.__dict__ for c in checks],
        }

    total_anomaly = sum(c.anomaly_count for c in checks)
    return {
        "status": "healthy" if total_anomaly == 0 else "anomaly",
        "checked_at": datetime.now().isoformat(),
        "total_anomaly_count": total_anomaly,
        "checks": [
            {
                "name": c.name,
                "description": c.description,
                "anomaly_count": c.anomaly_count,
                "samples": c.samples,
            }
            for c in checks
        ],
    }

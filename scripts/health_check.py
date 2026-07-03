#!/usr/bin/env python3
"""项目健康检查 —— Phase 4 可观测性的运维工具。

检查 4 类 DB / 文件系统一致性问题，每类问题计入异常计数：
  1. media_assets.transcript_status='completed' 但 transcript 文件实际不存在（被误删）
  2. transcribe_runs.stage='saved' 但 media_assets.transcript_status≠'completed'（状态机断裂）
  3. task_queue.status='RUNNING' 持续 > 1 小时（孤儿任务，cleanup_stale_tasks 漏了）
  4. transcribe_runs.gen_record_id 已记录但 24 小时未推进（Qwen 侧静默卡死）

输出：
  - JSON 到 stdout（含每类检查的明细）
  - 退出码 0 表示健康；1 表示至少有一类异常
  - 加 --verbose 可打印每条异常记录的标识符（受 sample_size 限制）
  - 加 --quiet 只输出退出码（不打印 JSON）

用法：
  python scripts/health_check.py
  python scripts/health_check.py --verbose
  python scripts/health_check.py --db ./data/media_tools.db --sample-size 20
  python scripts/health_check.py --db ./data/media_tools.db --transcripts-dir ./transcripts
  echo "0=healthy / 1=anomaly: $?"
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# 默认值，可被 CLI 参数覆盖
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "media_tools.db"
DEFAULT_TRANSCRIPTS_PATH = PROJECT_ROOT / "transcripts"
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
    conn: sqlite3.Connection, sample_size: int, transcripts_root: Path
) -> CheckResult:
    result = CheckResult(
        name="completed_transcript_file_missing",
        description="media_assets.transcript_status='completed' 但 transcript 文件不存在（疑似被误删）",
    )
    rows = conn.execute(
        """
        SELECT asset_id, transcript_path, title
        FROM media_assets
        WHERE transcript_status = 'completed'
          AND transcript_path IS NOT NULL
          AND transcript_path != ''
        """
    ).fetchall()
    # transcript_path 在数据库里以相对路径存储，base 是 transcripts/ 目录
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
                result.samples.append(
                    {
                        "asset_id": row["asset_id"],
                        "transcript_path": path,
                        "title": row["title"][:60] if row["title"] else None,
                    }
                )
    return result


def _check_run_saved_but_asset_not_completed(conn: sqlite3.Connection, sample_size: int) -> CheckResult:
    result = CheckResult(
        name="run_saved_but_asset_status_mismatch",
        description="transcribe_runs.stage='saved' 但 media_assets.transcript_status≠'completed'（状态机断裂）",
    )
    rows = conn.execute(
        """
        SELECT r.run_id, r.asset_id, r.transcript_path, m.transcript_status
        FROM transcribe_runs r
        LEFT JOIN media_assets m ON m.asset_id = r.asset_id
        WHERE r.stage = 'saved'
          AND (m.transcript_status IS NULL OR m.transcript_status != 'completed')
        LIMIT ?
        """,
        (sample_size + 100,),  # 多取一点以便准确计数
    ).fetchall()
    # 按 LIMIT + 100 截断，再取真总数
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
    for row in rows[:sample_size]:
        result.samples.append(
            {
                "run_id": row["run_id"],
                "asset_id": row["asset_id"],
                "transcript_path": row["transcript_path"],
                "asset_transcript_status": row["transcript_status"],
            }
        )
    return result


def _check_long_running_tasks(conn: sqlite3.Connection, sample_size: int) -> CheckResult:
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
        result.samples.append(
            {
                "task_id": row["task_id"],
                "task_type": row["task_type"],
                "update_time": row["update_time"],
            }
        )
    return result


def _check_qwen_stuck_runs(conn: sqlite3.Connection, sample_size: int) -> CheckResult:
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
        result.samples.append(
            {
                "run_id": row["run_id"],
                "asset_id": row["asset_id"],
                "account_id": row["account_id"],
                "stage": row["stage"],
                "updated_at": row["updated_at"],
                "gen_record_id": row["gen_record_id"],
            }
        )
    return result


def run_health_check(db_path: Path, sample_size: int, transcripts_root: Path) -> tuple[dict[str, Any], int]:
    """主入口：返回 (报告 dict, 退出码)。"""
    if not db_path.exists():
        return (
            {
                "status": "error",
                "error": f"db_not_found: {db_path}",
                "checks": [],
            },
            1,
        )

    checks: list[CheckResult] = []
    try:
        conn = sqlite3.connect(str(db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            # transcribe_runs 表可能不存在（旧 DB）—— 这种情况下跳过涉及它的检查
            has_runs_table = (
                conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transcribe_runs'").fetchone()
                is not None
            )
            checks.append(_check_completed_but_missing_file(conn, sample_size, transcripts_root))
            if has_runs_table:
                checks.append(_check_run_saved_but_asset_not_completed(conn, sample_size))
            checks.append(_check_long_running_tasks(conn, sample_size))
            if has_runs_table:
                checks.append(_check_qwen_stuck_runs(conn, sample_size))
        finally:
            conn.close()
    except sqlite3.Error as e:
        return (
            {
                "status": "error",
                "error": f"sqlite_error: {e}",
                "checks": [c.__dict__ for c in checks],
            },
            1,
        )

    total_anomaly = sum(c.anomaly_count for c in checks)
    overall_status = "healthy" if total_anomaly == 0 else "anomaly"
    return (
        {
            "status": overall_status,
            "checked_at": datetime.now().isoformat(),
            "db_path": str(db_path),
            "transcripts_root": str(transcripts_root),
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
        },
        0 if total_anomaly == 0 else 1,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Media Tools 项目健康检查（DB / 文件系统一致性扫描）")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite DB 路径（默认 {DEFAULT_DB_PATH}）",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help=f"每类检查打印的样本数上限（默认 {DEFAULT_SAMPLE_SIZE}）",
    )
    parser.add_argument(
        "--transcripts-dir",
        type=Path,
        default=DEFAULT_TRANSCRIPTS_PATH,
        help=f"transcript_path 相对路径的根目录（默认 {DEFAULT_TRANSCRIPTS_PATH}）",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="不打印 JSON 报告，只用退出码反馈结果",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="打印更详细的 sample（不裁剪长字段）",
    )
    args = parser.parse_args()

    report, exit_code = run_health_check(args.db, args.sample_size, args.transcripts_dir)
    if not args.quiet:
        print(json.dumps(report, ensure_ascii=False, indent=2 if args.verbose else None))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

"""scripts/health_check.py 单元测试。

每个检查项独立测试，验证：
  - 健康场景下 anomaly_count == 0
  - 异常场景下能检出 + samples 有内容
  - 退出码：0=healthy / 1=anomaly
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "health_check.py"


def _create_test_db(db_path: Path) -> None:
    """复刻 db/core.py 创建关键表（裁剪版，足够给 health_check 用）"""
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE media_assets (
            asset_id TEXT PRIMARY KEY,
            title TEXT,
            transcript_path TEXT,
            transcript_status TEXT DEFAULT 'none',
            update_time DATETIME
        );
        CREATE TABLE task_queue (
            task_id TEXT PRIMARY KEY,
            task_type TEXT,
            status TEXT DEFAULT 'PENDING',
            update_time DATETIME
        );
        CREATE TABLE transcribe_runs (
            run_id TEXT PRIMARY KEY,
            asset_id TEXT,
            video_path TEXT,
            account_id TEXT,
            stage TEXT,
            gen_record_id TEXT,
            transcript_path TEXT,
            updated_at DATETIME
        );
    """)
    conn.commit()
    conn.close()


def _run_script(db_path: Path) -> tuple[dict, int]:
    """调脚本返回 (报告 dict, exit code)"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--db", str(db_path)],
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout) if result.stdout.strip() else {}
    return report, result.returncode


def test_healthy_db_returns_zero(tmp_path):
    db = tmp_path / "test.db"
    _create_test_db(db)
    report, code = _run_script(db)
    assert code == 0
    assert report["status"] == "healthy"
    assert report["total_anomaly_count"] == 0


def test_completed_but_missing_file_detected(tmp_path):
    db = tmp_path / "test.db"
    _create_test_db(db)
    # transcripts 目录里**没有**这个文件
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO media_assets (asset_id, title, transcript_path, transcript_status) "
        "VALUES ('a-1', 'Test', 'creator-x/missing.md', 'completed')"
    )
    conn.commit()
    conn.close()

    report, code = _run_script(db)
    assert code == 1
    bucket = next(c for c in report["checks"] if c["name"] == "completed_transcript_file_missing")
    assert bucket["anomaly_count"] == 1
    assert bucket["samples"][0]["asset_id"] == "a-1"


def test_run_saved_but_asset_not_completed_detected(tmp_path):
    db = tmp_path / "test.db"
    _create_test_db(db)
    conn = sqlite3.connect(str(db))
    # asset 状态是 pending；run 已经 saved —— 状态机断裂
    conn.execute(
        "INSERT INTO media_assets (asset_id, title, transcript_path, transcript_status) "
        "VALUES ('a-2', 'Test', '', 'pending')"
    )
    conn.execute(
        "INSERT INTO transcribe_runs (run_id, asset_id, video_path, account_id, stage, updated_at) "
        "VALUES ('r-1', 'a-2', '/v.mp4', 'acc', 'saved', ?)",
        (datetime.now().isoformat(),),
    )
    conn.commit()
    conn.close()

    report, code = _run_script(db)
    assert code == 1
    bucket = next(c for c in report["checks"] if c["name"] == "run_saved_but_asset_status_mismatch")
    assert bucket["anomaly_count"] == 1


def test_long_running_task_detected(tmp_path):
    db = tmp_path / "test.db"
    _create_test_db(db)
    conn = sqlite3.connect(str(db))
    stale = (datetime.now() - timedelta(hours=2)).isoformat()
    conn.execute(
        "INSERT INTO task_queue (task_id, task_type, status, update_time) VALUES ('t-stale', 'pipeline', 'RUNNING', ?)",
        (stale,),
    )
    fresh = (datetime.now() - timedelta(minutes=10)).isoformat()
    conn.execute(
        "INSERT INTO task_queue (task_id, task_type, status, update_time) VALUES ('t-fresh', 'pipeline', 'RUNNING', ?)",
        (fresh,),
    )
    conn.commit()
    conn.close()

    report, code = _run_script(db)
    assert code == 1
    bucket = next(c for c in report["checks"] if c["name"] == "task_running_too_long")
    # 2 小时前的算异常，10 分钟前的不算
    assert bucket["anomaly_count"] == 1
    assert bucket["samples"][0]["task_id"] == "t-stale"


def test_qwen_stuck_run_detected(tmp_path):
    db = tmp_path / "test.db"
    _create_test_db(db)
    conn = sqlite3.connect(str(db))
    stale = (datetime.now() - timedelta(hours=30)).isoformat()
    # 卡死的 run：gen_record_id 已记录，stage 还是 transcribing，30 小时没动
    conn.execute(
        "INSERT INTO transcribe_runs (run_id, asset_id, video_path, account_id, stage, gen_record_id, updated_at) "
        "VALUES ('r-stuck', 'a-1', '/v.mp4', 'acc', 'transcribing', 'gen-xyz', ?)",
        (stale,),
    )
    # 健康对照：刚刚才更新的，不算
    fresh = (datetime.now() - timedelta(hours=2)).isoformat()
    conn.execute(
        "INSERT INTO transcribe_runs (run_id, asset_id, video_path, account_id, stage, gen_record_id, updated_at) "
        "VALUES ('r-fresh', 'a-2', '/v.mp4', 'acc', 'transcribing', 'gen-abc', ?)",
        (fresh,),
    )
    # 已完成的不算（终态被跳过）
    conn.execute(
        "INSERT INTO transcribe_runs (run_id, asset_id, video_path, account_id, stage, gen_record_id, updated_at) "
        "VALUES ('r-saved', 'a-3', '/v.mp4', 'acc', 'saved', 'gen-old', ?)",
        (stale,),
    )
    conn.commit()
    conn.close()

    report, code = _run_script(db)
    assert code == 1
    bucket = next(c for c in report["checks"] if c["name"] == "qwen_run_stuck")
    assert bucket["anomaly_count"] == 1
    assert bucket["samples"][0]["run_id"] == "r-stuck"


def test_missing_db_returns_error(tmp_path):
    db = tmp_path / "does_not_exist.db"
    report, code = _run_script(db)
    assert code == 1
    assert report["status"] == "error"
    assert "db_not_found" in report["error"]


def test_quiet_mode_suppresses_output(tmp_path):
    db = tmp_path / "test.db"
    _create_test_db(db)
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--db", str(db), "--quiet"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_old_db_without_transcribe_runs_table_skips_those_checks(tmp_path):
    """老版本 DB 没有 transcribe_runs 表时不应崩溃，跳过涉及它的检查。"""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE media_assets (
            asset_id TEXT PRIMARY KEY,
            title TEXT,
            transcript_path TEXT,
            transcript_status TEXT,
            update_time DATETIME
        );
        CREATE TABLE task_queue (
            task_id TEXT PRIMARY KEY,
            task_type TEXT,
            status TEXT,
            update_time DATETIME
        );
    """)
    conn.commit()
    conn.close()

    report, code = _run_script(db)
    # 没异常时退出 0；只跑了 2 项检查
    check_names = {c["name"] for c in report["checks"]}
    assert "completed_transcript_file_missing" in check_names
    assert "task_running_too_long" in check_names
    assert "run_saved_but_asset_status_mismatch" not in check_names
    assert "qwen_run_stuck" not in check_names
    assert code == 0

"""TranscribeRunRepository.aggregate_failures 单元测试。

覆盖：
- 无失败时返回空列表
- 单桶聚合（同 error_type+error_stage 多次失败）
- 多桶按 count 倒序、再按 last_seen 倒序
- 时间窗口过滤（days 参数）
- sample_error 取桶内最新一条错误信息（截断到 200 字）
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from media_tools.store import db as db_core
from media_tools.transcribe.repository import TranscribeRunRepository


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("media_tools.common.paths.get_db_path", lambda: db_path)
    db_core.reset_db_cache()
    db_core._db_path = None
    db_core.init_db(db_path)
    yield db_path
    db_core.reset_db_cache()
    db_core._db_path = None


def _insert_failed_run(
    *,
    run_id: str,
    error_type: str,
    error_stage: str,
    last_error: str = "boom",
    days_ago: int = 0,
) -> None:
    ts = (datetime.now() - timedelta(days=days_ago)).isoformat()
    with db_core.get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO transcribe_runs
                (run_id, asset_id, video_path, account_id, task_id, stage,
                 error_type, error_stage, last_error, created_at, updated_at)
            VALUES (?, 'a-1', '/v.mp4', 'acc-1', 't-1', 'failed', ?, ?, ?, ?, ?)
            """,
            (run_id, error_type, error_stage, last_error, ts, ts),
        )


def test_aggregate_failures_returns_empty_when_no_failures(tmp_db):
    assert TranscribeRunRepository.aggregate_failures(days=7) == []


def test_aggregate_failures_buckets_by_error_type_and_stage(tmp_db):
    _insert_failed_run(run_id="r1", error_type="quota", error_stage="transcribing")
    _insert_failed_run(run_id="r2", error_type="quota", error_stage="transcribing")
    _insert_failed_run(run_id="r3", error_type="network", error_stage="uploading")

    buckets = TranscribeRunRepository.aggregate_failures(days=7)

    assert len(buckets) == 2
    quota_bucket = next(b for b in buckets if b["error_type"] == "quota")
    network_bucket = next(b for b in buckets if b["error_type"] == "network")
    assert quota_bucket["count"] == 2
    assert quota_bucket["error_stage"] == "transcribing"
    assert network_bucket["count"] == 1
    assert network_bucket["error_stage"] == "uploading"


def test_aggregate_failures_orders_by_count_desc(tmp_db):
    # 3 个 network failures、1 个 quota failure
    for i in range(3):
        _insert_failed_run(run_id=f"net{i}", error_type="network", error_stage="upload")
    _insert_failed_run(run_id="q1", error_type="quota", error_stage="transcribing")

    buckets = TranscribeRunRepository.aggregate_failures(days=7)
    assert buckets[0]["error_type"] == "network"
    assert buckets[0]["count"] == 3
    assert buckets[1]["error_type"] == "quota"
    assert buckets[1]["count"] == 1


def test_aggregate_failures_window_filters_old_records(tmp_db):
    _insert_failed_run(run_id="recent", error_type="quota", error_stage="transcribing", days_ago=2)
    _insert_failed_run(run_id="old", error_type="quota", error_stage="transcribing", days_ago=30)

    buckets = TranscribeRunRepository.aggregate_failures(days=7)
    # 只应聚合到 1 条（recent），old 落在 30 天前超出 7 天窗口
    assert len(buckets) == 1
    assert buckets[0]["count"] == 1


def test_aggregate_failures_sample_error_is_latest_within_bucket(tmp_db):
    _insert_failed_run(
        run_id="r-old", error_type="auth", error_stage="upload",
        last_error="OLD ERROR MESSAGE", days_ago=3,
    )
    _insert_failed_run(
        run_id="r-new", error_type="auth", error_stage="upload",
        last_error="LATEST ERROR MESSAGE", days_ago=1,
    )

    buckets = TranscribeRunRepository.aggregate_failures(days=7)
    assert len(buckets) == 1
    assert buckets[0]["count"] == 2
    assert buckets[0]["sample_error"] == "LATEST ERROR MESSAGE"


def test_aggregate_failures_truncates_sample_error_to_200_chars(tmp_db):
    long_error = "x" * 500
    _insert_failed_run(run_id="r1", error_type="unknown", error_stage="unknown", last_error=long_error)

    buckets = TranscribeRunRepository.aggregate_failures(days=7)
    assert len(buckets[0]["sample_error"]) == 200


def test_aggregate_failures_handles_null_error_fields(tmp_db):
    """error_type / error_stage 都是 NULL 时被归到 'unknown' 桶"""
    ts = datetime.now().isoformat()
    with db_core.get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO transcribe_runs
                (run_id, asset_id, video_path, account_id, stage, created_at, updated_at)
            VALUES ('r-null', 'a-1', '/v.mp4', 'acc-1', 'failed', ?, ?)
            """,
            (ts, ts),
        )

    buckets = TranscribeRunRepository.aggregate_failures(days=7)
    assert len(buckets) == 1
    assert buckets[0]["error_type"] == "unknown"
    assert buckets[0]["error_stage"] == "unknown"

"""MediaAssetService 的 round-trip 测试。

覆盖：mark_downloaded（INSERT/UPDATE 语义）、mark_transcribe_running、
mark_transcribe_failed（aweme 路径 + 通用 LIKE 路径）、mark_transcribe_completed
（清错）、find_pending_to_transcribe 各种过滤组合。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest


def _build_in_memory_db() -> sqlite3.Connection:
    """构造一个最小的 media_assets 表，列覆盖 service 用到的全部字段。"""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE media_assets (
            asset_id TEXT PRIMARY KEY,
            creator_uid TEXT,
            source_url TEXT,
            title TEXT,
            duration INTEGER,
            video_path TEXT,
            video_status TEXT DEFAULT 'pending',
            transcript_path TEXT,
            transcript_status TEXT DEFAULT 'none',
            transcript_preview TEXT,
            transcript_text TEXT,
            transcript_last_error TEXT,
            transcript_error_type TEXT,
            transcript_retry_count INTEGER DEFAULT 0,
            transcript_failed_at DATETIME,
            last_task_id TEXT,
            source_platform TEXT,
            folder_path TEXT,
            is_read INTEGER DEFAULT 0,
            is_starred INTEGER DEFAULT 0,
            create_time DATETIME,
            update_time DATETIME
        )
        """
    )
    conn.commit()
    return conn


@pytest.fixture
def db():
    conn = _build_in_memory_db()
    with (
        patch("media_tools.assets.service.get_db_connection", return_value=conn),
        patch("media_tools.assets.service.update_fts_for_asset", return_value=None),
    ):
        yield conn
    conn.close()


def _row(conn: sqlite3.Connection, asset_id: str) -> dict:
    row = conn.execute("SELECT * FROM media_assets WHERE asset_id = ?", (asset_id,)).fetchone()
    return dict(row) if row else {}


def test_mark_downloaded_inserts_then_updates(db: sqlite3.Connection) -> None:
    from media_tools.assets.service import MediaAssetService

    MediaAssetService.mark_downloaded(
        asset_id="a1",
        creator_uid="u1",
        title="hello",
        video_path="creators/x/a1.mp4",
        source_platform="bilibili",
        source_url="https://example.com/a1",
        folder_path="x",
        duration=42,
    )
    row = _row(db, "a1")
    assert row["video_status"] == "downloaded"
    assert row["source_platform"] == "bilibili"
    assert row["video_path"] == "creators/x/a1.mp4"
    assert row["transcript_status"] == "pending"

    # 重复调用：path 改变 -> UPDATE 生效；title 不会被覆盖
    MediaAssetService.mark_downloaded(
        asset_id="a1",
        creator_uid="u1",
        title="ignored-on-update",
        video_path="creators/x/a1_v2.mp4",
        source_platform="bilibili",
    )
    row = _row(db, "a1")
    assert row["video_path"] == "creators/x/a1_v2.mp4"
    assert row["title"] == "hello"


def test_mark_transcribe_failed_aweme_path(db: sqlite3.Connection) -> None:
    from media_tools.assets.service import MediaAssetService

    db.execute(
        "INSERT INTO media_assets (asset_id, creator_uid, title, video_path, video_status, transcript_status, create_time, update_time) "
        "VALUES (?, ?, ?, ?, 'downloaded', 'pending', '2025', '2025')",
        ("123456789012345", "u1", "vid", "x/123456789012345.mp4"),
    )
    db.commit()

    MediaAssetService.mark_transcribe_failed(
        video_path=Path("x/123456789012345.mp4"),
        error_type="auth",
        error_message="Token expired",
        task_id="task-A",
    )
    row = _row(db, "123456789012345")
    assert row["transcript_status"] == "failed"
    assert row["transcript_error_type"] == "auth"
    assert row["transcript_last_error"] == "Token expired"
    assert row["transcript_retry_count"] == 1
    assert row["last_task_id"] == "task-A"

    # 第二次失败：retry_count 累加，task_id 仍可被新值覆盖
    MediaAssetService.mark_transcribe_failed(
        video_path=Path("x/123456789012345.mp4"),
        error_type="network",
        error_message="reset",
        task_id="task-B",
    )
    row = _row(db, "123456789012345")
    assert row["transcript_retry_count"] == 2
    assert row["transcript_error_type"] == "network"
    assert row["last_task_id"] == "task-B"


def test_mark_transcribe_failed_like_path_for_local_files(db: sqlite3.Connection) -> None:
    from media_tools.assets.service import MediaAssetService

    db.execute(
        "INSERT INTO media_assets (asset_id, creator_uid, title, video_path, video_status, transcript_status, create_time, update_time) "
        "VALUES (?, ?, ?, ?, 'downloaded', 'pending', '2025', '2025')",
        ("local:abc", "local:upload", "MyClip", "/tmp/MyClip.mp4"),
    )
    db.commit()

    MediaAssetService.mark_transcribe_failed(
        video_path=Path("/tmp/MyClip.mp4"),
        error_type="quota",
        error_message="rate limited",
    )
    row = _row(db, "local:abc")
    assert row["transcript_status"] == "failed"
    assert row["transcript_error_type"] == "quota"


def test_mark_transcribe_completed_clears_errors(db: sqlite3.Connection, tmp_path: Path) -> None:
    from media_tools.assets.service import MediaAssetService

    db.execute(
        """
        INSERT INTO media_assets (asset_id, creator_uid, title, video_path, video_status,
            transcript_status, transcript_last_error, transcript_error_type,
            transcript_retry_count, transcript_failed_at, create_time, update_time)
        VALUES (?, ?, ?, ?, 'downloaded', 'failed', 'old err', 'auth', 3, '2025', '2025', '2025')
        """,
        ("123456789012345", "u1", "v", "x/123456789012345.mp4"),
    )
    db.commit()

    MediaAssetService.mark_transcribe_completed(
        video_path=Path("x/123456789012345.mp4"),
        transcript_path=tmp_path / "out.txt",
        output_dir=tmp_path,
        preview="hi",
        full_text="hello world",
    )
    row = _row(db, "123456789012345")
    assert row["transcript_status"] == "completed"
    assert row["transcript_last_error"] is None
    assert row["transcript_error_type"] is None
    assert row["transcript_failed_at"] is None
    # retry_count 不被成功路径清零（保留历史可观测性）
    assert row["transcript_retry_count"] == 3


def test_find_pending_to_transcribe_filters(db: sqlite3.Connection) -> None:
    from media_tools.assets.service import MediaAssetService

    seed = [
        # asset_id, creator, status, error_type, platform
        ("c1", "u1", "completed", None, "douyin"),
        ("p1", "u1", "pending", None, "douyin"),
        ("n1", "u1", "none", None, "douyin"),
        ("f1", "u1", "failed", "auth", "douyin"),
        ("f2", "u2", "failed", "quota", "bilibili"),
        ("f3", "u1", "failed", "auth", "bilibili"),
    ]
    for aid, uid, st, et, plat in seed:
        db.execute(
            "INSERT INTO media_assets (asset_id, creator_uid, title, video_path, video_status, "
            "transcript_status, transcript_error_type, source_platform, create_time, update_time) "
            "VALUES (?, ?, ?, ?, 'downloaded', ?, ?, ?, '2025', '2025')",
            (aid, uid, aid, f"{aid}.mp4", st, et, plat),
        )
    db.commit()

    only_failed = MediaAssetService.find_pending_to_transcribe(only_failed=True)
    assert sorted(r["asset_id"] for r in only_failed) == ["f1", "f2", "f3"]

    auth_only = MediaAssetService.find_pending_to_transcribe(only_failed=True, error_types=["auth"])
    assert sorted(r["asset_id"] for r in auth_only) == ["f1", "f3"]

    bilibili_failed = MediaAssetService.find_pending_to_transcribe(only_failed=True, platform="bilibili")
    assert sorted(r["asset_id"] for r in bilibili_failed) == ["f2", "f3"]

    u1_failed = MediaAssetService.find_pending_to_transcribe(only_failed=True, creator_uid="u1")
    assert sorted(r["asset_id"] for r in u1_failed) == ["f1", "f3"]

    # not only_failed 时也包含 pending / none
    all_pending = MediaAssetService.find_pending_to_transcribe(only_failed=False, creator_uid="u1")
    assert sorted(r["asset_id"] for r in all_pending) == ["f1", "f3", "n1", "p1"]

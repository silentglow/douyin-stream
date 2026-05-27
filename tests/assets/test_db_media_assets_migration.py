"""media_assets 第二阶段迁移测试。

老库（缺新列）启动一次 init_db 后，新增的 6 列必须全部到位，且老数据保留、
默认值生效（transcript_retry_count = 0）。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from media_tools.store.db import init_db


_NEW_COLUMNS = {
    "transcript_last_error",
    "transcript_error_type",
    "transcript_retry_count",
    "transcript_failed_at",
    "last_task_id",
    "source_platform",
}


def _legacy_schema(conn: sqlite3.Connection) -> None:
    """模拟第二阶段之前的旧库：只有最早期的核心字段。"""
    conn.execute(
        """
        CREATE TABLE media_assets (
            asset_id TEXT PRIMARY KEY,
            creator_uid TEXT,
            title TEXT,
            video_status TEXT DEFAULT 'pending',
            transcript_status TEXT DEFAULT 'none',
            create_time DATETIME,
            update_time DATETIME
        )
        """
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_fresh_db_has_all_new_columns(tmp_path: Path) -> None:
    db = tmp_path / "fresh.db"
    init_db(str(db))
    with sqlite3.connect(db) as conn:
        cols = _columns(conn, "media_assets")
    assert _NEW_COLUMNS.issubset(cols), f"missing: {_NEW_COLUMNS - cols}"


def test_legacy_db_upgrades_in_place_and_preserves_data(tmp_path: Path) -> None:
    db = tmp_path / "legacy.db"
    with sqlite3.connect(db) as conn:
        _legacy_schema(conn)
        conn.execute(
            "INSERT INTO media_assets(asset_id, creator_uid, title) VALUES ('old1','u1','existing')"
        )
        conn.commit()

    init_db(str(db))

    with sqlite3.connect(db) as conn:
        cols = _columns(conn, "media_assets")
        assert _NEW_COLUMNS.issubset(cols), f"missing: {_NEW_COLUMNS - cols}"

        row = conn.execute(
            "SELECT title, transcript_retry_count, transcript_last_error, source_platform "
            "FROM media_assets WHERE asset_id = 'old1'"
        ).fetchone()

    assert row is not None
    title, retry_count, last_err, platform = row
    assert title == "existing"
    assert retry_count == 0
    assert last_err is None
    assert platform is None


def test_init_db_idempotent(tmp_path: Path) -> None:
    """重复 init_db 不应抛错也不应丢列。"""
    db = tmp_path / "idem.db"
    init_db(str(db))
    init_db(str(db))
    init_db(str(db))
    with sqlite3.connect(db) as conn:
        cols = _columns(conn, "media_assets")
    assert _NEW_COLUMNS.issubset(cols)

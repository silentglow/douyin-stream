from __future__ import annotations

import contextlib
import sqlite3
from unittest.mock import patch

import pytest

from media_tools.creators.sync import CreatorSyncWorker


def _seed_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE creators (
          uid TEXT PRIMARY KEY,
          sec_user_id TEXT,
          nickname TEXT,
          avatar TEXT,
          platform TEXT,
          sync_status TEXT,
          last_fetch_time DATETIME
        );
        """
    )
    conn.execute(
        "INSERT INTO creators (uid, sec_user_id, nickname, avatar, platform) "
        "VALUES ('bilibili:99','99','UP','https://old/b.jpg','bilibili')"
    )
    conn.execute(
        "INSERT INTO creators (uid, sec_user_id, nickname, avatar, platform) "
        "VALUES ('youtube:UCx','UCx','Chan','https://old/y.jpg','youtube')"
    )
    conn.execute(
        "INSERT INTO creators (uid, sec_user_id, nickname, avatar, platform) "
        "VALUES ('dy1','MS4wABC','抖音号','https://old/d.jpg','douyin')"
    )
    conn.commit()
    return conn


def _patch_db(conn: sqlite3.Connection):
    @contextlib.contextmanager
    def fake_conn():
        yield conn

    return patch("media_tools.creators.sync.get_db_connection", fake_conn)


def _avatar(conn: sqlite3.Connection, uid: str) -> str | None:
    return conn.execute("SELECT avatar FROM creators WHERE uid = ?", (uid,)).fetchone()[0]


@pytest.mark.asyncio
async def test_refresh_avatar_bilibili_updates_url() -> None:
    conn = _seed_conn()
    worker = CreatorSyncWorker()
    with (
        _patch_db(conn),
        patch(
            "media_tools.bilibili.nickname.fetch_bilibili_profile",
            return_value={"nickname": "UP", "avatar": "https://new/b.jpg"},
        ),
    ):
        await worker._refresh_avatar("bilibili", "bilibili:99", "99")
    assert _avatar(conn, "bilibili:99") == "https://new/b.jpg"


@pytest.mark.asyncio
async def test_refresh_avatar_youtube_updates_url() -> None:
    conn = _seed_conn()
    worker = CreatorSyncWorker()
    with (
        _patch_db(conn),
        patch(
            "media_tools.platform.youtube.fetch_youtube_channel_info",
            return_value={"nickname": "Chan", "channel_id": "UCx", "avatar": "https://new/y.jpg"},
        ),
    ):
        await worker._refresh_avatar("youtube", "youtube:UCx", "UCx")
    assert _avatar(conn, "youtube:UCx") == "https://new/y.jpg"


@pytest.mark.asyncio
async def test_refresh_avatar_douyin_updates_url() -> None:
    conn = _seed_conn()
    worker = CreatorSyncWorker()
    with (
        _patch_db(conn),
        patch(
            "media_tools.douyin.core.following_mgr._fetch_user_info_via_f2",
            return_value={"avatar_url": "https://new/d.jpg"},
        ),
    ):
        await worker._refresh_avatar("douyin", "dy1", "MS4wABC")
    assert _avatar(conn, "dy1") == "https://new/d.jpg"


@pytest.mark.asyncio
async def test_refresh_avatar_empty_does_not_clobber() -> None:
    conn = _seed_conn()
    worker = CreatorSyncWorker()
    with (
        _patch_db(conn),
        patch(
            "media_tools.bilibili.nickname.fetch_bilibili_profile",
            return_value={"nickname": "UP", "avatar": ""},
        ),
    ):
        await worker._refresh_avatar("bilibili", "bilibili:99", "99")
    assert _avatar(conn, "bilibili:99") == "https://old/b.jpg"


@pytest.mark.asyncio
async def test_refresh_avatar_fetch_error_is_swallowed() -> None:
    conn = _seed_conn()
    worker = CreatorSyncWorker()
    with (
        _patch_db(conn),
        patch(
            "media_tools.bilibili.nickname.fetch_bilibili_profile",
            side_effect=RuntimeError("boom"),
        ),
    ):
        # must not raise
        await worker._refresh_avatar("bilibili", "bilibili:99", "99")
    assert _avatar(conn, "bilibili:99") == "https://old/b.jpg"


@pytest.mark.asyncio
async def test_refresh_avatar_douyin_without_sec_user_id_noops() -> None:
    conn = _seed_conn()
    worker = CreatorSyncWorker()
    with _patch_db(conn):
        # no sec_user_id → early return, no fetch, no crash
        await worker._refresh_avatar("douyin", "dy1", "")
    assert _avatar(conn, "dy1") == "https://old/d.jpg"

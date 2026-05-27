from __future__ import annotations


def test_qwen_account_status_does_not_mark_invalid_when_snapshot_fails(monkeypatch) -> None:
    import sqlite3
    import asyncio

    from media_tools.accounts import status as qwen_status

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE Accounts_Pool(account_id TEXT PRIMARY KEY, platform TEXT, cookie_data TEXT, remark TEXT, status TEXT DEFAULT 'active', auth_state_path TEXT DEFAULT '')"
    )
    conn.execute(
        "INSERT INTO Accounts_Pool(account_id, platform, cookie_data, remark, status, auth_state_path) VALUES(?,?,?,?,?,?)",
        ("a1", "qwen", "", "r", "active", "data/auth/qwen-storage-state-a1.json"),
    )
    conn.commit()

    monkeypatch.setattr("media_tools.accounts.status.get_db_connection", lambda: conn)

    async def _fail_snapshot(*args, **kwargs):  # noqa: ANN001,ARG001
        raise RuntimeError("connection reset by peer")

    monkeypatch.setattr("media_tools.accounts.status.get_quota_snapshot", _fail_snapshot)

    result = asyncio.run(qwen_status.get_qwen_account_status())
    assert result["status"] == "success"
    assert result["accounts"][0]["status"] == "active"
    assert result["accounts"][0]["remaining_hours"] == 0

    row = conn.execute("SELECT status FROM Accounts_Pool WHERE account_id='a1'").fetchone()
    assert row is not None
    assert row[0] == "active"

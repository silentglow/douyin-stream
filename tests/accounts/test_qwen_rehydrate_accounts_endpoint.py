from __future__ import annotations


def test_rehydrate_qwen_accounts_updates_auth_state_paths(monkeypatch) -> None:
    import sqlite3
    from media_tools.api.routers import settings as settings_router

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE Accounts_Pool(account_id TEXT PRIMARY KEY, platform TEXT, cookie_data TEXT, remark TEXT, status TEXT DEFAULT 'active', auth_state_path TEXT DEFAULT '')"
    )
    conn.execute(
        "INSERT INTO Accounts_Pool(account_id, platform, cookie_data, remark, status, auth_state_path) VALUES(?,?,?,?,?,?)",
        ("a1", "qwen", "x=y", "r", "active", ""),
    )
    conn.execute(
        "INSERT INTO Accounts_Pool(account_id, platform, cookie_data, remark, status, auth_state_path) VALUES(?,?,?,?,?,?)",
        ("a2", "qwen", "", "r", "active", ""),
    )
    conn.commit()
    monkeypatch.setattr("media_tools.accounts.repository.get_db_connection", lambda: conn)

    called: list[tuple[str, str]] = []

    def _fake_save(cookie_string: str, auth_state_path, **kwargs):  # noqa: ANN001
        called.append((cookie_string, str(auth_state_path)))
        return {}

    monkeypatch.setattr("media_tools.api.routers.settings.save_qwen_cookie_string", _fake_save)

    result = settings_router.rehydrate_qwen_accounts()
    assert result["status"] == "success"
    assert result["updated"] == 1
    assert result["skipped"] == 1
    assert result["failed"] == 0
    assert len(called) == 1

    row = conn.execute("SELECT auth_state_path FROM Accounts_Pool WHERE account_id='a1'").fetchone()
    assert row is not None
    assert str(row["auth_state_path"]).strip()


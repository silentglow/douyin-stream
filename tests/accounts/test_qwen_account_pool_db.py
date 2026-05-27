from __future__ import annotations

import sqlite3


def test_db_init_adds_accounts_pool_auth_state_path(tmp_path) -> None:
    from media_tools.store.db import init_db

    db_path = tmp_path / "t.db"
    init_db(str(db_path))

    conn = sqlite3.connect(str(db_path))
    cols = [row[1] for row in conn.execute("PRAGMA table_info(Accounts_Pool)").fetchall()]
    assert "auth_state_path" in cols


def test_build_qwen_auth_state_path_for_account() -> None:
    from media_tools.transcribe.db_account_pool import build_qwen_auth_state_path_for_account

    p = build_qwen_auth_state_path_for_account("abc123")
    assert p.name == "qwen-storage-state-abc123.json"


def test_add_qwen_account_sets_auth_state_path(monkeypatch) -> None:
    import sqlite3
    import asyncio
    from media_tools.api.routers import settings as settings_router

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE Accounts_Pool(account_id TEXT PRIMARY KEY, platform TEXT, cookie_data TEXT, remark TEXT, status TEXT DEFAULT 'active', auth_state_path TEXT DEFAULT '')"
    )
    conn.commit()
    monkeypatch.setattr("media_tools.accounts.repository.get_db_connection", lambda: conn)
    monkeypatch.setattr("media_tools.accounts.repository.get_db_connection", lambda: conn)

    called = {}

    def _fake_save(cookie_string: str, auth_state_path, **kwargs):  # noqa: ANN001
        called["auth_state_path"] = str(auth_state_path)
        return {}

    monkeypatch.setattr("media_tools.api.routers.settings.save_qwen_cookie_string", _fake_save)

    async def _fake_get_snapshot(*, auth_state_path, account_id="", **kwargs):  # noqa: ANN001
        class _S:
            remaining_upload = 60 * 375
            used_upload = 0
            total_upload = 0
            raw = {}
            gratis_upload = False
            free = True

        return _S()

    monkeypatch.setattr("media_tools.api.routers.settings.get_quota_snapshot", _fake_get_snapshot)

    req = settings_router.QwenAccountRequest(cookie_string="tongyi_sso_ticket=abcdefghijklmnopqrstuvwxyz1234567890", remark="r")
    result = asyncio.run(settings_router.add_qwen_account(req))
    account_id = result["account_id"]
    row = conn.execute("SELECT auth_state_path FROM Accounts_Pool WHERE account_id=?", (account_id,)).fetchone()
    assert row is not None
    assert row[0]
    assert "qwen-storage-state-" in row[0]
    assert called["auth_state_path"] == row[0]


def test_add_qwen_account_returns_validation_ok_when_snapshot_succeeds(monkeypatch) -> None:
    import sqlite3
    import asyncio
    from media_tools.api.routers import settings as settings_router

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE Accounts_Pool(account_id TEXT PRIMARY KEY, platform TEXT, cookie_data TEXT, remark TEXT, status TEXT DEFAULT 'active', auth_state_path TEXT DEFAULT '')"
    )
    conn.commit()
    monkeypatch.setattr("media_tools.accounts.repository.get_db_connection", lambda: conn)

    monkeypatch.setattr("media_tools.api.routers.settings.save_qwen_cookie_string", lambda *args, **kwargs: {})  # noqa: ARG005

    async def _fake_get_snapshot(*, auth_state_path, account_id="", **kwargs):  # noqa: ANN001
        class _S:
            remaining_upload = 60 * 10
            used_upload = 0
            total_upload = 0
            raw = {}
            gratis_upload = False
            free = True

        return _S()

    monkeypatch.setattr("media_tools.api.routers.settings.get_quota_snapshot", _fake_get_snapshot)

    req = settings_router.QwenAccountRequest(cookie_string="tongyi_sso_ticket=abcdefghijklmnopqrstuvwxyz1234567890", remark="r")
    result = asyncio.run(settings_router.add_qwen_account(req))
    assert result["status"] == "success"
    assert result["validation"]["ok"] is True
    assert result["validation"]["remaining_hours"] == 10


def test_add_qwen_account_sets_status_expired_only_on_auth_error(monkeypatch) -> None:
    import sqlite3
    import asyncio
    from media_tools.api.routers import settings as settings_router

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE Accounts_Pool(account_id TEXT PRIMARY KEY, platform TEXT, cookie_data TEXT, remark TEXT, status TEXT DEFAULT 'active', auth_state_path TEXT DEFAULT '')"
    )
    conn.commit()
    monkeypatch.setattr("media_tools.accounts.repository.get_db_connection", lambda: conn)
    monkeypatch.setattr("media_tools.api.routers.settings.save_qwen_cookie_string", lambda *args, **kwargs: {})  # noqa: ARG005

    async def _auth_fail_snapshot(*args, **kwargs):  # noqa: ANN001,ARG001
        raise RuntimeError("401 unauthorized")

    monkeypatch.setattr("media_tools.api.routers.settings.get_quota_snapshot", _auth_fail_snapshot)

    req = settings_router.QwenAccountRequest(cookie_string="tongyi_sso_ticket=abcdefghijklmnopqrstuvwxyz1234567890", remark="r")
    result = asyncio.run(settings_router.add_qwen_account(req))
    account_id = result["account_id"]
    assert result["validation"]["ok"] is False
    assert result["validation"]["error_type"] == "auth"
    row = conn.execute("SELECT status FROM Accounts_Pool WHERE account_id=?", (account_id,)).fetchone()
    assert row is not None
    assert row[0] == "expired"


def test_add_qwen_account_does_not_set_status_expired_on_network_error(monkeypatch) -> None:
    import sqlite3
    import asyncio
    from media_tools.api.routers import settings as settings_router

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE Accounts_Pool(account_id TEXT PRIMARY KEY, platform TEXT, cookie_data TEXT, remark TEXT, status TEXT DEFAULT 'active', auth_state_path TEXT DEFAULT '')"
    )
    conn.commit()
    monkeypatch.setattr("media_tools.accounts.repository.get_db_connection", lambda: conn)
    monkeypatch.setattr("media_tools.api.routers.settings.save_qwen_cookie_string", lambda *args, **kwargs: {})  # noqa: ARG005

    async def _network_fail_snapshot(*args, **kwargs):  # noqa: ANN001,ARG001
        raise RuntimeError("token-get failed: EOF occurred in violation of protocol")

    monkeypatch.setattr("media_tools.api.routers.settings.get_quota_snapshot", _network_fail_snapshot)

    req = settings_router.QwenAccountRequest(cookie_string="tongyi_sso_ticket=abcdefghijklmnopqrstuvwxyz1234567890", remark="r")
    result = asyncio.run(settings_router.add_qwen_account(req))
    account_id = result["account_id"]
    assert result["validation"]["ok"] is False
    assert result["validation"]["error_type"] == "network"
    row = conn.execute("SELECT status FROM Accounts_Pool WHERE account_id=?", (account_id,)).fetchone()
    assert row is not None
    assert row[0] == "active"


def test_qwen_status_returns_remaining_hours_from_db(monkeypatch) -> None:
    import sqlite3
    import asyncio
    from media_tools.api.routers import settings as settings_router

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE Accounts_Pool(account_id TEXT PRIMARY KEY, platform TEXT, cookie_data TEXT, remark TEXT, status TEXT DEFAULT 'active', auth_state_path TEXT DEFAULT '')"
    )
    conn.execute(
        "INSERT INTO Accounts_Pool(account_id, platform, cookie_data, remark, status, auth_state_path) VALUES(?,?,?,?,?,?)",
        ("a1", "qwen", "tongyi_sso_ticket=abcdefghijklmnopqrstuvwxyz1234567890", "r", "active", "data/auth/qwen-storage-state-a1.json"),
    )
    conn.commit()
    monkeypatch.setattr("media_tools.accounts.repository.get_db_connection", lambda: conn)

    async def _fake_get_qwen_account_status():
        return {
            "status": "success",
            "accounts": [
                {"accountId": "a1", "accountLabel": "r", "remaining_hours": 375, "status": "active"}
            ]
        }

    monkeypatch.setattr("media_tools.api.routers.settings.get_qwen_account_status", _fake_get_qwen_account_status)

    result = asyncio.run(settings_router.get_qwen_status())
    assert result["status"] == "success"
    assert result["accounts"][0]["remaining_hours"] == 375


def test_qwen_status_does_not_fail_when_single_account_snapshot_errors(monkeypatch) -> None:
    import sqlite3
    import asyncio
    from media_tools.api.routers import settings as settings_router

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE Accounts_Pool(account_id TEXT PRIMARY KEY, platform TEXT, cookie_data TEXT, remark TEXT, status TEXT DEFAULT 'active', auth_state_path TEXT DEFAULT '')"
    )
    conn.execute(
        "INSERT INTO Accounts_Pool(account_id, platform, cookie_data, remark, status, auth_state_path) VALUES(?,?,?,?,?,?)",
        ("a1", "qwen", "tongyi_sso_ticket=abcdefghijklmnopqrstuvwxyz1234567890", "r", "active", "data/auth/qwen-storage-state-a1.json"),
    )
    conn.commit()
    monkeypatch.setattr("media_tools.accounts.repository.get_db_connection", lambda: conn)

    async def _fake_get_qwen_account_status():
        return {
            "status": "success",
            "accounts": [
                {"accountId": "a1", "accountLabel": "r", "remaining_hours": 0, "status": "active"}
            ]
        }

    monkeypatch.setattr("media_tools.api.routers.settings.get_qwen_account_status", _fake_get_qwen_account_status)

    result = asyncio.run(settings_router.get_qwen_status())
    assert result["status"] == "success"
    assert len(result["accounts"]) == 1
    assert result["accounts"][0]["accountId"] == "a1"
    assert result["accounts"][0]["remaining_hours"] == 0


def test_qwen_claim_iterates_db_accounts(monkeypatch) -> None:
    import sqlite3
    import asyncio
    from media_tools.api.routers import settings as settings_router

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE Accounts_Pool(account_id TEXT PRIMARY KEY, platform TEXT, cookie_data TEXT, remark TEXT, status TEXT DEFAULT 'active', auth_state_path TEXT DEFAULT '')"
    )
    conn.execute(
        "INSERT INTO Accounts_Pool(account_id, platform, cookie_data, remark, status, auth_state_path) VALUES(?,?,?,?,?,?)",
        ("a1", "qwen", "tongyi_sso_ticket=abcdefghijklmnopqrstuvwxyz1234567890", "r", "active", "data/auth/qwen-storage-state-a1.json"),
    )
    conn.commit()
    monkeypatch.setattr("media_tools.accounts.repository.get_db_connection", lambda: conn)

    called = {"count": 0}

    async def _fake_claim_qwen_quota():
        called["count"] += 1
        return {"status": "success", "results": [{"accountId": "a1", "status": "claimed", "reason": ""}]}

    monkeypatch.setattr("media_tools.api.routers.settings.claim_qwen_quota", _fake_claim_qwen_quota)

    result = asyncio.run(settings_router.claim_qwen_quota_endpoint())
    assert result["status"] == "success"
    assert called["count"] == 1


def test_orchestrator_tries_multiple_qwen_accounts(monkeypatch, tmp_path) -> None:
    import asyncio
    from pathlib import Path
    from media_tools.transcribe.service import OrchestratorV2
    from media_tools.core.config import AppConfig
    from media_tools.transcribe.models import AccountPool

    class _AuthErr(Exception):
        pass

    calls: list[str] = []

    async def _fake_run_real_flow(*, file_path, auth_state_path, **kwargs):  # noqa: ANN001
        calls.append(str(auth_state_path))
        if len(calls) == 1:
            raise _AuthErr("401 unauthorized")

        class _R:
            export_path = tmp_path / "o.md"
            record_id = "r"
            gen_record_id = "g"
            remote_deleted = True

        return _R()

    monkeypatch.setattr("media_tools.transcribe.service.run_real_flow", _fake_run_real_flow)

    cfg = AppConfig()
    orch = OrchestratorV2(config=cfg, auth_state_path=Path("dummy.json"))

    # 正确初始化账号池（使用 acquire/release 互斥机制）
    accounts = [
        {"account_id": "a1", "auth_state_path": Path("a1.json")},
        {"account_id": "a2", "auth_state_path": Path("a2.json")},
    ]
    orch._account_pool_service._account_pool = AccountPool(accounts)

    # 模拟 _get_shared_api 和 _release_shared_api（避免启动真实 Playwright）
    async def _fake_get_shared_api(auth_state_path):
        return None
    async def _fake_release_shared_api():
        pass
    orch._get_shared_api = _fake_get_shared_api  # type: ignore[attr-defined]
    orch._release_shared_api = _fake_release_shared_api  # type: ignore[attr-defined]

    p = tmp_path / "a.mp3"
    p.write_bytes(b"ok")
    result = asyncio.run(orch._transcribe_single_video(p))
    assert result.success is True
    assert calls == ["a1.json", "a2.json"]

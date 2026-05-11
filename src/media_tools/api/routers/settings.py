from typing import Optional, Union
import logging
import sqlite3
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from media_tools.pipeline.error_types import ErrorType, classify_error
from media_tools.transcribe.auth_state import has_qwen_auth_state, save_qwen_cookie_string, default_qwen_auth_state_path
from media_tools.transcribe.db_account_pool import build_qwen_auth_state_path_for_account
from media_tools.transcribe.quota import get_quota_snapshot, remaining_hours_from_snapshot
from media_tools.douyin.core.config_mgr import get_config
from media_tools.db.core import get_db_connection
from media_tools.core.config import get_runtime_setting, get_runtime_setting_int, get_runtime_setting_bool, set_runtime_setting
from media_tools.services.qwen_status import get_qwen_account_status, claim_qwen_quota

router = APIRouter(prefix="/api/v1/settings", tags=["settings"], redirect_slashes=False)
logger = logging.getLogger(__name__)

class QwenConfigRequest(BaseModel):
    cookie_string: str

class QwenAccountRequest(BaseModel):
    cookie_string: str
    remark: str = ""

class QwenCookieUpdateRequest(BaseModel):
    cookie_string: str

class DouyinAccountRequest(BaseModel):
    cookie_string: str
    remark: str = ""

class BilibiliAccountRequest(BaseModel):
    cookie_string: str
    remark: str = ""

class GlobalSettingsRequest(BaseModel):
    concurrency: Optional[int] = None
    auto_delete: Optional[bool] = None
    auto_transcribe: Optional[bool] = None
    export_format: Optional[str] = None

class RemarkRequest(BaseModel):
    remark: str

@router.get("")
def get_settings():
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get douyin accounts
        cursor.execute("SELECT account_id, status, last_used, remark, create_time FROM Accounts_Pool WHERE platform='douyin'")
        accounts = [{"id": row[0], "status": row[1], "last_used": row[2], "remark": row[3] or "", "create_time": row[4] or ""} for row in cursor.fetchall()]

        # Get qwen accounts
        cursor.execute("SELECT account_id, status, last_used, remark, create_time FROM Accounts_Pool WHERE platform='qwen'")
        qwen_accounts = [{"id": row[0], "status": row[1], "last_used": row[2], "remark": row[3] or "", "create_time": row[4] or ""} for row in cursor.fetchall()]

        # Get bilibili accounts
        cursor.execute("SELECT account_id, status, last_used, remark, create_time FROM Accounts_Pool WHERE platform='bilibili'")
        bilibili_accounts = [{"id": row[0], "status": row[1], "last_used": row[2], "remark": row[3] or "", "create_time": row[4] or ""} for row in cursor.fetchall()]

    concurrency = get_runtime_setting_int("concurrency", 10)
    auto_delete = get_runtime_setting_bool("auto_delete", True)
    auto_transcribe = get_runtime_setting_bool("auto_transcribe", False)
    export_format = get_runtime_setting("export_format", "md")
    douyin_accounts_count = len(accounts)
    douyin_primary_configured = get_config().has_cookie()
    douyin_cookie_source = "pool" if douyin_accounts_count > 0 else ("config" if douyin_primary_configured else "none")
    qwen_configured = has_qwen_auth_state()
    qwen_accounts_count = len(qwen_accounts)
    bilibili_accounts_count = len(bilibili_accounts)
    can_download = douyin_primary_configured or douyin_accounts_count > 0 or bilibili_accounts_count > 0
    can_transcribe = qwen_configured or qwen_accounts_count > 0

    return {
        "qwen_configured": qwen_configured,
        "douyin_accounts": accounts,
        "qwen_accounts": qwen_accounts,
        "bilibili_accounts": bilibili_accounts,
        "global_settings": {
            "concurrency": concurrency,
            "auto_delete": auto_delete,
            "auto_transcribe": auto_transcribe,
            "export_format": export_format,
        },
        "status_summary": {
            "qwen_ready": qwen_configured or qwen_accounts_count > 0,
            "douyin_ready": douyin_primary_configured or douyin_accounts_count > 0,
            "douyin_accounts_count": douyin_accounts_count,
            "douyin_primary_configured": douyin_primary_configured,
            "douyin_cookie_source": douyin_cookie_source,
            "qwen_accounts_count": qwen_accounts_count,
            "bilibili_accounts_count": bilibili_accounts_count,
            "can_download": can_download,
            "can_transcribe": can_transcribe,
            "can_run_pipeline": can_download and can_transcribe,
        }
    }

_MIN_COOKIE_LENGTH = 20


def _validate_cookie_string(cookie_string: str) -> str:
    trimmed = cookie_string.strip()
    if not trimmed:
        raise HTTPException(status_code=400, detail="Cookie 不能为空")
    if len(trimmed) < _MIN_COOKIE_LENGTH:
        raise HTTPException(status_code=400, detail=f"Cookie 格式无效或过短（最少 {_MIN_COOKIE_LENGTH} 字符）")
    if "=" not in trimmed:
        raise HTTPException(status_code=400, detail="Cookie 格式无效，应为 key=value;key=value 格式")
    return trimmed


@router.post("/douyin")
def add_douyin_account(req: DouyinAccountRequest):
    try:
        cookie = _validate_cookie_string(req.cookie_string)
        account_id = str(uuid.uuid4())
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO Accounts_Pool (account_id, platform, cookie_data, remark) VALUES (?, ?, ?, ?)",
                (account_id, "douyin", cookie, req.remark)
            )
            conn.commit()
        return {"status": "success", "account_id": account_id}
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/douyin/{account_id}")
def delete_douyin_account(account_id: str):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM Accounts_Pool WHERE account_id=? AND platform='douyin'", (account_id,))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Account not found")
            conn.commit()
        return {"status": "success"}
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/douyin/{account_id}/remark")
def update_douyin_account_remark(account_id: str, req: RemarkRequest):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE Accounts_Pool SET remark=? WHERE account_id=? AND platform='douyin'",
                (req.remark, account_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Account not found")
            conn.commit()
        return {"status": "success"}
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/bilibili/accounts")
def add_bilibili_account(req: BilibiliAccountRequest):
    try:
        cookie = _validate_cookie_string(req.cookie_string)
        account_id = str(uuid.uuid4())
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO Accounts_Pool (account_id, platform, cookie_data, remark) VALUES (?, ?, ?, ?)",
                (account_id, "bilibili", cookie, req.remark),
            )
            conn.commit()
        return {"status": "success", "account_id": account_id}
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/bilibili/accounts/{account_id}")
def delete_bilibili_account(account_id: str):
    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM Accounts_Pool WHERE account_id=? AND platform='bilibili'",
                (account_id,),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Account not found")
            conn.commit()
        return {"status": "success"}
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/bilibili/accounts/{account_id}/remark")
def update_bilibili_account_remark(account_id: str, req: RemarkRequest):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE Accounts_Pool SET remark=? WHERE account_id=? AND platform='bilibili'",
                (req.remark, account_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Account not found")
            conn.commit()
        return {"status": "success"}
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/qwen/status")
async def get_qwen_status():
    return await get_qwen_account_status()

@router.post("/qwen/claim")
async def claim_qwen_quota_endpoint():
    """手动触发领取每日 Qwen 额度"""
    try:
        return await claim_qwen_quota()
    except (RuntimeError, OSError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/global")
def update_global_settings(req: GlobalSettingsRequest):
    try:
        if req.concurrency is None and req.auto_delete is None and req.auto_transcribe is None and req.export_format is None:
            raise HTTPException(status_code=400, detail="No fields to update")
        if req.concurrency is not None:
            if req.concurrency < 1 or req.concurrency > 100:
                raise HTTPException(status_code=400, detail="concurrency 必须在 1-100 之间")
            set_runtime_setting("concurrency", req.concurrency)
        if req.auto_delete is not None:
            set_runtime_setting("auto_delete", req.auto_delete)
        if req.auto_transcribe is not None:
            set_runtime_setting("auto_transcribe", req.auto_transcribe)
        if req.export_format is not None:
            if req.export_format not in ("md", "docx", "pdf", "srt", "txt"):
                raise HTTPException(status_code=400, detail="export_format must be one of: md, docx, pdf, srt, txt")
            set_runtime_setting("export_format", req.export_format)
        return {"status": "success"}
    except HTTPException:
        raise
    except (ValueError, sqlite3.Error, OSError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/qwen")
def update_qwen_key(req: QwenConfigRequest):
    try:
        cookie = _validate_cookie_string(req.cookie_string)
        save_qwen_cookie_string(cookie, default_qwen_auth_state_path())
        return {"status": "success"}
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/qwen/accounts")
async def add_qwen_account(req: QwenAccountRequest):
    try:
        cookie = _validate_cookie_string(req.cookie_string)
        account_id = str(uuid.uuid4())
        auth_state_path = build_qwen_auth_state_path_for_account(account_id)
        save_qwen_cookie_string(cookie, auth_state_path, sync_db=False)

        status = "active"
        validation: dict[str, object] = {
            "ok": True,
            "remaining_hours": 0,
            "error_type": "",
            "message": "",
        }
        try:
            snapshot = await get_quota_snapshot(
                auth_state_path=auth_state_path,
                account_id=account_id,
            )
            validation["remaining_hours"] = remaining_hours_from_snapshot(snapshot)
        except (RuntimeError, OSError, ValueError, TypeError) as exc:
            et = classify_error(exc)
            validation["ok"] = False
            validation["error_type"] = et.value
            validation["message"] = str(exc)
            validation["remaining_hours"] = 0
            if et == ErrorType.AUTH:
                status = "expired"

        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO Accounts_Pool (account_id, platform, cookie_data, remark, auth_state_path, status) VALUES (?, ?, ?, ?, ?, ?)",
                (account_id, "qwen", req.cookie_string, req.remark, str(auth_state_path), status),
            )
            conn.commit()
        return {"status": "success", "account_id": account_id, "validation": validation}
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/qwen/accounts/{account_id}/cookie")
def update_qwen_account_cookie(account_id: str, req: QwenCookieUpdateRequest):
    try:
        cookie = _validate_cookie_string(req.cookie_string)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute(
                "SELECT auth_state_path FROM Accounts_Pool WHERE account_id=? AND platform='qwen'",
                (account_id,),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Account not found")

            existing_path = str(row[0] or "")
            auth_state_path = Path(existing_path) if existing_path.strip() else build_qwen_auth_state_path_for_account(account_id)

            save_qwen_cookie_string(cookie, auth_state_path, sync_db=False)

            cursor.execute(
                "UPDATE Accounts_Pool SET cookie_data=?, status='active', auth_state_path=? WHERE account_id=? AND platform='qwen'",
                (cookie, str(auth_state_path), account_id),
            )
            conn.commit()

        return {"status": "success", "account_id": account_id}
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/qwen/accounts/{account_id}")
def delete_qwen_account(account_id: str):
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM Accounts_Pool WHERE account_id=? AND platform='qwen'", (account_id,))
            conn.commit()
        return {"status": "success"}
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/qwen/accounts/rehydrate")
def rehydrate_qwen_accounts():
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT account_id, cookie_data, auth_state_path FROM Accounts_Pool WHERE platform='qwen'",
            ).fetchall()

            results: list[dict[str, str]] = []
            updated = 0
            skipped = 0
            failed = 0

            for row in rows:
                account_id = str(row["account_id"] or "")
                cookie_data = str(row["cookie_data"] or "").strip()
                existing_path = str(row["auth_state_path"] or "").strip()
                auth_state_path = Path(existing_path) if existing_path else build_qwen_auth_state_path_for_account(account_id)

                if not cookie_data:
                    skipped += 1
                    results.append(
                        {
                            "account_id": account_id,
                            "status": "skipped",
                            "reason": "empty-cookie",
                            "auth_state_path": str(auth_state_path),
                        }
                    )
                    continue

                try:
                    save_qwen_cookie_string(cookie_data, auth_state_path, sync_db=False)
                except (ValueError, OSError, sqlite3.Error) as exc:
                    failed += 1
                    results.append(
                        {
                            "account_id": account_id,
                            "status": "failed",
                            "reason": str(exc),
                            "auth_state_path": str(auth_state_path),
                        }
                    )
                    continue

                updated += 1
                results.append(
                    {
                        "account_id": account_id,
                        "status": "updated",
                        "reason": "",
                        "auth_state_path": str(auth_state_path),
                    }
                )

                if not existing_path:
                    conn.execute(
                        "UPDATE Accounts_Pool SET auth_state_path=?, status='active' WHERE account_id=? AND platform='qwen'",
                        (str(auth_state_path), account_id),
                    )

            conn.commit()

        return {
            "status": "success",
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
            "results": results,
        }
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/qwen/accounts/{account_id}/remark")
def update_qwen_account_remark(account_id: str, req: RemarkRequest):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Accounts_Pool SET remark=? WHERE account_id=? AND platform='qwen'", (req.remark, account_id))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Account not found")
            conn.commit()
        return {"status": "success"}
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

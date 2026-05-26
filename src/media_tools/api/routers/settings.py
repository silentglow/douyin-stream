from typing import Optional
import logging
import sqlite3
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from media_tools.transcribe.errors import ErrorType, classify_error
from media_tools.transcribe.auth_state import has_qwen_auth_state, save_qwen_cookie_string, default_qwen_auth_state_path
from media_tools.transcribe.db_account_pool import build_qwen_auth_state_path_for_account
from media_tools.transcribe.quota import get_quota_snapshot, remaining_hours_from_snapshot
from media_tools.douyin.core.config_mgr import get_config
from media_tools.core.config import get_runtime_setting, get_runtime_setting_int, get_runtime_setting_bool, set_runtime_setting
from media_tools.accounts.status import get_qwen_account_status, claim_qwen_quota
from media_tools.accounts.repository import AccountRepository

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
    transcript_output_dir: Optional[str] = None

class RemarkRequest(BaseModel):
    remark: str

@router.get("")
def get_settings():
    accounts = AccountRepository.list_by_platform("douyin")
    qwen_accounts = AccountRepository.list_by_platform("qwen")
    bilibili_accounts = AccountRepository.list_by_platform("bilibili")

    concurrency = get_runtime_setting_int("concurrency", 10)
    auto_delete = get_runtime_setting_bool("auto_delete", True)
    auto_transcribe = get_runtime_setting_bool("auto_transcribe", False)
    export_format = get_runtime_setting("export_format", "md")
    transcript_output_dir = get_runtime_setting("transcript_output_dir", "")
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
            "transcript_output_dir": transcript_output_dir,
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
        AccountRepository.create(account_id, "douyin", cookie, req.remark)
        return {"status": "success", "account_id": account_id}
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/douyin/{account_id}")
def delete_douyin_account(account_id: str):
    try:
        rowcount = AccountRepository.delete(account_id, "douyin")
        if rowcount == 0:
            raise HTTPException(status_code=404, detail="Account not found")
        return {"status": "success"}
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/douyin/{account_id}/remark")
def update_douyin_account_remark(account_id: str, req: RemarkRequest):
    try:
        rowcount = AccountRepository.update_remark(account_id, "douyin", req.remark)
        if rowcount == 0:
            raise HTTPException(status_code=404, detail="Account not found")
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
        AccountRepository.create(account_id, "bilibili", cookie, req.remark)
        return {"status": "success", "account_id": account_id}
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/bilibili/accounts/{account_id}")
def delete_bilibili_account(account_id: str):
    try:
        rowcount = AccountRepository.delete(account_id, "bilibili")
        if rowcount == 0:
            raise HTTPException(status_code=404, detail="Account not found")
        return {"status": "success"}
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/bilibili/accounts/{account_id}/remark")
def update_bilibili_account_remark(account_id: str, req: RemarkRequest):
    try:
        rowcount = AccountRepository.update_remark(account_id, "bilibili", req.remark)
        if rowcount == 0:
            raise HTTPException(status_code=404, detail="Account not found")
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
        if req.concurrency is None and req.auto_delete is None and req.auto_transcribe is None and req.export_format is None and req.transcript_output_dir is None:
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
        if req.transcript_output_dir is not None:
            from pathlib import Path
            import os
            target = Path(req.transcript_output_dir).resolve()
            # 防止路径注入：只允许项目根目录下的子路径
            project_root = Path(__file__).resolve().parents[4]
            try:
                target.relative_to(project_root)
            except ValueError:
                raise HTTPException(status_code=400, detail="transcript_output_dir 必须在项目目录内")
            if not os.path.isdir(target):
                raise HTTPException(status_code=400, detail="transcript_output_dir 目录不存在")
            set_runtime_setting("transcript_output_dir", str(target))
        return {"status": "success"}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (sqlite3.Error, OSError) as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/qwen")
def update_qwen_key(req: QwenConfigRequest):
    try:
        cookie = _validate_cookie_string(req.cookie_string)
        save_qwen_cookie_string(cookie, default_qwen_auth_state_path())
        return {"status": "success"}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (sqlite3.Error, OSError) as e:
        raise HTTPException(status_code=500, detail=str(e))

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

        AccountRepository.create(
            account_id, "qwen", req.cookie_string, req.remark,
            auth_state_path=str(auth_state_path), status=status,
        )
        return {"status": "success", "account_id": account_id, "validation": validation}
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/qwen/accounts/{account_id}/cookie")
def update_qwen_account_cookie(account_id: str, req: QwenCookieUpdateRequest):
    try:
        cookie = _validate_cookie_string(req.cookie_string)
        existing_path = AccountRepository.get_auth_state_path(account_id, "qwen")
        auth_state_path = Path(existing_path) if existing_path else build_qwen_auth_state_path_for_account(account_id)

        save_qwen_cookie_string(cookie, auth_state_path, sync_db=False)

        AccountRepository.update_cookie_and_status(
            account_id, "qwen", cookie, auth_state_path=str(auth_state_path), status="active",
        )

        return {"status": "success", "account_id": account_id}
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/qwen/accounts/{account_id}")
def delete_qwen_account(account_id: str):
    try:
        rowcount = AccountRepository.delete(account_id, "qwen")
        if rowcount == 0:
            raise HTTPException(status_code=404, detail="Account not found")
        return {"status": "success"}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (sqlite3.Error, OSError) as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/qwen/accounts/rehydrate")
def rehydrate_qwen_accounts():
    try:
        rows = AccountRepository.list_qwen_with_cookie()

        results: list[dict[str, str]] = []
        updated = 0
        skipped = 0
        failed = 0

        for row in rows:
            account_id = str(row.get("account_id") or "").strip()
            cookie_data = str(row.get("cookie_data") or "").strip()
            existing_path = str(row.get("auth_state_path") or "").strip()
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
                AccountRepository.update_auth_state_path(
                    account_id, "qwen", str(auth_state_path), status="active",
                )

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
        rowcount = AccountRepository.update_remark(account_id, "qwen", req.remark)
        if rowcount == 0:
            raise HTTPException(status_code=404, detail="Account not found")
        return {"status": "success"}
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

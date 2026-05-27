from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from media_tools.common.runtime import ensure_dir
from media_tools.core.config import get_db_path
from media_tools.douyin.utils.auth_parser import AuthParser
from media_tools.logger import get_logger
from media_tools.transcribe.config import load_config

logger = get_logger(__name__)

QWEN_AUTH_PLATFORM = "qwen"
QWEN_COOKIE_DOMAIN = ".qianwen.com"
QWEN_COOKIE_CORE_KEYS = frozenset(
    {
        "tongyi_sso_ticket",
        "tongyi_sso_ticket_hash",
        "login_aliyunid_ticket",
        "login_aliyunid_ticket_sha256",
        "cookie2",
        "XSRF-TOKEN",
        "atpsida",
        "cna",
        "xlly_s",
        "aliyungf_tc",
    }
)
QWEN_COOKIE_CORE_KEYS_LOWER = frozenset(item.lower() for item in QWEN_COOKIE_CORE_KEYS)

QWEN_COOKIE_NAME_MARKERS = (
    "tongyi",
    "aliyun",
    "xsrf",
    "csrf",
    "token",
    "ticket",
    "auth",
    "sess",
    "atps",
)


@dataclass(frozen=True)
class ResolvedQwenAuthState:
    storage_state: str | dict[str, Any]
    source: str
    auth_state_path: Path


def _normalized_path(input_path: str | Path) -> Path:
    return Path(input_path).expanduser().resolve()


def default_qwen_auth_state_path() -> Path:
    return _normalized_path(load_config().paths.auth_state_path)


def is_default_qwen_auth_state_path(auth_state_path: str | Path) -> bool:
    return _normalized_path(auth_state_path) == default_qwen_auth_state_path()


def validate_qwen_cookie_string(raw_cookie: str) -> tuple[bool, str, dict[str, str]]:
    parser = AuthParser()
    success, message, parsed = parser.validate_data(raw_cookie, "cookie", QWEN_AUTH_PLATFORM)

    normalized: dict[str, str] = {}
    if isinstance(parsed, dict):
        for key, value in parsed.items():
            key_text = str(key).strip()
            value_text = str(value).strip()
            if key_text and value_text:
                normalized[key_text] = value_text

    return success, message, normalized


def _should_keep_qwen_cookie(cookie_name: str) -> bool:
    normalized = cookie_name.strip().lower()
    if not normalized:
        return False
    if cookie_name in QWEN_COOKIE_CORE_KEYS:
        return True
    if normalized in QWEN_COOKIE_CORE_KEYS_LOWER:
        return True
    return any(marker in normalized for marker in QWEN_COOKIE_NAME_MARKERS)


def _build_cookie_dict(name: str, value: str) -> dict[str, Any]:
    return {
        "name": name,
        "value": value,
        "domain": QWEN_COOKIE_DOMAIN,
        "path": "/",
        "expires": -1,
        "httpOnly": False,
        "secure": False,
        "sameSite": "Lax",
    }


def build_qwen_storage_state(cookie_values: Mapping[str, str]) -> dict[str, Any]:
    cookies: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_cookie(name: str, value: str) -> None:
        normalized = name.strip().lower()
        if not normalized or not value.strip() or normalized in seen:
            return
        seen.add(normalized)
        cookies.append(_build_cookie_dict(name.strip(), value.strip()))

    for name, value in cookie_values.items():
        if _should_keep_qwen_cookie(name):
            add_cookie(name, value)

    if not cookies:
        for name, value in cookie_values.items():
            add_cookie(name, value)

    return {"cookies": cookies, "origins": []}


def build_qwen_storage_state_from_cookie_string(raw_cookie: str) -> dict[str, Any]:
    success, message, cookies = validate_qwen_cookie_string(raw_cookie)
    if not success:
        raise ValueError(message)

    state = build_qwen_storage_state(cookies)
    if not is_valid_qwen_storage_state(state):
        raise ValueError("未能从 Cookie 中构建有效的 Qwen 认证状态")
    return state


def is_valid_qwen_storage_state(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    cookies = value.get("cookies")
    if not isinstance(cookies, list) or not cookies:
        return False
    return any(
        isinstance(cookie, dict) and str(cookie.get("name", "")).strip() and str(cookie.get("value", "")).strip()
        for cookie in cookies
    )


def normalize_qwen_storage_state(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    cookies = value.get("cookies")
    if not isinstance(cookies, list):
        return None

    normalized_cookies: list[dict[str, Any]] = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue

        name = str(cookie.get("name") or "").strip()
        value_text = str(cookie.get("value") or "").strip()
        if not name or not value_text:
            continue

        domain_raw = cookie.get("domain")
        domain = domain_raw.strip() if isinstance(domain_raw, str) else ""
        if not domain:
            domain = QWEN_COOKIE_DOMAIN

        path_raw = cookie.get("path")
        path = path_raw.strip() if isinstance(path_raw, str) else ""
        if not path:
            path = "/"

        normalized_cookie = dict(cookie)
        normalized_cookie["name"] = name
        normalized_cookie["value"] = value_text
        normalized_cookie["domain"] = domain
        normalized_cookie["path"] = path
        normalized_cookies.append(normalized_cookie)

    if not normalized_cookies:
        return None

    origins = value.get("origins")
    normalized_origins = origins if isinstance(origins, list) else []
    return {"cookies": normalized_cookies, "origins": normalized_origins}


def read_qwen_storage_state_file(auth_state_path: str | Path) -> dict[str, Any] | None:
    path = _normalized_path(auth_state_path)
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    normalized = normalize_qwen_storage_state(parsed)
    return normalized if normalized is not None and is_valid_qwen_storage_state(normalized) else None


def load_qwen_storage_state_from_db(db_path: str | Path | None = None) -> dict[str, Any] | None:
    configured_path = db_path if db_path is not None else get_db_path()
    resolved_db_path = Path(configured_path).expanduser().resolve()
    if not resolved_db_path.exists():
        return None

    try:
        from media_tools.store.db import get_db_connection

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT auth_data FROM auth_credentials WHERE platform = ?",
                (QWEN_AUTH_PLATFORM,),
            )
            row = cursor.fetchone()
    except sqlite3.Error as e:
        logger.warning(f"加载Qwen认证状态失败: {e}")
        return None

    if not row or not row[0]:
        return None

    try:
        parsed = json.loads(str(row[0]))
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.warning("Qwen 认证数据库记录不是合法 JSON，已忽略")
        return None

    normalized = normalize_qwen_storage_state(parsed)
    return normalized if normalized is not None and is_valid_qwen_storage_state(normalized) else None


def has_qwen_auth_state(auth_state_path: str | Path | None = None) -> bool:
    target_path = _normalized_path(auth_state_path or default_qwen_auth_state_path())
    if _has_active_qwen_account_in_pool():
        return True
    return read_qwen_storage_state_file(target_path) is not None


def _has_active_qwen_account_in_pool() -> bool:
    try:
        from media_tools.store.db import get_db_connection

        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM Accounts_Pool WHERE platform='qwen' AND status='active' AND cookie_data IS NOT NULL AND cookie_data != '' LIMIT 1",
            ).fetchone()
            return row is not None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"检查活跃 Qwen 账号失败: {e}")
        return False


def _get_active_qwen_cookie_from_pool() -> str:
    try:
        from media_tools.store.db import get_db_connection

        with get_db_connection() as conn:
            row = conn.execute(
                """
                SELECT cookie_data
                FROM Accounts_Pool
                WHERE platform = 'qwen' AND status = 'active'
                  AND cookie_data IS NOT NULL AND cookie_data != ''
                ORDER BY
                    CASE WHEN last_used IS NULL THEN 0 ELSE 1 END,
                    last_used ASC,
                    create_time ASC
                LIMIT 1
                """,
            ).fetchone()
            if row and row[0]:
                return str(row[0]).strip()
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"从账号池读取Qwen Cookie失败: {e}")
    return ""


def resolve_qwen_auth_state(auth_state_path: str | Path) -> ResolvedQwenAuthState:
    target_path = _normalized_path(auth_state_path)

    pool_cookie = _get_active_qwen_cookie_from_pool()
    if pool_cookie:
        try:
            state = build_qwen_storage_state_from_cookie_string(pool_cookie)
            return ResolvedQwenAuthState(
                storage_state=state,
                source="pool",
                auth_state_path=target_path,
            )
        except (ValueError, OSError):
            logger.warning("账号池中的 Qwen Cookie 无法构建有效的 storage state，回退到文件")

    file_state = read_qwen_storage_state_file(target_path)
    if file_state is not None:
        return ResolvedQwenAuthState(
            storage_state=file_state,
            source="file",
            auth_state_path=target_path,
        )

    raise FileNotFoundError(f"auth state file does not exist or is invalid: {target_path}")


def persist_qwen_auth_state(
    state: Mapping[str, Any],
    auth_state_path: str | Path,
    *,
    sync_db: bool | None = None,
) -> Path:
    serialized_state = dict(state)
    if not is_valid_qwen_storage_state(serialized_state):
        raise ValueError("invalid Qwen storage state payload")

    target_path = _normalized_path(auth_state_path)
    ensure_dir(target_path.parent)
    import os
    import threading

    payload = json.dumps(serialized_state, ensure_ascii=False, indent=2)
    tmp_path = target_path.with_name(f"{target_path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    os.replace(str(tmp_path), str(target_path))

    return target_path


def save_qwen_cookie_string(
    raw_cookie: str,
    auth_state_path: str | Path,
    *,
    sync_db: bool | None = None,
) -> dict[str, Any]:
    state = build_qwen_storage_state_from_cookie_string(raw_cookie)
    persist_qwen_auth_state(state, auth_state_path)
    return state


def cookie_string_from_storage_state(storage_state: Mapping[str, Any]) -> str:
    cookies = storage_state.get("cookies")
    if not isinstance(cookies, list):
        return ""
    pairs: list[str] = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "").strip()
        if not name or not value:
            continue
        pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def resolve_qwen_cookie_string(*, auth_state_path: str | Path, account_id: str = "") -> str:
    selected_account = str(account_id or "").strip()
    if selected_account:
        from .db_account_pool import load_qwen_cookie_data_for_account

        cookie_data = load_qwen_cookie_data_for_account(selected_account)
        if cookie_data:
            return cookie_data

    pool_cookie = _get_active_qwen_cookie_from_pool()
    if pool_cookie:
        return pool_cookie

    resolved = resolve_qwen_auth_state(auth_state_path)
    storage_state = resolved.storage_state
    if isinstance(storage_state, str):
        try:
            parsed = json.loads(storage_state)
        except (TypeError, ValueError, json.JSONDecodeError):
            return ""
        normalized = normalize_qwen_storage_state(parsed)
        if normalized is None:
            return ""
        return cookie_string_from_storage_state(normalized)

    normalized = normalize_qwen_storage_state(storage_state)
    if normalized is None:
        return ""
    return cookie_string_from_storage_state(normalized)

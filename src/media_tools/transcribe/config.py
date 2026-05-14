from __future__ import annotations
from typing import Optional, Union

from dataclasses import dataclass
from pathlib import Path
import os

from .errors import ConfigurationError
from .runtime import as_absolute, env_flag


@dataclass(frozen=True)
class AppPaths:
    auth_state_path: Path
    accounts_file: Path
    account_pool_state_file: Path
    quota_state_file: Path
    network_log_dir: Path
    download_dir: Path


@dataclass(frozen=True)
class TranscribeConfig:
    """转写模块专属配置（Qwen API 相关）。"""

    base_url: str
    app_url: str
    default_account: str
    default_account_strategy: str
    status_low_quota_minutes: int
    capture_timeout_ms: int
    flow_file: str
    export_format: str
    delete_after_export: bool
    save_debug_json: bool
    export_concurrency: int
    export_max_retries: int
    export_initial_backoff_seconds: float
    upload_concurrency_per_account: int
    paths: AppPaths


def _strip(value: Optional[str], default: str) -> str:
    return str(value or default).strip()


def parse_int_setting(name: str, default: int, *, minimum: Optional[int] = None) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        value = default
    else:
        try:
            value = int(raw)
        except ValueError as error:
            raise ConfigurationError(f"{name} must be an integer, got {raw!r}") from error
    if minimum is not None and value < minimum:
        raise ConfigurationError(f"{name} must be >= {minimum}, got {value}")
    return value


def parse_float_setting(name: str, default: float, *, minimum: Optional[float] = None) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        value = default
    else:
        try:
            value = float(raw)
        except ValueError as error:
            raise ConfigurationError(f"{name} must be a number, got {raw!r}") from error
    if minimum is not None and value < minimum:
        raise ConfigurationError(f"{name} must be >= {minimum}, got {value}")
    return value


def load_config() -> TranscribeConfig:
    base_url = _strip(os.environ.get("QWEN_BASE_URL"), "https://www.qianwen.com")
    app_url = _strip(os.environ.get("QWEN_APP_URL"), f"{base_url}/discover")
    auth_state_path = as_absolute(_strip(os.environ.get("QWEN_AUTH_STATE_PATH"), "data/auth/qwen-storage-state.json"))
    accounts_file = as_absolute(_strip(os.environ.get("QWEN_ACCOUNTS_FILE"), "data/auth/accounts.json"))
    account_pool_state_file = as_absolute(
        _strip(os.environ.get("QWEN_ACCOUNT_POOL_STATE_FILE"), "data/auth/account-pool-state.json")
    )
    quota_state_file = as_absolute(_strip(os.environ.get("QWEN_QUOTA_STATE_FILE"), "data/auth/quota-usage.json"))
    network_log_dir = as_absolute(_strip(os.environ.get("QWEN_NETWORK_LOG_DIR"), "data/logs/network"))
    download_dir = as_absolute(_strip(os.environ.get("QWEN_DOWNLOAD_DIR"), "data/downloads"))

    return TranscribeConfig(
        base_url=base_url,
        app_url=app_url,
        default_account=_strip(os.environ.get("QWEN_ACCOUNT"), ""),
        default_account_strategy=_strip(os.environ.get("QWEN_ACCOUNT_STRATEGY"), "round-robin"),
        status_low_quota_minutes=parse_int_setting("QWEN_STATUS_LOW_QUOTA_MINUTES", 120, minimum=0),
        capture_timeout_ms=parse_int_setting("QWEN_CAPTURE_TIMEOUT_MS", 900000, minimum=1),
        flow_file=_strip(os.environ.get("QWEN_FLOW_FILE"), ""),
        export_format=_strip(os.environ.get("QWEN_EXPORT_FORMAT"), "md"),
        delete_after_export=env_flag("QWEN_DELETE_AFTER_EXPORT", default=True),
        save_debug_json=env_flag("QWEN_SAVE_DEBUG_JSON", default=False),
        export_concurrency=parse_int_setting("QWEN_EXPORT_CONCURRENCY", 2, minimum=1),
        export_max_retries=parse_int_setting("QWEN_EXPORT_MAX_RETRIES", 6, minimum=1),
        export_initial_backoff_seconds=parse_float_setting(
            "QWEN_EXPORT_INITIAL_BACKOFF_SECONDS",
            2.0,
            minimum=0.1,
        ),
        upload_concurrency_per_account=parse_int_setting(
            "QWEN_UPLOAD_CONCURRENCY_PER_ACCOUNT",
            1,
            minimum=1,
        ),
        paths=AppPaths(
            auth_state_path=auth_state_path,
            accounts_file=accounts_file,
            account_pool_state_file=account_pool_state_file,
            quota_state_file=quota_state_file,
            network_log_dir=network_log_dir,
            download_dir=download_dir,
        ),
    )

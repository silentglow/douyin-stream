from __future__ import annotations
"""统一配置系统 — AppConfig 是运行时配置的唯一事实源。

配置项归属：
- SystemSettings 表：concurrency, auto_transcribe, auto_delete, api_key（运行时用户可修改）
- config/config.yaml：cookie, download_path, naming（启动时确定）
- 环境变量：DEBUG, LOG_LEVEL, PIPELINE_* 系列（启动参数）

使用方式：
    from media_tools.core.config import get_app_config
    
    config = get_app_config()
    config.concurrency      # 并发数
    config.download_path    # 下载路径
    config.debug_mode       # 调试模式
"""

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Callable, Optional, Union

logger = logging.getLogger(__name__)

from media_tools.db.core import get_db_connection, validate_identifier


class ConfigError(Exception):
    """配置错误"""


# --- Runtime config backed by SystemSettings ---

_RUNTIME_DEFAULTS: dict[str, str] = {
    "concurrency": "10",
    "auto_transcribe": "false",
    "auto_delete": "true",
    "api_key": "",
    "export_format": "md",
}


# --- Cache for system settings ---
import time

_settings_cache: dict[str, tuple[str, float]] = {}  # key -> (value, expire_time)
_settings_cache_ttl: int = 300  # 5分钟缓存过期时间


def _get_system_setting(key: str) -> Optional[str]:
    """从 SystemSettings 表读取单个配置值（带缓存）。"""
    now = time.time()
    
    # 先检查缓存
    if key in _settings_cache:
        value, expire_time = _settings_cache[key]
        if now < expire_time:
            return value
    
    # 缓存未命中或已过期，从数据库读取
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT value FROM SystemSettings WHERE key = ?", (key,)
            ).fetchone()
            value = row[0] if row else None
            
            # 更新缓存
            if value is not None:
                _settings_cache[key] = (value, now + _settings_cache_ttl)
            
            return value
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"读取系统设置失败: {e}")
        return None


def _invalidate_settings_cache(key: Optional[str] = None) -> None:
    """清除设置缓存。"""
    if key is None:
        _settings_cache.clear()
    elif key in _settings_cache:
        del _settings_cache[key]


def _set_system_setting(key: str, value: str) -> None:
    """写入 SystemSettings 表（写入后清除相关缓存）。"""
    try:
        with get_db_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO SystemSettings (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()
        
        # 清除相关缓存，确保下次读取时获取最新值
        _invalidate_settings_cache(key)
    except (sqlite3.Error, OSError) as e:
        raise ConfigError(f"无法保存配置 {key}: {e}") from e


def get_runtime_setting(key: str, default: Optional[str] = None) -> str:
    """读取运行时配置。优先从 SystemSettings 读取，fallback 到默认值。"""
    value = _get_system_setting(key)
    if value is not None:
        return value
    return default if default is not None else _RUNTIME_DEFAULTS.get(key, "")


def get_runtime_setting_bool(key: str, default: bool = False) -> bool:
    """读取布尔型运行时配置。"""
    raw = get_runtime_setting(key)
    if raw == "":
        return default
    return raw.lower() in ("true", "1", "yes", "on")


def get_runtime_setting_int(key: str, default: int = 0) -> int:
    """读取整型运行时配置。"""
    raw = get_runtime_setting(key)
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def set_runtime_setting(key: str, value: str | bool | int) -> None:
    """设置运行时配置，写入 SystemSettings 表。"""
    if isinstance(value, bool):
        str_value = "true" if value else "false"
    else:
        str_value = str(value)
    _set_system_setting(key, str_value)


# --- Config.yaml access (read-only for runtime) ---

_CONFIG_MGR: Optional[Any] = None


def _get_config_mgr() -> Any:
    """延迟加载 douyin 配置管理器（兼容层）。"""
    global _CONFIG_MGR
    if _CONFIG_MGR is None:
        from media_tools.douyin.core.config_mgr import get_config

        _CONFIG_MGR = get_config()
    return _CONFIG_MGR


def reset_config_cache() -> None:
    """重置配置缓存（测试用）。"""
    global _CONFIG_MGR
    _CONFIG_MGR = None


def get_cookie() -> str:
    """获取 Cookie 字符串。来源：config.yaml（敏感信息暂不迁移到数据库）。"""
    return _get_config_mgr().get_cookie()


def has_cookie() -> bool:
    """检查是否配置了 Cookie。"""
    return _get_config_mgr().has_cookie()


def get_download_path() -> Path:
    """获取下载路径。来源：config.yaml。"""
    return _get_config_mgr().get_download_path()


def get_naming_format() -> str:
    """获取文件命名格式。来源：config.yaml。"""
    return _get_config_mgr().get_naming()


def get_project_root() -> Path:
    """获取项目根目录。来源：config.yaml。"""
    return _get_config_mgr().project_root


def get_db_path() -> Path:
    """获取数据库文件路径。来源：config.yaml。"""
    return _get_config_mgr().get_db_path()


# --- Environment variable helpers ---

def _get_env_bool(key: str, default: bool = False) -> bool:
    """从环境变量读取布尔值。"""
    value = os.environ.get(key, "").strip().lower()
    if value == "":
        return default
    return value in ("true", "1", "yes", "on")


def _get_env_int(key: str, default: int = 0) -> int:
    """从环境变量读取整数值。"""
    value = os.environ.get(key, "").strip()
    if value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_str(key: str, default: str = "") -> str:
    """从环境变量读取字符串值。"""
    return os.environ.get(key, default).strip()


# --- Unified AppConfig ---

class AppConfig:
    """统一应用配置接口 — 所有配置项的唯一入口。
    
    配置来源优先级（从高到低）：
    1. 环境变量
    2. SystemSettings 数据库表
    3. config.yaml
    4. 默认值
    """

    # === Runtime settings (SystemSettings) ===
    
    @property
    def concurrency(self) -> int:
        """并发数（同时处理的任务数量）"""
        return get_runtime_setting_int("concurrency", 10)

    @property
    def auto_transcribe(self) -> bool:
        """是否自动转写下载的视频"""
        return get_runtime_setting_bool("auto_transcribe", False)

    @property
    def auto_delete(self) -> bool:
        """转写完成后是否自动删除源视频文件"""
        return get_runtime_setting_bool("auto_delete", True)

    @property
    def api_key(self) -> str:
        """API 密钥（用于认证）"""
        return get_runtime_setting("api_key", "")

    # === Static settings (config.yaml) ===
    
    @property
    def cookie(self) -> str:
        """抖音 Cookie（敏感信息）"""
        return get_cookie()

    @property
    def has_cookie(self) -> bool:
        """检查是否配置了 Cookie"""
        return has_cookie()

    @property
    def download_path(self) -> Path:
        """视频下载路径"""
        return get_download_path()

    @property
    def naming_format(self) -> str:
        """文件命名格式"""
        return get_naming_format()

    @property
    def project_root(self) -> Path:
        """项目根目录"""
        return get_project_root()

    @property
    def db_path(self) -> Path:
        """数据库文件路径"""
        return get_db_path()

    # === Environment settings ===
    
    @property
    def debug_mode(self) -> bool:
        """调试模式"""
        return _get_env_bool("DEBUG", False)

    @property
    def log_level(self) -> str:
        """日志级别 (DEBUG, INFO, WARNING, ERROR)"""
        return _get_env_str("LOG_LEVEL", "INFO").upper()

    @property
    def log_json_format(self) -> bool:
        """是否使用 JSON 格式日志"""
        return _get_env_bool("LOG_JSON_FORMAT", True)

    @property
    def pipeline_export_format(self) -> str:
        """Pipeline 导出格式 (md, docx, pdf, srt, txt)。优先从 SystemSettings 读取，fallback 到环境变量。"""
        db_value = get_runtime_setting("export_format", "")
        if db_value in ("md", "docx", "pdf", "srt", "txt"):
            return db_value
        return _get_env_str("PIPELINE_EXPORT_FORMAT", "md").lower()

    @property
    def pipeline_output_dir(self) -> str:
        """Pipeline 输出目录"""
        return _get_env_str("PIPELINE_OUTPUT_DIR", str(self.project_root / "data" / "transcripts"))

    @property
    def pipeline_delete_after_export(self) -> bool:
        """导出后是否删除源文件"""
        return _get_env_bool("PIPELINE_DELETE_AFTER_EXPORT", True)

    @property
    def pipeline_account_id(self) -> str:
        """Pipeline 默认账号 ID"""
        return _get_env_str("PIPELINE_ACCOUNT_ID", "")

    # === Derived properties ===
    
    @property
    def output_path(self) -> Path:
        """Pipeline 输出路径（解析后的绝对路径）"""
        return Path(self.pipeline_output_dir).resolve()

    # === Configuration validation ===
    
    def validate(self) -> list[str]:
        """验证所有配置项，返回错误列表"""
        errors = []
        
        if self.concurrency < 1:
            errors.append("concurrency 必须大于 0")
        
        if self.concurrency > 100:
            errors.append("concurrency 建议不超过 100")
        
        if not self.db_path.parent.exists():
            errors.append(f"数据库目录不存在: {self.db_path.parent}")
        
        if not self.download_path.exists():
            errors.append(f"下载目录不存在: {self.download_path}")
        
        return errors

    # === Configuration description ===
    
    def describe(self) -> dict[str, Any]:
        """返回配置项描述字典（不包含敏感信息）"""
        return {
            "runtime": {
                "concurrency": self.concurrency,
                "auto_transcribe": self.auto_transcribe,
                "auto_delete": self.auto_delete,
                "api_key_set": bool(self.api_key),
            },
            "static": {
                "download_path": str(self.download_path),
                "naming_format": self.naming_format,
                "project_root": str(self.project_root),
                "db_path": str(self.db_path),
                "cookie_set": self.has_cookie,
            },
            "environment": {
                "debug_mode": self.debug_mode,
                "log_level": self.log_level,
                "log_json_format": self.log_json_format,
                "pipeline_export_format": self.pipeline_export_format,
                "pipeline_output_dir": self.pipeline_output_dir,
                "pipeline_delete_after_export": self.pipeline_delete_after_export,
                "pipeline_account_id_set": bool(self.pipeline_account_id),
                "auto_delete": self.auto_delete,
            },
        }


# --- Configuration change listeners ---

_config_listeners: list[Callable[[str, Any, Any], None]] = []


def add_config_listener(listener: Callable[[str, Any, Any], None]) -> None:
    """添加配置变更监听器。
    
    Args:
        listener: 回调函数，接收 (key, old_value, new_value) 参数
    """
    _config_listeners.append(listener)


def notify_config_change(key: str, old_value: Any, new_value: Any) -> None:
    """通知所有监听器配置变更。"""
    for listener in _config_listeners:
        try:
            listener(key, old_value, new_value)
        except Exception as e:
            logger.error(f"配置变更监听器执行失败: {e}")


# --- Global instances ---

_app_config = AppConfig()


def get_app_config() -> AppConfig:
    """获取全局 AppConfig 实例。"""
    return _app_config


# --- Pipeline config (for backward compatibility) ---

class PipelineConfig:
    """Pipeline 配置 — 从环境变量读取（启动参数），支持实例化覆盖。
    
    保留此类以保持向后兼容，新代码建议使用 AppConfig。
    """

    def __init__(
        self,
        export_format: str = "",
        output_dir: str = "",
        delete_after_export: Optional[bool] = None,
        account_id: str = "",
        concurrency: Optional[int] = None,
        export_concurrency: Optional[int] = None,
    ):
        self._export_format = export_format
        self._output_dir = output_dir
        self._delete_after_export = delete_after_export
        self._account_id = account_id
        self._concurrency = concurrency
        self._export_concurrency = export_concurrency

    @property
    def export_format(self) -> str:
        if self._export_format:
            return self._export_format
        return get_app_config().pipeline_export_format

    @property
    def output_dir(self) -> str:
        if self._output_dir:
            return self._output_dir
        return get_app_config().pipeline_output_dir

    @property
    def output_path(self) -> Path:
        if self._output_dir:
            return Path(self._output_dir).resolve()
        return get_app_config().output_path

    @property
    def delete_after_export(self) -> bool:
        if self._delete_after_export is not None:
            return self._delete_after_export
        return get_app_config().pipeline_delete_after_export

    @property
    def account_id(self) -> str:
        if self._account_id:
            return self._account_id
        return get_app_config().pipeline_account_id

    @property
    def concurrency(self) -> int:
        if self._concurrency is not None:
            return self._concurrency
        return get_app_config().concurrency

    @property
    def export_concurrency(self) -> int:
        if self._export_concurrency is not None:
            return self._export_concurrency
        return _get_env_int("QWEN_EXPORT_CONCURRENCY", 2)


_pipeline_config = PipelineConfig()


def get_pipeline_config() -> PipelineConfig:
    """获取全局 PipelineConfig 实例。"""
    return _pipeline_config
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一配置管理模块
"""

import os
import sqlite3
from pathlib import Path

import yaml


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_path=None):
        """
        初始化配置管理器

        Args:
            config_path: 配置文件路径，默认使用项目根目录的 config/config.yaml
        """
        self.project_root = self._detect_project_root(config_path)
        if config_path is None:
            config_path = self.project_root / "config" / "config.yaml"
        self.config_path = Path(config_path).expanduser().resolve()
        self._config = {}
        self._load_config()

    def _detect_project_root(self, config_path=None) -> Path:
        env_root = os.getenv("MEDIA_TOOLS_PROJECT_ROOT")
        if env_root:
            return Path(env_root).expanduser().resolve()

        if config_path:
            p = Path(config_path).expanduser().resolve()
            if p.name.endswith(".yaml"):
                return p.parent.parent
            return p.parent

        cwd = Path.cwd().resolve()
        for candidate in [cwd, *cwd.parents]:
            if (candidate / "config" / "config.yaml").exists():
                return candidate
            if (candidate / "pyproject.toml").exists():
                return candidate
        return cwd

    def _load_config(self):
        """加载配置文件"""
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
        else:
            self._config = {}

    def reload(self):
        """重新加载配置"""
        self._load_config()

    def get(self, key, default=None):
        """
        获取配置值

        Args:
            key: 配置键，支持点号分隔的嵌套键，如 'download.path'
            default: 默认值

        Returns:
            配置值
        """
        keys = key.split(".")
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key, value):
        """
        设置配置值（仅内存，不写入文件）

        Args:
            key: 配置键
            value: 配置值
        """
        keys = key.split(".")
        config = self._config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def save(self, config_path=None):
        """
        保存配置到文件

        Args:
            config_path: 保存路径，默认使用初始化时的路径
        """
        save_path = Path(config_path) if config_path else self.config_path
        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, "w", encoding="utf-8") as f:
            yaml.dump(self._config, f, allow_unicode=True, default_flow_style=False)

    def has_cookie(self):
        cookie = self.get("douyin.cookie") or self.get("cookie")
        return bool(cookie) and len(cookie.strip()) > 0

    def get_cookie(self):
        return self.get("douyin.cookie") or self.get("cookie", "")

    def get_download_path(self):
        """获取下载路径"""
        path = self.get("download.path") or self.get("download_path")
        if path:
            return Path(path).expanduser()

        return self.project_root / "data" / "downloads"

    def get_db_path(self):
        """获取数据库路径"""
        path = self.get("database.path")
        if path:
            return Path(path).expanduser()

        return self.project_root / "data" / "media_tools.db"

    def get_naming(self):
        """获取文件命名格式"""
        return self.get("naming", "{desc}_{aweme_id}")

    def is_auto_transcribe(self):
        """获取是否开启自动转写（委托到 SystemSettings 表）。"""
        try:
            from media_tools.core.config import get_runtime_setting_bool
            return get_runtime_setting_bool("auto_transcribe", False)
        except (ImportError, OSError, sqlite3.Error):
            # fallback 到 config.yaml（兼容旧代码）
            val = self.get("auto_transcribe", False)
            if isinstance(val, str):
                return val.lower() in ('true', '1', 'yes')
            return bool(val)

    def is_auto_delete_video(self):
        """获取是否开启转写成功后自动删除视频（委托到 SystemSettings 表）。"""
        try:
            from media_tools.core.config import get_runtime_setting_bool
            return get_runtime_setting_bool("auto_delete", True)
        except (ImportError, OSError, sqlite3.Error):
            # fallback 到 config.yaml（兼容旧代码）
            val = self.get("auto_delete_video", True)
            if isinstance(val, str):
                return val.lower() in ('true', '1', 'yes')
            return bool(val)

    def get_api_key(self):
        """获取 API 认证密钥（可选）"""
        return self.get("api_key", "")



    def validate(self):
        """
        验证配置是否完整

        Returns:
            (is_valid, errors) 元组
        """
        errors = []

        # 检查配置文件是否存在
        if not self.config_path.exists():
            errors.append(f"配置文件不存在: {self.config_path}")
            return False, errors

        # 检查 Cookie
        if not self.has_cookie():
            errors.append("未配置 Cookie，请运行登录功能获取")

        # 检查下载路径
        download_path = self.get_download_path()
        if not download_path.exists():
            try:
                download_path.mkdir(parents=True, exist_ok=True)
            except (OSError, PermissionError) as e:
                errors.append(f"无法创建下载目录: {e}")

        return len(errors) == 0, errors


# 全局配置实例（单例模式）
_config_instance = None


def get_config(config_path=None):
    """
    获取全局配置实例

    Args:
        config_path: 配置文件路径

    Returns:
        ConfigManager 实例
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigManager(config_path)
    return _config_instance


def reset_config():
    """重置配置实例（用于测试）"""
    global _config_instance
    _config_instance = None
    try:
        from media_tools.core.config import reset_config_cache
        reset_config_cache()
    except ImportError:
        pass

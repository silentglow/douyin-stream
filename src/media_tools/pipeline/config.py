from __future__ import annotations
"""Pipeline 配置管理 — 委托给统一配置系统。"""

from media_tools.core.config import get_app_config, AppConfig

__all__ = ["AppConfig", "load_pipeline_config"]


def load_pipeline_config() -> AppConfig:
    """加载 Pipeline 配置（从统一配置系统）。"""
    return get_app_config()

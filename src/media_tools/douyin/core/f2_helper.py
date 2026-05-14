#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
F2 辅助模块 - 统一管理 F2 配置和初始化
"""

import f2
import logging

logger = logging.getLogger(__name__)
from f2.utils.conf_manager import ConfigManager

from .config_mgr import get_config


def _disable_f2_bark_notifications() -> None:
    """关闭 F2 的 Bark 推送，避免无关网络请求和噪音日志。"""
    try:
        from f2.apps.bark.utils import ClientConfManager as BarkClientConfManager

        BarkClientConfManager.enable_bark = classmethod(lambda cls: False)
    except (ImportError, ModuleNotFoundError, AttributeError):
        pass


def _disable_f2_logging() -> None:
    """优化 F2 库的日志输出策略。
    
    策略：
    1. 保留 WARNING 及以上级别日志（用于记录异常和错误）
    2. 移除 F2 默认的文件 handler（避免产生大量空的 f2-trace-*.log 文件）
    3. 允许日志向上传播到根日志器（便于统一管理和输出）
    """
    f2_logger = logging.getLogger('f2')
    # 设置为 INFO 级别，保留 HTTP 请求等下载活动日志
    f2_logger.setLevel(logging.INFO)
    
    # 移除 F2 默认添加的文件 handler（这些会产生大量空的 f2-trace-*.log 文件）
    for handler in list(f2_logger.handlers):
        # 只移除文件 handler，保留其他类型的 handler
        if isinstance(handler, logging.FileHandler):
            f2_logger.removeHandler(handler)
    
    # 允许日志向上传播到父日志器，这样可以统一管理日志输出
    f2_logger.propagate = True


_disable_f2_bark_notifications()
_disable_f2_logging()


def merge_f2_config(main_conf: dict, custom_conf: dict) -> dict:
    """
    合并 F2 配置

    Args:
        main_conf: F2 默认配置
        custom_conf: 自定义配置

    Returns:
        合并后的配置
    """
    result = (main_conf or {}).copy()
    for key, value in (custom_conf or {}).items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key].update(value)
        else:
            result[key] = value
    return result


def get_f2_kwargs() -> dict:
    """
    获取 F2 所需的配置参数

    Returns:
        F2 配置字典
    """
    config = get_config()

    from media_tools.core.cookie_manager import get_cookie_manager
    cookie = get_cookie_manager().get_cookie("douyin")
    if not cookie:
        cookie = config.get_cookie()

    # 加载 F2 默认配置
    try:
        main_conf_manager = ConfigManager(f2.F2_CONFIG_FILE_PATH)
        all_conf = main_conf_manager.config
        main_conf = all_conf.get("douyin", {}) if all_conf else {}
    except (OSError, KeyError, TypeError):
        main_conf = {}

    # 自定义配置
    custom_conf = {
        "cookie": cookie,
        "path": str(config.get_download_path()),
    }

    # 合并配置
    kwargs = merge_f2_config(main_conf, custom_conf)

    # 添加必要参数
    kwargs["app_name"] = "douyin"
    kwargs["mode"] = "post"
    kwargs["path"] = str(config.get_download_path())

    # 让 F2 生成更短的临时文件名，避免超长标题在下载阶段触发路径问题。
    # 最终展示名会在本地重命名流程里恢复为可读标题。
    kwargs["naming"] = "{aweme_id}"

    # 显式使用全量抓取，避免 F2 打印“未提供日期区间参数”并误触发日期过滤。
    kwargs["interval"] = kwargs.get("interval") or "all"

    # 默认略微放宽超时时间，减少 HEAD/GET 抖动导致的误报失败。
    try:
        current_timeout = int(kwargs.get("timeout") or 0)
    except (TypeError, ValueError):
        current_timeout = 0
    kwargs["timeout"] = max(current_timeout, 20)

    # 确保 headers 存在
    if not kwargs.get("headers"):
        kwargs["headers"] = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.douyin.com/",
        }

    return kwargs


import datetime


class StructuredLogger:
    """结构化日志记录器 - 添加时间戳、图标和阶段标识"""
    
    _stage_icons = {
        "list": "📋",
        "fetching": "📋",
        "audit": "✔️",
        "auditing": "✔️",
        "download": "⬇️",
        "downloading": "⬇️",
        "transcribe": "✍️",
        "transcribing": "✍️",
        "export": "📤",
        "exporting": "📤",
        "done": "✅",
        "completed": "✅",
        "success": "✅",
        "failed": "❌",
        "error": "❌",
        "cancel": "🚫",
        "cancelled": "🚫",
    }
    
    _type_icons = {
        "info": "ℹ️",
        "success": "✅",
        "warning": "⚠️",
        "error": "❌",
        "debug": "🔧",
    }
    
    @classmethod
    def _get_timestamp(cls) -> str:
        """获取格式化的时间戳"""
        return datetime.datetime.now().strftime("%H:%M:%S")
    
    @classmethod
    def _get_stage_icon(cls, stage: str) -> str:
        """获取阶段图标"""
        return cls._stage_icons.get(stage.lower(), "📦")
    
    @classmethod
    def log(cls, message: str, stage: str = "", log_type: str = "info") -> None:
        """记录结构化日志"""
        timestamp = cls._get_timestamp()
        type_icon = cls._type_icons.get(log_type.lower(), "ℹ️")
        stage_icon = cls._get_stage_icon(stage) if stage else ""
        
        if stage:
            log_message = f"[{timestamp}] {type_icon} {stage_icon} {stage.upper():<12} - {message}"
        else:
            log_message = f"[{timestamp}] {type_icon} {message}"
        
        if log_type.lower() == "error":
            logger.error(log_message)
        elif log_type.lower() == "warning":
            logger.warning(log_message)
        elif log_type.lower() == "debug":
            logger.debug(log_message)
        else:
            logger.info(log_message)
    
    @classmethod
    def info(cls, message: str, stage: str = "") -> None:
        cls.log(message, stage, "info")
    
    @classmethod
    def success(cls, message: str, stage: str = "") -> None:
        cls.log(message, stage, "success")
    
    @classmethod
    def warning(cls, message: str, stage: str = "") -> None:
        cls.log(message, stage, "warning")
    
    @classmethod
    def error(cls, message: str, stage: str = "") -> None:
        cls.log(message, stage, "error")
    
    @classmethod
    def debug(cls, message: str, stage: str = "") -> None:
        cls.log(message, stage, "debug")


def _is_interactive_terminal() -> bool:
    """检测当前是否在交互式终端中运行。

    交互式终端：用户直接在前台运行，支持 Rich 的动态刷新。
    非交互式终端：后台服务（uvicorn）、管道、重定向输出等，
                  Rich Live 的终端控制序列会产生空行干扰。
    """
    import sys
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _patch_f2_console_for_non_interactive() -> None:
    """非交互式终端环境下，将 F2 的 rich console 输出重定向到日志系统。

    F2 使用 rich_console.print(Rule(...)) 输出"处理第 X 页"等分隔线，
    Rule 带有上下边距，在 uvicorn 日志环境中会产生大量空行。
    通过替换 Console，将输出捕获并转发到 Python logging，同时过滤空行。
    """
    if _is_interactive_terminal():
        return

    try:
        import io
        from rich.console import Console
        from f2.cli.cli_console import RichConsoleManager

        class LogConsole(Console):
            """将 Rich print 输出重定向到 Python logging，过滤空行。"""

            def __init__(self, *args, **kwargs):
                self._log_buffer = io.StringIO()
                super().__init__(
                    file=self._log_buffer,
                    force_terminal=False,
                    width=120,
                    *args,
                    **kwargs,
                )

            def print(self, *args, **kwargs):
                super().print(*args, **kwargs)
                value = self._log_buffer.getvalue()
                if value:
                    for line in value.rstrip("\n").splitlines():
                        stripped = line.strip()
                        # 跳过纯分隔线和空行
                        if not stripped or set(stripped) <= {"─", "━", "═", "─"}:
                            continue
                        # 去掉行首行尾的分隔符，提取核心内容
                        cleaned = stripped.strip("─━═─ ")
                        if cleaned:
                            logger.info(f"[F2] {cleaned}")
                    self._log_buffer.truncate(0)
                    self._log_buffer.seek(0)

        # 替换 RichConsoleManager 的 rich_console property
        original_property = RichConsoleManager.rich_console

        @property
        def patched_rich_console(self):
            return LogConsole()

        RichConsoleManager.rich_console = patched_rich_console
        logger.debug("已重定向 F2 Console 输出到日志系统（非交互式终端）")

    except Exception as e:
        logger.debug(f"Failed to patch F2 console output: {e}")


def _patch_f2_live_for_non_interactive() -> None:
    """非交互式终端环境下，禁用 F2 的 rich.live 动态刷新。

    保留 Progress 进度条和 Console 输出，只禁用 Live 的终端控制序列，
    避免在 uvicorn 日志环境中产生大量空行。
    """
    if _is_interactive_terminal():
        return

    try:
        from rich import live

        def noop_refresh(self, *args, **kwargs):
            return

        def noop_update(self, renderable=None, *args, **kwargs):
            return

        live.Live.refresh = noop_refresh
        live.Live.update = noop_update
        logger.debug("已禁用 F2 Live 动态刷新（非交互式终端）")

    except Exception as e:
        logger.debug(f"Failed to patch F2 live output: {e}")


def _clean_f2_trace_logs(max_age_days: int = 7) -> None:
    """清理超过指定天数的 f2-trace-*.log 文件。

    F2 默认会创建 f2-trace-*.log 文件，即使内容为空。
    定期清理避免文件堆积。

    Args:
        max_age_days: 保留最近几天的日志，默认 7 天
    """
    import os
    import time
    from pathlib import Path

    try:
        cutoff = time.time() - max_age_days * 86400
        cleaned = 0

        # 常见路径：当前目录、用户主目录、临时目录
        search_paths = [
            Path.cwd(),
            Path.home(),
            Path(os.environ.get("TMPDIR", "/tmp")),
            Path(os.environ.get("TEMP", "/tmp")),
        ]

        for base_path in search_paths:
            if not base_path.exists():
                continue
            for log_file in base_path.glob("f2-trace-*.log"):
                try:
                    if log_file.stat().st_mtime < cutoff:
                        log_file.unlink()
                        cleaned += 1
                except (OSError, PermissionError):
                    continue

        if cleaned:
            logger.debug(f"清理了 {cleaned} 个过期 f2-trace 日志文件")

    except Exception as e:
        logger.debug(f"清理 f2-trace 日志失败: {e}")


_patch_f2_console_for_non_interactive()
_patch_f2_live_for_non_interactive()
_clean_f2_trace_logs()

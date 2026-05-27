#!/usr/bin/env python3
"""
统一日志系统 - 为整个项目提供日志记录功能

功能：
- 分级日志（DEBUG/INFO/WARNING/ERROR）
- 彩色终端输出
- 文件持久化
- 日志轮转（自动清理旧日志）
- 结构化 JSON 日志（通过配置系统启用）
- 性能追踪
- 日志上下文注入（request_id/task_id/creator_uid）

配置来源：
- AppConfig.log_level: 日志级别
- AppConfig.log_json_format: 是否使用 JSON 格式
"""

import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.logging import RichHandler

console = Console()

# ANSI 颜色转义码正则（用于文件日志自动过滤颜色）
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _inject_logging_context(payload: dict[str, Any]) -> None:
    """将 logging_context 中的字段（request_id / task_id / creator_uid）注入 payload。"""
    try:
        from media_tools.core.logging_context import get_logging_context

        ctx = get_logging_context()
        if ctx:
            payload.update(ctx)
    except (ImportError, ModuleNotFoundError):
        pass


class StripAnsiFormatter(logging.Formatter):
    """文件日志 formatter：自动过滤 ANSI 颜色代码，避免日志文件出现 [92m 等转义码。"""

    def format(self, record: logging.LogRecord) -> str:
        s = super().format(record)
        return _ANSI_RE.sub("", s)


class AnsiStripFilter(logging.Filter):
    """在 handler 层清洗 ANSI 码，确保所有 logger（包括 get_logger 返回的原生 Logger）都生效。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg and isinstance(record.msg, str):
            record.msg = _ANSI_RE.sub("", record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _ANSI_RE.sub("", str(v)) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(_ANSI_RE.sub("", str(v)) if isinstance(v, str) else v for v in record.args)
        return True


class JsonFormatter(logging.Formatter):
    """JSON 结构化日志 formatter，便于日志采集系统解析。"""

    # LogRecord 内部字段集合，用于过滤 extra 字段
    _RESERVED_ATTRS: frozenset[str] = frozenset(
        {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "asctime",
            "taskName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": _ANSI_RE.sub("", str(record.getMessage())),
        }
        _inject_logging_context(payload)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info
        # 支持额外字段
        for key, value in record.__dict__.items():
            if key not in self._RESERVED_ATTRS:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


class StructuredFormatter(JsonFormatter):
    """结构化 JSON 日志 formatter，JsonFormatter 的别名。

    保留向后兼容性，新代码应直接使用 JsonFormatter。
    """


class MediaLogger:
    """统一日志管理器"""

    def __init__(
        self,
        name: str = "media_tools",
        log_dir: Path = Path("logs"),
        level: int = logging.INFO,
        json_logs: bool = False,
    ):
        self.name = name
        self.log_dir = log_dir
        self.json_logs = json_logs

        # 确保日志目录存在
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 创建logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

        # 避免重复添加handler
        if not self.logger.handlers:
            self._setup_handlers()

    def _setup_handlers(self):
        """配置日志handler"""
        # 全局 ANSI 清洗 filter，挂在根 logger 上，所有子 logger 自动生效
        self.logger.addFilter(AnsiStripFilter())

        # 1. 终端输出（Rich）
        rich_handler = RichHandler(
            console=console,
            show_time=True,
            show_level=True,
            show_path=False,
            markup=False,
        )
        rich_handler.setLevel(logging.INFO)
        rich_handler.setFormatter(StripAnsiFormatter("%(message)s", datefmt="[%X]"))
        self.logger.addHandler(rich_handler)

        # 2. 文件输出（过滤 ANSI 颜色代码）
        log_file = self.log_dir / f"media_tools_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            StripAnsiFormatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        )
        self.logger.addHandler(file_handler)

        # 3. 错误文件输出（过滤 ANSI 颜色代码）
        error_file = self.log_dir / f"error_{datetime.now().strftime('%Y%m%d')}.log"
        error_handler = logging.FileHandler(error_file, encoding="utf-8")
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(StripAnsiFormatter("%(asctime)s [ERROR] %(name)s\n%(message)s\n%(exc_info)s\n"))
        self.logger.addHandler(error_handler)

        # 4. JSON 结构化日志（可选，通过环境变量 MEDIA_TOOLS_JSON_LOGS=1 启用）
        if self.json_logs:
            json_file = self.log_dir / f"media_tools_{datetime.now().strftime('%Y%m%d')}.jsonl"
            json_handler = logging.FileHandler(json_file, encoding="utf-8")
            json_handler.setLevel(logging.DEBUG)
            json_handler.setFormatter(JsonFormatter())
            self.logger.addHandler(json_handler)

    def _clean_msg(self, message: str) -> str:
        """清理消息中的 ANSI 颜色代码（由 AnsiStripFilter 在 handler 层统一处理，此方法保留兼容）。"""
        if message is None:
            return ""
        return _ANSI_RE.sub("", message)

    def debug(self, message: str = "", *args, **kwargs):
        """DEBUG级别日志"""
        self.logger.debug(message, *args, **kwargs)

    def info(self, message: str = "", *args, **kwargs):
        """INFO级别日志"""
        self.logger.info(message, *args, **kwargs)

    def warning(self, message: str = "", *args, **kwargs):
        """WARNING级别日志"""
        self.logger.warning(message, *args, **kwargs)

    def error(self, message: str = "", *args, exc_info=False, **kwargs):
        """ERROR级别日志"""
        self.logger.error(message, *args, exc_info=exc_info, **kwargs)

    def critical(self, message: str = "", *args, **kwargs):
        """CRITICAL级别日志"""
        self.logger.critical(message, *args, **kwargs)

    def exception(self, message: str = "", *args, **kwargs):
        """异常日志（自动包含堆栈信息）"""
        self.logger.exception(message, *args, **kwargs)

    def log_operation(
        self,
        operation: str,
        status: str,
        details: str = "",
        duration: float = 0,
    ):
        """记录操作日志（格式化）

        Args:
            operation: 操作名称
            status: 状态 (success/failed/warning)
            details: 详细信息
            duration: 耗时（秒）
        """
        icon = {
            "success": "✅",
            "failed": "❌",
            "warning": "⚠️",
            "running": "🔄",
        }.get(status.lower(), "📝")

        msg = f"{icon} {operation}"
        if details:
            msg += f" - {details}"
        if duration > 0:
            msg += f" ({duration:.1f}s)"

        if status.lower() == "success":
            self.info(msg)
        elif status.lower() == "failed":
            self.error(msg)
        elif status.lower() == "warning":
            self.warning(msg)
        else:
            self.info(msg)


# 全局日志实例
_logger: MediaLogger | None = None


def get_logger(name: str = "media_tools") -> logging.Logger:
    global _logger
    if _logger is None:
        init_logging()
    if name == "media_tools":
        return logging.getLogger("media_tools")
    # 确保子 logger 挂在 media_tools 层级下，才能继承已配置的 handlers
    if not name.startswith("media_tools."):
        name = f"media_tools.{name}"
    child = logging.getLogger(name)
    child.setLevel(logging.DEBUG)
    child.propagate = True
    return child


def init_logging(
    level: str | None = None,
    log_dir: Path | None = None,
) -> MediaLogger:
    global _logger

    _is_test = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ

    try:
        from media_tools.core.config import get_app_config

        config = get_app_config()

        if level is None:
            level = config.log_level

        if log_dir is None:
            log_dir = config.project_root / "data" / "logs"
    except ImportError:
        if level is None:
            level = os.environ.get("LOG_LEVEL", os.environ.get("MEDIA_TOOLS_LOG_LEVEL", "INFO"))

        if log_dir is None:
            log_dir = Path("data/logs")

    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }

    json_logs = not _is_test and os.environ.get("MEDIA_TOOLS_JSON_LOGS", "1").lower() in ("1", "true", "yes")
    structured = not _is_test and _should_use_structured_logging(level)

    _logger = MediaLogger(
        name="media_tools",
        log_dir=log_dir,
        level=level_map.get(level.upper(), logging.INFO),
        json_logs=json_logs,
    )

    if _is_test:
        for handler in list(_logger.logger.handlers):
            if isinstance(handler, logging.FileHandler):
                _logger.logger.removeHandler(handler)
                handler.close()

    if structured:
        setup_structured_logging(level)

    _logger.info(f"日志系统初始化完成 (级别: {level}, JSON日志: {json_logs}, 结构化: {structured})")
    return _logger


def setup_structured_logging(level: str = "INFO") -> None:
    """将所有 handler 切换为 JSON 结构化输出。

    调用后，控制台和文件日志统一输出 JSON 行格式，适用于日志采集系统。
    可在应用启动时显式调用，也可通过 MEDIA_TOOLS_LOG_FORMAT=json 环境变量自动启用。

    Args:
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
    """
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    log_level = level_map.get(level.upper(), logging.INFO)

    formatter = StructuredFormatter()

    root = logging.getLogger("media_tools")
    root.setLevel(log_level)
    for handler in root.handlers:
        handler.setFormatter(formatter)


def _should_use_structured_logging(level: str = "INFO") -> bool:
    """检查是否启用结构化 JSON 日志。

    优先级：配置系统 > 环境变量
    """
    # 优先从配置系统读取
    try:
        from media_tools.core.config import get_app_config

        config = get_app_config()
        return config.log_json_format
    except ImportError:
        # 配置系统尚未初始化时使用环境变量
        return os.environ.get("MEDIA_TOOLS_LOG_FORMAT", "").lower() == "json"


def main():
    """测试日志系统"""

    # 初始化
    logger = init_logging(level="DEBUG")

    # 测试各级别日志
    logger.debug("这是一条DEBUG日志")
    logger.info("这是一条INFO日志")
    logger.warning("这是一条WARNING日志")
    logger.error("这是一条ERROR日志")

    # 测试操作日志
    logger.log_operation("下载视频", "success", "video_001.mp4", 2.5)
    logger.log_operation("转写视频", "failed", "配额不足", 1.2)
    logger.log_operation("检查更新", "warning", "网络延迟", 5.0)

    # 测试异常日志
    try:
        raise ValueError("测试异常")
    except ValueError:
        logger.exception("捕获到异常")

    logger.info("日志系统测试完成")
    logger.info(f"日志文件保存在: {logger.log_dir}")


if __name__ == "__main__":
    main()

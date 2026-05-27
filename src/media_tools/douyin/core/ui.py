#!/usr/bin/env python3
"""
终端美化输出模块 - 提供统一的颜色、进度条、表格等 UI 组件
"""

import logging
import sys
from datetime import datetime

from rich.console import Console

console = Console(no_color=True)
_logger = logging.getLogger("media_tools.douyin.ui")


class Colors:
    """终端颜色代码"""

    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"

    # 背景色
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"


def _supports_color():
    """检测终端是否支持颜色"""
    return bool(hasattr(sys.stdout, "isatty") and sys.stdout.isatty())


_SUPPORTS_COLOR = _supports_color()


def _colorize(text, color_code):
    """应用颜色代码"""
    if _SUPPORTS_COLOR:
        return f"{color_code}{text}{Colors.RESET}"
    return text


def success(text):
    """成功消息（绿色）"""
    return _colorize(f"✓ {text}", Colors.GREEN)


def error(text):
    """错误消息（红色）"""
    return _colorize(f"✗ {text}", Colors.RED)


def warning(text):
    """警告消息（黄色）"""
    return _colorize(f"⚠ {text}", Colors.YELLOW)


def info(text):
    """信息消息（蓝色）"""
    return _colorize(text, Colors.BLUE)


def header(text):
    """标题（粗体+青色）"""
    return _colorize(text, Colors.BOLD + Colors.CYAN)


def dim(text):
    """暗淡文本"""
    return _colorize(text, Colors.DIM)


def bold(text):
    """粗体文本"""
    return _colorize(text, Colors.BOLD)


def separator(char="=", length=60):
    """分隔线"""
    return char * length


def print_header(title):
    """打印标题头"""
    width = 60
    _logger.info("")
    _logger.info(separator("=", width))
    _logger.info(f"  {title}")
    _logger.info(separator("=", width))
    _logger.info("")


def print_menu(items):
    """
    打印菜单选项

    Args:
        items: 列表，每个元素为 (key, description) 元组
    """
    for key, desc in items:
        console.print(f"  {bold(key)}. {desc}")
    console.print()


def print_table(headers, rows):
    """
    打印简单表格

    Args:
        headers: 表头列表
        rows: 数据行列表，每行是列表
    """
    # 计算每列宽度
    col_widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))

    # 打印表头
    header_line = "  ".join(str(h).ljust(col_widths[i]) for i, h in enumerate(headers))
    console.print(bold(header_line))
    console.print(separator("-", sum(col_widths) + 2 * len(col_widths)))

    # 打印数据行
    for row in rows:
        line = "  ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
        console.print(line)


class ProgressBar:
    """简易进度条"""

    def __init__(self, total, desc="进度"):
        self.total = total
        self.current = 0
        self.desc = desc
        self.bar_width = 40

    def update(self, n=1):
        """更新进度"""
        self.current += n
        self._render()

    def _render(self):
        """渲染进度条"""
        percent = 100 if self.total == 0 else self.current / self.total * 100

        filled = int(self.bar_width * self.current / self.total) if self.total > 0 else self.bar_width
        bar = "█" * filled + "░" * (self.bar_width - filled)

        # 移动到行首
        sys.stdout.write("\r")
        sys.stdout.write(f"  {self.desc}: [{bar}] {self.current}/{self.total} ({percent:.1f}%)")
        sys.stdout.flush()

    def finish(self):
        """完成"""
        self.current = self.total
        self._render()
        sys.stdout.write("\n")


def print_status(status, message):
    """打印状态信息"""
    status_map = {
        "success": (success, "✓"),
        "error": (error, "✗"),
        "warning": (warning, "⚠"),
        "info": (info, "ℹ"),
    }

    func, icon = status_map.get(status, (info, "ℹ"))
    console.print(f"  {func(f'{icon} {message}')}")


def print_key_value(key, value, indent=2):
    """打印键值对"""
    prefix = " " * indent
    console.print(f"{prefix}{bold(key)}: {value}")


def print_countdown(seconds, message="开始"):
    """倒计时"""
    for i in range(seconds, 0, -1):
        sys.stdout.write("\r")
        sys.stdout.write(f"  {i} 秒后{message}... (按 Ctrl+C 取消)")
        sys.stdout.flush()
        import time

        time.sleep(1)
    sys.stdout.write("\n")


def format_size(bytes_size):
    """格式化文件大小"""
    if bytes_size < 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"


def format_number(num):
    """格式化数字"""
    if num is None:
        return "0"
    if num >= 100000000:
        return f"{num / 100000000:.1f}亿"
    if num >= 10000:
        return f"{num / 10000:.1f}万"
    return str(num)


def format_duration(seconds):
    """格式化时长"""
    if seconds < 60:
        return f"{seconds}秒"
    if seconds < 3600:
        return f"{seconds // 60}分{seconds % 60}秒"
    return f"{seconds // 3600}时{(seconds % 3600) // 60}分"


def print_footer(text=""):
    """打印脚注"""
    console.print()
    console.print(dim(separator("=", 60)))
    if text:
        console.print(dim(text))
    console.print(dim(f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    console.print()

from __future__ import annotations
"""临时文件安全管理"""

import atexit
import os
import signal
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional, Union

from media_tools.logger import get_logger

logger = get_logger("bilibili")

_temp_files: set[str] = set()
_temp_files_lock = threading.Lock()


def _cleanup_temp_files() -> None:
    """进程退出时清理所有临时文件"""
    with _temp_files_lock:
        for path_str in list(_temp_files):
            try:
                if os.path.exists(path_str):
                    os.unlink(path_str)
                    logger.debug(f"Cleaned up temp file: {path_str}")
            except (OSError, PermissionError) as e:
                logger.warning(f"Failed to cleanup temp file {path_str}: {e}")
        _temp_files.clear()


def _register_temp_file(path_str: str) -> None:
    """注册临时文件到清理列表"""
    with _temp_files_lock:
        _temp_files.add(path_str)


def _unregister_temp_file(path_str: str) -> None:
    """从清理列表移除（已清理时调用）"""
    with _temp_files_lock:
        _temp_files.discard(path_str)


def _cleanup_on_signal(signum, frame) -> None:
    """信号处理时清理临时文件"""
    _cleanup_temp_files()
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


# 注册进程退出清理
atexit.register(_cleanup_temp_files)
if hasattr(signal, 'SIGTERM'):
    signal.signal(signal.SIGTERM, _cleanup_on_signal)
signal.signal(signal.SIGINT, _cleanup_on_signal)


@contextmanager
def managed_temp_file(mode: str = 'w', suffix: str = '.txt', dir: Optional[str] = None) -> Generator[tuple, None, None]:
    """安全的临时文件上下文管理器"""
    import io
    fd, path = tempfile.mkstemp(suffix=suffix, prefix='bili_tmp_', dir=dir)
    _register_temp_file(path)
    try:
        os.close(fd)
        os.chmod(path, 0o600)
        handle = io.open(path, mode, newline='')
        yield handle, path
    finally:
        try:
            if not handle.closed:
                handle.close()
            if os.path.exists(path):
                os.unlink(path)
        except (OSError, PermissionError):
            pass
        _unregister_temp_file(path)

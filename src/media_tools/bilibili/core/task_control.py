from __future__ import annotations
"""下载任务取消/暂停控制"""

import os
import signal
import subprocess
import threading

from media_tools.logger import get_logger

logger = get_logger("bilibili")

_pause_controllers: dict[str, "PauseController"] = {}
_pause_lock = threading.Lock()

# 全局取消标志（用于库内调用的 yt-dlp，无法通过 subprocess 信号中断）
_cancel_flags: dict[str, threading.Event] = {}
_cancel_flags_lock = threading.Lock()


def register_cancel_flag(task_id: str) -> threading.Event:
    """为 task_id 注册一个线程安全的取消标志"""
    event = threading.Event()
    with _cancel_flags_lock:
        _cancel_flags[task_id] = event
    return event


def cancel_download(task_id: str) -> None:
    """标记 task_id 对应的下载为取消"""
    with _cancel_flags_lock:
        flag = _cancel_flags.get(task_id)
        if flag:
            flag.set()


def unregister_cancel_flag(task_id: str) -> None:
    """清理取消标志"""
    with _cancel_flags_lock:
        _cancel_flags.pop(task_id, None)


class PauseController:
    """暂停控制器，支持暂停/恢复下载"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._paused = threading.Event()
        self._paused.set()  # 初始不暂停
        self._cancelled = threading.Event()
        self._process: subprocess.Popen | None = None

    def pause(self):
        """暂停下载"""
        self._paused.clear()
        if self._process and self._process.poll() is None:
            try:
                if hasattr(signal, 'SIGSTOP'):
                    self._process.send_signal(signal.SIGSTOP)
                logger.info(f"Task {self.task_id} paused")
            except (OSError, ProcessLookupError) as e:
                logger.warning(f"Failed to pause task {self.task_id}: {e}")

    def resume(self):
        """恢复下载"""
        self._paused.set()
        if self._process and self._process.poll() is None:
            try:
                if hasattr(signal, 'SIGCONT'):
                    self._process.send_signal(signal.SIGCONT)
                logger.info(f"Task {self.task_id} resumed")
            except (OSError, ProcessLookupError) as e:
                logger.warning(f"Failed to resume task {self.task_id}: {e}")

    def cancel(self):
        """取消下载"""
        self._cancelled.set()
        self._paused.set()
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                logger.info(f"Task {self.task_id} cancelled")
            except (OSError, ProcessLookupError) as e:
                logger.warning(f"Failed to cancel task {self.task_id}: {e}")

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def check_pause(self):
        """检查是否需要暂停（阻塞直到恢复）"""
        self._paused.wait()

    def set_process(self, proc: subprocess.Popen):
        self._process = proc


def register_pause_controller(task_id: str) -> PauseController:
    with _pause_lock:
        controller = PauseController(task_id)
        _pause_controllers[task_id] = controller
        return controller


def get_pause_controller(task_id: str) -> PauseController | None:
    with _pause_lock:
        return _pause_controllers.get(task_id)


def unregister_pause_controller(task_id: str):
    with _pause_lock:
        _pause_controllers.pop(task_id, None)


def pause_task(task_id: str):
    """暂停指定任务"""
    controller = get_pause_controller(task_id)
    if controller:
        controller.pause()


def resume_task(task_id: str):
    """恢复指定任务"""
    controller = get_pause_controller(task_id)
    if controller:
        controller.resume()


def cancel_task_download(task_id: str):
    """取消指定任务的下载"""
    cancel_download(task_id)
    controller = get_pause_controller(task_id)
    if controller:
        controller.cancel()

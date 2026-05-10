from __future__ import annotations
"""Pipeline 状态管理器 - 负责断点续传"""
from typing import Optional, Union

import json
import logging
import os
import re
import time
from pathlib import Path

from .models import VideoState
from ..transcribe.runtime import ensure_dir

logger = logging.getLogger(__name__)

_SENSITIVE_PATTERNS = [
    re.compile(r'cookie:\s*\S+', re.IGNORECASE),
    re.compile(r'tongyi_sso_ticket=\S+', re.IGNORECASE),
    re.compile(r'tongyi_guest_ticket=\S+', re.IGNORECASE),
    re.compile(r'tongyi_sso_ticket_hash=\S+', re.IGNORECASE),
    re.compile(r'authorization:\s*\S+', re.IGNORECASE),
    re.compile(r'x-xsrf-token:\s*\S+', re.IGNORECASE),
]


def _sanitize_error_message(message: str) -> str:
    if not message:
        return message
    sanitized = message
    for pattern in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized

DEFAULT_STATE_FILE = None  # Will use project root when None


class PipelineStateManager:
    """Pipeline 状态管理器 - 负责断点续传

    将每个视频的处理状态持久化到 JSON 文件，
    支持中断后从断点继续执行。
    """

    def __init__(self, state_file: Path | Optional[str] = DEFAULT_STATE_FILE):
        if state_file is None:
            from media_tools.core.config import get_project_root
            state_file = get_project_root() / ".pipeline_state.json"
        self.state_file = Path(state_file)
        self.states: dict[str, VideoState] = {}
        self._load()

    def _load(self) -> None:
        """从文件加载状态（跳过损坏条目而非丢弃全部）"""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                skipped = 0
                for path_str, state_data in data.items():
                    try:
                        self.states[path_str] = VideoState(**state_data)
                    except (TypeError, ValueError):
                        skipped += 1
                if skipped:
                    logger.warning(f"跳过 {skipped} 条损坏的状态记录")
                logger.info(f"已加载状态文件: {self.state_file} ({len(self.states)} 条记录)")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"加载状态文件失败，将创建新状态: {e}")
                self.states = {}
        else:
            logger.info(f"状态文件不存在，将创建新状态: {self.state_file}")

    def _save(self) -> None:
        """保存状态到文件（原子写入：先写临时文件再 rename）"""
        try:
            from dataclasses import asdict
            data = {path: asdict(state) for path, state in self.states.items()}
            ensure_dir(self.state_file.parent)
            tmp_file = self.state_file.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self.state_file)
            logger.debug(f"状态已保存到: {self.state_file}")
        except (OSError, TypeError, json.JSONDecodeError) as e:
            logger.error(f"保存状态文件失败: {e}")

    def get_state(self, video_path: Path) -> VideoState:
        key = str(video_path)
        if key not in self.states:
            self.states[key] = VideoState(video_path=str(video_path))
        return self.states[key]

    def update_state(
        self,
        video_path: Path,
        status: str,
        attempt: int = 0,
        max_attempts: int = 3,
        error_type: str = "",
        error_message: str = "",
        transcript_path: str = "",
    ) -> None:
        key = str(video_path)
        state = self.get_state(video_path)
        state.status = status
        state.attempt = attempt
        state.max_attempts = max_attempts

        if status == "running":
            state.started_at = time.time()
        elif status in ("success", "failed", "cancelled"):
            state.completed_at = time.time()
            if transcript_path:
                state.transcript_path = transcript_path
            if error_type:
                state.error_type = error_type
            if error_message:
                state.error_message = _sanitize_error_message(error_message)
            if status == "failed":
                state.last_error_time = time.time()

        self._save()

    def get_pending_videos(self, video_paths: list[Path]) -> list[Path]:
        """获取待处理的视频列表（排除已成功且无需重试的）"""
        pending = []
        needs_save = False
        for path in video_paths:
            state = self.get_state(path)
            if state.status == "running":
                state.status = "pending"
                needs_save = True
            if state.status == "success" and state.transcript_path:
                if Path(state.transcript_path).exists():
                    continue
                logger.warning(f"缓存的转录文件已丢失，重新加入队列: {path}")
                state.status = "pending"
                state.transcript_path = ""
                needs_save = True
            pending.append(path)
        if needs_save:
            self._save()
        return pending

    def clear_completed(self) -> int:
        """清除已成功的状态记录"""
        before = len(self.states)
        self.states = {k: v for k, v in self.states.items() if v.status != "success"}
        self._save()
        return before - len(self.states)

    def reset_all(self) -> None:
        """重置所有状态"""
        self.states = {}
        self._save()
        logger.info("已重置所有状态")

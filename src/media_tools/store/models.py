from enum import Enum


class VideoStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    FAILED = "failed"


class TranscriptStatus(str, Enum):
    NONE = "none"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PARTIAL_FAILED = "PARTIAL_FAILED"


# Backward compatibility mappings
VIDEO_STATUS_MAP = {s.value: i for i, s in enumerate(VideoStatus)}
TRANSCRIPT_STATUS_MAP = {s.value: i for i, s in enumerate(TranscriptStatus)}
TASK_STATUS_MAP = {s.value: i for i, s in enumerate(TaskStatus)}

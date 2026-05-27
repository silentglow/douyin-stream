from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BilibiliUrlKind(StrEnum):
    SPACE = "space"
    VIDEO = "video"
    SHORT = "short"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class NormalizedBilibiliUrl:
    kind: BilibiliUrlKind
    original_url: str
    mid: str | None = None
    bvid: str | None = None

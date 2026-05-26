from __future__ import annotations
from typing import Optional, Union

from dataclasses import dataclass
from enum import Enum


class BilibiliUrlKind(str, Enum):
    SPACE = "space"
    VIDEO = "video"
    SHORT = "short"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class NormalizedBilibiliUrl:
    kind: BilibiliUrlKind
    original_url: str
    mid: Optional[str] = None
    bvid: Optional[str] = None


from __future__ import annotations
from typing import Optional, Union

import re


def build_bilibili_creator_uid(mid: str) -> str:
    return f"bilibili:{mid}"


def build_bilibili_asset_id(bvid: str, p_index: Optional[int]) -> str:
    if p_index is None:
        return f"bilibili:{bvid}"
    return f"bilibili:{bvid}:p{p_index}"


def sanitize_filename(name: str) -> str:
    value = name or ""
    value = re.sub(r'[<>:"/\\|?*]', "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


from __future__ import annotations

from urllib.parse import urlparse

from .models import BilibiliUrlKind, NormalizedBilibiliUrl


def normalize_bilibili_url(url: str) -> NormalizedBilibiliUrl:
    raw = (url or "").strip()
    if not raw:
        return NormalizedBilibiliUrl(kind=BilibiliUrlKind.UNKNOWN, original_url=url)

    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = f"https://{raw}"

    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""

    if host in {"b23.tv", "www.b23.tv"}:
        return NormalizedBilibiliUrl(kind=BilibiliUrlKind.SHORT, original_url=raw)

    if host.endswith("bilibili.com"):
        if host == "space.bilibili.com":
            mid = path.strip("/").split("/")[0] if path.strip("/") else ""
            if mid.isdigit():
                return NormalizedBilibiliUrl(kind=BilibiliUrlKind.SPACE, original_url=raw, mid=mid)
            return NormalizedBilibiliUrl(kind=BilibiliUrlKind.UNKNOWN, original_url=raw)

        if path.startswith("/video/"):
            parts = path.split("/")
            bvid = parts[2] if len(parts) > 2 else ""
            if bvid.startswith("BV"):
                return NormalizedBilibiliUrl(kind=BilibiliUrlKind.VIDEO, original_url=raw, bvid=bvid)
            return NormalizedBilibiliUrl(kind=BilibiliUrlKind.UNKNOWN, original_url=raw)

    return NormalizedBilibiliUrl(kind=BilibiliUrlKind.UNKNOWN, original_url=raw)


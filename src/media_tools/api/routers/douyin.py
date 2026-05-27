from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/v1/douyin", tags=["douyin"], redirect_slashes=False)

_f2_import_error: Exception | None = None

try:
    from f2.apps.douyin.handler import DouyinHandler as _RealDouyinHandler
    from f2.apps.douyin.utils import SecUserIdFetcher as _RealSecUserIdFetcher

    DouyinHandler = _RealDouyinHandler
    SecUserIdFetcher = _RealSecUserIdFetcher
except BaseException as exc:  # pragma: no cover - depends on optional runtime dependency/network side effects
    if not isinstance(exc, Exception):
        raise
    _f2_import_error = exc

    class DouyinHandler:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            self._args = args
            self._kwargs = kwargs

        async def fetch_user_profile(self, *_args, **_kwargs):
            raise RuntimeError(f"f2 unavailable: {_f2_import_error}")

        async def fetch_user_post_videos(self, *_args, **_kwargs):
            raise RuntimeError(f"f2 unavailable: {_f2_import_error}")
            yield  # makes this an async generator so `async for` raises the RuntimeError above instead of TypeError

    class SecUserIdFetcher:  # type: ignore[no-redef]
        @staticmethod
        async def get_sec_user_id(*_args, **_kwargs):
            raise RuntimeError(f"f2 unavailable: {_f2_import_error}")


@router.get("/metadata")
async def get_metadata(
    url: str = Query(..., min_length=1, max_length=2048),
    max_counts: int = Query(10, ge=1, le=1000),
):
    try:
        from media_tools.douyin.core.f2_helper import get_f2_kwargs

        sec_user_id = await SecUserIdFetcher.get_sec_user_id(url)
        if not sec_user_id:
            raise HTTPException(status_code=400, detail="Invalid URL or unable to parse sec_user_id")

        kwargs = get_f2_kwargs()
        kwargs["url"] = url
        kwargs["timeout"] = min(int(kwargs.get("timeout") or 20), 10)

        handler = DouyinHandler(kwargs)
        user_profile = await handler.fetch_user_profile(sec_user_id)
        if not user_profile:
            raise HTTPException(status_code=404, detail="User profile not found")

        videos = []
        async for page in handler.fetch_user_post_videos(sec_user_id, max_counts=max_counts):
            if hasattr(page, "_to_list"):
                page_data = page._to_list()
                for video in page_data[:max_counts]:
                    aweme_id = str(video.get("aweme_id") or "")
                    cover_url = (
                        video.get("video", {}).get("cover", {}).get("url_list", [None])[0] or video.get("cover") or ""
                    )
                    videos.append(
                        {
                            "aweme_id": aweme_id,
                            "desc": video.get("desc", ""),
                            "create_time": video.get("create_time", 0),
                            "video_url": f"https://www.douyin.com/video/{aweme_id}",
                            "cover_url": cover_url,
                        }
                    )
                    if len(videos) >= max_counts:
                        break
            else:
                aweme_id = str(getattr(page, "aweme_id", "") or "")
                cover_url = ""
                cover = getattr(page, "video_play_addr", None)
                if isinstance(cover, dict):
                    cover_url = str(cover.get("cover") or "")
                videos.append(
                    {
                        "aweme_id": aweme_id,
                        "desc": getattr(page, "desc", "") or "",
                        "create_time": getattr(page, "create_time", 0) or 0,
                        "video_url": f"https://www.douyin.com/video/{aweme_id}",
                        "cover_url": cover_url,
                    }
                )
                if len(videos) >= max_counts:
                    break

        return {
            "creator": {
                "uid": getattr(user_profile, "uid", sec_user_id),
                "nickname": getattr(user_profile, "nickname", sec_user_id),
                "avatar": getattr(user_profile, "avatar_larger", ""),
            },
            "videos": videos[:max_counts],
        }
    except HTTPException:
        raise
    except (RuntimeError, OSError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))

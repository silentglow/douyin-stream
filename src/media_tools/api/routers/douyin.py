import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/douyin", tags=["douyin"], redirect_slashes=False)

logger = logging.getLogger(__name__)

_f2_import_error: Exception | None = None


class _UnavailableF2APIError(Exception):
    """占位异常：f2 不可用时不会被触发。"""


_f2_api_error: type[Exception] = _UnavailableF2APIError

try:
    from f2.apps.douyin.handler import DouyinHandler as _RealDouyinHandler
    from f2.apps.douyin.utils import SecUserIdFetcher as _RealSecUserIdFetcher
    from f2.exceptions.api_exceptions import APIError as _F2APIError

    DouyinHandler = _RealDouyinHandler
    SecUserIdFetcher = _RealSecUserIdFetcher
    _f2_api_error = _F2APIError
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


def _translate_f2_error(exc: Exception) -> HTTPException:
    """把 f2 / httpx 的底层异常翻译成对用户友好的 HTTP 错误。"""
    status_code = getattr(exc, "status_code", None)
    text = str(exc)

    if status_code == 403:
        return HTTPException(
            status_code=502,
            detail="抖音接口返回 403，Cookie 可能已失效或被风控拦截，请在设置中更新抖音 Cookie 后重试",
        )
    if status_code == 429:
        return HTTPException(status_code=429, detail="抖音接口请求过于频繁（429），请稍后再试")
    if status_code == 401:
        return HTTPException(status_code=502, detail="抖音接口鉴权失败（401），请更新抖音 Cookie")
    if status_code == 404:
        return HTTPException(status_code=404, detail="抖音接口未找到目标资源（404）")
    if status_code == 408:
        return HTTPException(status_code=504, detail="抖音接口请求超时（408），请稍后重试")
    if status_code == 503:
        return HTTPException(status_code=502, detail="抖音服务暂时不可用（503），请稍后重试")

    return HTTPException(status_code=502, detail=f"抖音接口请求失败：{text}")


class CookieCheckRequest(BaseModel):
    cookie_string: str | None = None
    account_id: str | None = None


def _resolve_douyin_cookie(cookie_string: str | None, account_id: str | None) -> tuple[str, str]:
    """确定要自检的 Cookie 及其来源。"""
    if cookie_string and cookie_string.strip():
        return cookie_string.strip(), "input"

    from media_tools.core.cookie_manager import get_cookie_manager
    from media_tools.douyin.core.config_mgr import get_config

    manager = get_cookie_manager()
    if account_id:
        cookie = manager.get_cookie("douyin", account_id=account_id)
        if not cookie:
            raise HTTPException(status_code=404, detail="抖音账号不存在或已停用")
        return cookie, "account"

    cookie = manager.get_cookie("douyin")
    if cookie:
        return cookie, "pool"

    cookie = get_config().get_cookie()
    if cookie:
        return cookie, "config"

    return "", "none"


@router.post("/cookie/check")
async def check_cookie(req: CookieCheckRequest | None = None):
    """抖音 Cookie 自检：判断当前 Cookie 是否仍然可用。"""
    from media_tools.douyin.core.cookie_check import check_douyin_cookie

    req = req or CookieCheckRequest()
    cookie, source = _resolve_douyin_cookie(req.cookie_string, req.account_id)
    result = await check_douyin_cookie(cookie)
    return {"status": "success", "source": source, "result": result.to_dict()}


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
    except _f2_api_error as e:
        # f2 的接口异常（403/429/超时等），翻译成友好的 HTTP 错误
        logger.warning("抖音 metadata 接口调用失败: %s", e)
        raise _translate_f2_error(e) from e
    except (RuntimeError, OSError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))

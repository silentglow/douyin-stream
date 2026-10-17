"""抖音 Cookie 自检。

用于判断一份抖音 Cookie 是否仍然可用，主要解决「Cookie 过期后接口返回 403，
但错误信息不直观」的问题。

判定分两步：

1. 结构检查（离线）：解析 Cookie 字符串，检查登录态与设备指纹相关的关键字段是否存在。
2. 登录态探测（在线）：请求抖音的 ``user/profile/self`` 接口，该接口直接返回当前
   Cookie 的登录状态，无需 ``sec_user_id``：
   - ``status_code == 0`` 且带 ``user``：Cookie 有效；
   - ``status_code == 8`` / ``用户未登录``：Cookie 已失效；
   - ``403`` / ``ArgusSecurityPlugin``：被风控拦截（设备指纹失效）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 登录态自检接口：直接反映当前 Cookie 的登录状态，无需 sec_user_id。
SELF_PROFILE_ENDPOINT = "https://www.douyin.com/aweme/v1/web/user/profile/self/"

# 判定登录态的关键字段（任一存在即可视为「有登录态」）。
_LOGIN_KEYS = ("sessionid", "sid_tt")
# 判定设备指纹的关键字段（任一存在即可）。
_DEVICE_KEYS = ("UIFID", "UIFID_TEMP", "ttwid")
# 建议存在但不强制（缺失通常仍可用）。
_RECOMMENDED_KEYS = ("msToken", "passport_csrf_token")

# 结果状态
STATUS_VALID = "valid"
STATUS_EXPIRED = "expired"
STATUS_BLOCKED = "blocked"
STATUS_MISSING = "missing"
STATUS_ERROR = "error"


@dataclass
class DouyinCookieCheckResult:
    """Cookie 自检结果。"""

    valid: bool
    status: str
    message: str
    http_status: int | None = None
    missing_keys: list[str] = field(default_factory=list)
    nickname: str = ""

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "status": self.status,
            "message": self.message,
            "http_status": self.http_status,
            "missing_keys": self.missing_keys,
            "nickname": self.nickname,
        }


def parse_cookie_keys(cookie: str) -> dict[str, str]:
    """把 Cookie 字符串解析为 ``{小写键: 值}`` 映射。"""
    result: dict[str, str] = {}
    for chunk in (cookie or "").split(";"):
        if "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        key = key.strip()
        if not key:
            continue
        result[key.lower()] = value.strip()
    return result


def inspect_cookie_structure(cookie: str) -> list[str]:
    """返回 Cookie 中缺失的关键字段列表（含建议字段）。"""
    keys = parse_cookie_keys(cookie)
    missing: list[str] = []
    if not any(k.lower() in keys for k in _LOGIN_KEYS):
        missing.append("sessionid")
    if not any(k.lower() in keys for k in _DEVICE_KEYS):
        missing.append("UIFID")
    for key in _RECOMMENDED_KEYS:
        if key.lower() not in keys:
            missing.append(key)
    return missing


def _has_login_state(cookie: str) -> bool:
    keys = parse_cookie_keys(cookie)
    return any(k.lower() in keys for k in _LOGIN_KEYS)


async def _probe_login_state(cookie: str, timeout: float) -> tuple[int, str]:
    """请求抖音登录态接口，返回 ``(http_status, body_text)``。"""
    from f2.apps.douyin.crawler import DouyinCrawler

    from media_tools.douyin.core.f2_helper import get_f2_kwargs

    kwargs = get_f2_kwargs()
    kwargs["cookie"] = cookie

    # 检查输入 Cookie 时，网关头必须来自这份 Cookie，而不是账号池当前 Cookie。
    # 否则检测新 Cookie 时可能被旧设备指纹干扰，结果不准确。
    headers = dict(kwargs.get("headers") or {})
    headers.pop("uifid", None)
    headers.pop("x-tt-argus", None)
    checked_cookie_values = parse_cookie_keys(cookie)
    checked_uifid = checked_cookie_values.get("uifid")
    if checked_uifid:
        headers["uifid"] = checked_uifid
        headers["x-tt-argus"] = "1"
    kwargs["headers"] = headers

    try:
        kwargs["timeout"] = max(int(kwargs.get("timeout") or 0), int(timeout))
    except (TypeError, ValueError):
        kwargs["timeout"] = timeout

    crawler = DouyinCrawler(kwargs)
    try:
        # 该接口不带业务参数时，即使 Cookie 有效也可能返回 status_code=8。
        # 浏览器请求至少会带 aid 和 cookie_enabled，这里保持一致。
        params = {
            "aid": "6383",
            "cookie_enabled": "true",
        }
        endpoint = crawler.bogus_manager.model_2_endpoint(
            crawler.headers.get("User-Agent"), SELF_PROFILE_ENDPOINT, params
        )
        response = await crawler.aclient.get(endpoint)
        return response.status_code, response.text
    finally:
        await crawler.close()


def _interpret_response(http_status: int, body: str) -> DouyinCookieCheckResult:
    if http_status == 200:
        try:
            data = json.loads(body)
        except ValueError:
            return DouyinCookieCheckResult(False, STATUS_ERROR, "抖音返回了非 JSON 响应", http_status)
        code = data.get("status_code")
        status_msg = data.get("status_msg") or ""
        user = data.get("user")
        if code == 0 and user:
            nickname = str(user.get("nickname") or "")
            message = f"Cookie 有效，登录态正常（{nickname}）" if nickname else "Cookie 有效，登录态正常"
            return DouyinCookieCheckResult(True, STATUS_VALID, message, http_status, nickname=nickname)
        if code == 8 or "未登录" in status_msg:
            return DouyinCookieCheckResult(
                False, STATUS_EXPIRED, "Cookie 已失效（登录态丢失），请在浏览器重新登录后获取新的 Cookie", http_status
            )
        detail = status_msg or f"status_code={code}"
        return DouyinCookieCheckResult(False, STATUS_ERROR, f"抖音返回异常状态：{detail}", http_status)

    if http_status == 403:
        if "ArgusSecurityPlugin" in body:
            return DouyinCookieCheckResult(
                False,
                STATUS_BLOCKED,
                "被抖音风控拦截（设备指纹 UIFID 失效），请重新获取 Cookie",
                http_status,
            )
        return DouyinCookieCheckResult(False, STATUS_BLOCKED, "抖音接口返回 403，Cookie 可能已失效或被风控", http_status)

    if http_status == 429:
        return DouyinCookieCheckResult(False, STATUS_ERROR, "请求过于频繁（429），请稍后再试", http_status)

    return DouyinCookieCheckResult(False, STATUS_ERROR, f"抖音接口返回异常状态码 {http_status}", http_status)


async def check_douyin_cookie(cookie: str, *, timeout: float = 10.0) -> DouyinCookieCheckResult:
    """检查一份抖音 Cookie 是否仍然可用。"""
    cookie = (cookie or "").strip()
    if not cookie:
        return DouyinCookieCheckResult(False, STATUS_MISSING, "未提供 Cookie", None)

    missing = inspect_cookie_structure(cookie)

    # 结构上完全没有登录态时无需发请求，直接判定失效。
    if not _has_login_state(cookie):
        return DouyinCookieCheckResult(
            False, STATUS_EXPIRED, "Cookie 缺少登录态字段（sessionid/sid_tt），请重新获取", None, missing_keys=missing
        )

    try:
        http_status, body = await _probe_login_state(cookie, timeout)
    except Exception as exc:  # pragma: no cover - 依赖外部网络
        logger.warning("抖音 Cookie 自检请求失败: %s", exc)
        return DouyinCookieCheckResult(
            False, STATUS_ERROR, f"自检请求失败：{exc}", None, missing_keys=missing
        )

    result = _interpret_response(http_status, body)
    result.missing_keys = missing
    return result

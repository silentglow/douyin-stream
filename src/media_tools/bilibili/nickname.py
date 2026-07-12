from __future__ import annotations

"""B站用户昵称获取服务"""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

# 模块级初始化，避免 TOCTOU 竞态
_bilibili_semaphore: asyncio.Semaphore = asyncio.Semaphore(5)
_client_lock: asyncio.Lock = asyncio.Lock()

# 共享 httpx 客户端，避免每次请求创建新的连接池和 TLS 上下文
_shared_client: httpx.AsyncClient | None = None
_client_timeout = httpx.Timeout(timeout=10.0, connect=5.0)
_client_headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://space.bilibili.com/",
}


async def _get_shared_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        async with _client_lock:
            if _shared_client is None or _shared_client.is_closed:
                _shared_client = httpx.AsyncClient(timeout=_client_timeout, follow_redirects=True)
    return _shared_client


async def close_bilibili_client() -> None:
    """关闭共享 httpx 客户端，应在应用 shutdown 时调用。"""
    global _shared_client
    async with _client_lock:
        if _shared_client is not None and not _shared_client.is_closed:
            await _shared_client.aclose()
            _shared_client = None


async def fetch_bilibili_profile(mid: str, retries: int = 3) -> dict[str, str]:
    """
    异步获取 B 站用户资料（昵称 + 头像）

    - 超时控制: connect=5s, read=10s
    - 重试: 最多 3 次，指数退避
    - 异常: 昵称回退为 mid，头像为空串
    """
    url = f"https://api.bilibili.com/x/web-interface/card?mid={mid}"
    client = await _get_shared_client()

    for attempt in range(retries):
        try:
            async with _bilibili_semaphore:
                resp = await client.get(url, headers=_client_headers)
                logger.info(f"B站API响应: mid={mid}, status={resp.status_code}")
                if resp.status_code == 200:
                    json_data = resp.json()
                    code = json_data.get("code")
                    data = json_data.get("data", {})
                    if code == 0 and data.get("card"):
                        card = data["card"]
                        name = card.get("name")
                        face = card.get("face") or ""
                        logger.info(f"B站资料获取成功: mid={mid}, name={name}")
                        return {"nickname": name or mid, "avatar": face}
                    else:
                        logger.warning(f"B站API业务错误: code={code}, mid={mid}")
                elif resp.status_code == 404:
                    logger.warning(f"B站用户不存在: mid={mid}")
                    return {"nickname": mid, "avatar": ""}
                else:
                    logger.warning(f"B站API返回非200: {resp.status_code}, body={resp.text[:200]}, mid={mid}")
        except httpx.TimeoutException:
            wait = 2**attempt
            logger.warning(f"B站API超时 (attempt {attempt + 1}/{retries}), 重试等待 {wait}s: mid={mid}")
            if attempt < retries - 1:
                await asyncio.sleep(wait)
        except httpx.HTTPError as e:
            wait = 2**attempt
            logger.warning(f"B站API错误 (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                await asyncio.sleep(wait)
        except (RuntimeError, OSError, ValueError) as e:
            logger.error(f"B站API异常: {e}")
            break

    return {"nickname": mid, "avatar": ""}


async def fetch_bilibili_nickname(mid: str, retries: int = 3) -> str:
    """异步获取 B 站用户昵称（兼容旧调用，内部走 fetch_bilibili_profile）。"""
    profile = await fetch_bilibili_profile(mid, retries=retries)
    return profile["nickname"]

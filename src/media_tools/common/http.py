from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

import httpx

from .runtime import ensure_dir


# ═════════════════════════════════════════════════════════════════
# 千问 API 客户端 — httpx.AsyncClient 包装
# ═════════════════════════════════════════════════════════════════
# 历史 v2026-05-26 之前用 RequestsApiContext (requests.Session + asyncio.to_thread),
# 改 httpx 后:
#   - 原生 async (不再用 to_thread 包同步调用)
#   - 单一 HTTP 库(替代 requests + urllib + 自写适配链的混用)
#   - httpx.Timeout 分别配 connect/read/write/pool
# 公开类名保留 RequestsApiContext / RequestsApiResponse 作为别名,所有外部 import 零改动。


@dataclass(frozen=True)
class HttpxApiResponse:
    """fetch() 返回的响应,鸭子类型符合调用方期待:
    `.ok` / `.status` / `.status_text` / async `.json()`。
    """
    ok: bool
    status: int
    status_text: str
    _payload: Any

    async def json(self) -> Any:
        return self._payload


class HttpxApiContext:
    """千问 API 调用上下文。一次性创建,服务于一个 flow 的所有 API 调用,end 时 dispose()。

    保留旧 RequestsApiContext 的全部接口契约:
      - 构造:`HttpxApiContext(cookie_string=..., base_headers=..., timeout_seconds=30)`
      - `await ctx.fetch(url, method='POST', headers=None, data=None) -> HttpxApiResponse`
      - `await ctx.dispose()`

    使用 httpx.AsyncClient 内部 connection pool,所有调用复用 keep-alive 连接。
    """

    def __init__(
        self,
        *,
        cookie_string: str = "",
        base_headers: dict[str, str] | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        headers = dict(base_headers or {})
        headers.setdefault("accept", "application/json, text/plain, */*")
        headers.setdefault(
            "user-agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        )
        cleaned_cookie = cookie_string.strip()
        if cleaned_cookie:
            headers["cookie"] = cleaned_cookie

        # connect 10s 够建立 TLS;read 用 timeout_seconds 控制 API 响应;
        # write/pool 给充足余量避免 false-fail
        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(
                connect=10.0,
                read=float(timeout_seconds),
                write=float(timeout_seconds),
                pool=5.0,
            ),
            follow_redirects=False,
        )

    async def dispose(self) -> None:
        await self._client.aclose()

    async def fetch(
        self,
        url: str,
        *,
        method: str = "POST",
        headers: dict[str, str] | None = None,
        data: Optional[str] = None,
    ) -> HttpxApiResponse:
        content = data.encode("utf-8") if isinstance(data, str) else data
        try:
            resp = await self._client.request(
                method,
                url,
                headers=headers,
                content=content,
            )
        except httpx.RequestError as error:
            raise RuntimeError(f"API request failed: {error}") from error

        payload: Any
        if resp.content:
            try:
                payload = resp.json()
            except (json.JSONDecodeError, ValueError):
                payload = resp.text
        else:
            payload = None

        return HttpxApiResponse(
            ok=bool(resp.is_success),
            status=int(resp.status_code),
            status_text=resp.reason_phrase or "",
            _payload=payload,
        )


# 向后兼容别名 - 调用方 (flow.py / quota.py / assets/gc.py) 的 import 路径不变
RequestsApiContext = HttpxApiContext
RequestsApiResponse = HttpxApiResponse


async def api_json(
    context: Any,
    url: str,
    body: Any,
    headers: dict[str, str] | None = None,
) -> Any:
    """统一 POST JSON 调用入口。context 是任何提供 .fetch() 的对象。"""
    response = await context.fetch(
        url,
        method="POST",
        headers={
            "content-type": "application/json",
            **(headers or {}),
        },
        data=json.dumps(body),
    )
    if not response.ok:
        raise RuntimeError(f"API request failed: {response.status} {response.status_text} {url}")
    return await response.json()


# ═════════════════════════════════════════════════════════════════
# 文件下载 - httpx 流式
# ═════════════════════════════════════════════════════════════════
# 历史 v2026-05-26 之前用 urllib.request.urlopen + 整文件读内存。改 httpx 后:
#   - 流式落盘 (response.aiter_bytes),不读到内存
#   - 原生 async (await asyncio.sleep 替代 time.sleep)
#   - 跟随重定向(export URL 可能 302 到 OSS 下载地址)


async def download_file(
    url: str,
    output_path: Union[str, Path],
    timeout: int = 30,
) -> Path:
    """下载 URL 到本地文件,流式落盘 + 3 次指数退避重试。"""
    path = Path(output_path).resolve()
    ensure_dir(path.parent)

    last_error: Optional[BaseException] = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=float(timeout),
                    write=float(timeout),
                    pool=5.0,
                ),
                follow_redirects=True,
            ) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    with open(path, "wb") as f:
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)
            return path
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            last_error = e
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"下载失败 (重试3次): {url}") from last_error

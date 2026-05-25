from __future__ import annotations

import asyncio
import threading
import time
from email.utils import formatdate
import os
import re
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Union
from urllib import request as urllib_request
from xml.sax.saxutils import escape as xml_escape

import requests
from requests.adapters import HTTPAdapter

from .oss_sign import md5_base64, sign_oss_request, build_oss_url


ProgressCallback = Callable[[dict[str, Any]], None]


_SESSION: Optional[requests.Session] = None
_SESSION_LOCK = threading.Lock()


def _get_session() -> requests.Session:
    """模块级 requests.Session，跨所有 asyncio.to_thread worker 共享。
    urllib3 PoolManager 内部 thread-safe，多个 worker 并发调用共用同一连接池。
    """
    global _SESSION
    if _SESSION is None:
        with _SESSION_LOCK:
            if _SESSION is None:
                s = requests.Session()
                # max_retries=0：重试由 _open_request 上层统一控制（保持原语义）
                adapter = HTTPAdapter(pool_connections=10, pool_maxsize=50, max_retries=0)
                s.mount("https://", adapter)
                s.mount("http://", adapter)
                _SESSION = s
    return _SESSION


class _RequestsResponseAdapter:
    """适配 requests.Response 到原 urllib urlopen 的 context-manager + .headers + .read() 契约，
    让 `with _open_request(req) as response:` 调用点零改动。
    """

    def __init__(self, resp: requests.Response) -> None:
        self._resp = resp
        self.headers = resp.headers  # CaseInsensitiveDict 支持 .get("ETag")

    def __enter__(self) -> "_RequestsResponseAdapter":
        return self

    def __exit__(self, *args: Any) -> None:
        self._resp.close()

    def read(self) -> bytes:
        return self._resp.content


def normalize_oss_token(token: dict[str, Any]) -> dict[str, Any]:
    """兼容新版 token 结构：把 data.sts 里的字段平铺到顶层。"""
    normalized = dict(token or {})
    sts = normalized.get("sts")
    if isinstance(sts, dict):
        for key in ["bucket", "endpoint", "fileKey", "accessKeyId", "accessKeySecret", "securityToken"]:
            if key not in normalized and key in sts:
                normalized[key] = sts[key]
    return normalized


def parse_upload_id(xml_text: str) -> str:
    match = re.search(r"<UploadId>([^<]+)</UploadId>", xml_text)
    if not match:
        raise RuntimeError("Unable to parse UploadId from OSS initiate response.")
    return match.group(1)


def _open_request(req: urllib_request.Request, timeout: int = 30) -> _RequestsResponseAdapter:
    """通过共享 requests.Session 发请求；保留原 urllib_request.Request 入参接口，
    输出符合 context-manager + .headers + .read() 契约的 adapter。
    内置 3 次重试（指数退避 1s/2s/4s），与原 urllib 版本语义一致。
    """
    session = _get_session()
    method = req.get_method()
    url = req.full_url
    headers = dict(req.headers)
    body = req.data

    last_error: Optional[BaseException] = None
    for attempt in range(3):
        try:
            resp = session.request(
                method, url,
                data=body, headers=headers,
                timeout=timeout, allow_redirects=False,
            )
            if 200 <= resp.status_code < 300:
                return _RequestsResponseAdapter(resp)
            # 4xx/5xx：保留 body 片段，方便排查 OSS 错误码（NoSuchUpload / InvalidDigest 等）
            detail = (resp.text or "")[:500]
            resp.close()
            raise RuntimeError(f"HTTP {resp.status_code}: {detail}")
        except (requests.RequestException, OSError) as e:
            last_error = e
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"请求失败 (重试3次): {last_error}") from last_error


CHUNK_SIZE = 8 * 1024 * 1024  # 8MB chunks


class _ChunkedFileReader:
    """流式文件读取器，避免大文件一次性读入内存"""
    def __init__(self, file_path: Path, chunk_size: int = CHUNK_SIZE):
        self.file_path = file_path
        self.chunk_size = chunk_size
        self._file = None

    def __enter__(self):
        self._file = open(self.file_path, 'rb')
        return self

    def __exit__(self, *args):
        if self._file:
            self._file.close()

    def __iter__(self) -> Iterable[bytes]:
        while True:
            chunk = self._file.read(self.chunk_size)
            if not chunk:
                break
            yield chunk


def initiate_multipart_upload(sts: dict[str, Any], mime_type: str) -> str:
    oss_date = formatdate(usegmt=True)
    headers = {
        "x-oss-date": oss_date,
        "x-oss-security-token": sts["securityToken"],
        "x-oss-user-agent": "qwen-web-capture/0.1",
    }
    authorization = sign_oss_request(
        method="POST",
        bucket=sts["bucket"],
        object_key=sts["fileKey"],
        access_key_id=sts["accessKeyId"],
        access_key_secret=sts["accessKeySecret"],
        content_type=mime_type,
        date_value=oss_date,
        oss_headers=headers,
        subresources={"uploads": ""},
    )
    req = urllib_request.Request(
        build_oss_url(sts["bucket"], sts["endpoint"], sts["fileKey"], {"uploads": ""}),
        method="POST",
        headers={
            **headers,
            "authorization": authorization,
            "content-type": mime_type,
        },
    )
    with _open_request(req) as response:
        return parse_upload_id(response.read().decode("utf-8", errors="replace"))


def direct_upload_with_presigned_url(url: str, file_buffer: bytes, mime_type: str) -> None:
    req = urllib_request.Request(
        url,
        data=file_buffer,
        method="PUT",
        headers={"content-type": mime_type},
    )
    with _open_request(req):
        return


def _direct_upload_with_presigned_url_from_path(url: str, file_path: Path, mime_type: str) -> None:
    """从文件路径直接上传到预签名URL。

    使用一次性读取（非流式），因为 _open_request 会重试，
    流式迭代器在首次请求后耗尽会导致重试时上传空 body。
    """
    data = file_path.read_bytes()
    req = urllib_request.Request(
        url,
        data=data,
        method="PUT",
        headers={"content-type": mime_type, "content-length": str(len(data))},
    )
    with _open_request(req):
        return


def abort_multipart_upload(sts: dict[str, Any], upload_id: str) -> None:
    """取消分片上传，清理已上传的分片"""
    oss_date = formatdate(usegmt=True)
    headers = {
        "x-oss-date": oss_date,
        "x-oss-security-token": sts["securityToken"],
        "x-oss-user-agent": "qwen-web-capture/0.1",
    }
    authorization = sign_oss_request(
        method="DELETE",
        bucket=sts["bucket"],
        object_key=sts["fileKey"],
        access_key_id=sts["accessKeyId"],
        access_key_secret=sts["accessKeySecret"],
        date_value=oss_date,
        oss_headers=headers,
        subresources={"uploadId": upload_id},
    )
    req = urllib_request.Request(
        build_oss_url(
            sts["bucket"],
            sts["endpoint"],
            sts["fileKey"],
            {"uploadId": upload_id},
        ),
        method="DELETE",
        headers={
            **headers,
            "authorization": authorization,
        },
    )
    with _open_request(req):
        return


def upload_part(sts: dict[str, Any], upload_id: str, part_number: int, chunk: bytes, mime_type: str) -> str:
    oss_date = formatdate(usegmt=True)
    content_md5 = md5_base64(chunk)
    headers = {
        "x-oss-date": oss_date,
        "x-oss-security-token": sts["securityToken"],
        "x-oss-user-agent": "qwen-web-capture/0.1",
    }
    authorization = sign_oss_request(
        method="PUT",
        bucket=sts["bucket"],
        object_key=sts["fileKey"],
        access_key_id=sts["accessKeyId"],
        access_key_secret=sts["accessKeySecret"],
        content_md5=content_md5,
        content_type=mime_type,
        date_value=oss_date,
        oss_headers=headers,
        subresources={
            "partNumber": str(part_number),
            "uploadId": upload_id,
        },
    )
    req = urllib_request.Request(
        build_oss_url(
            sts["bucket"],
            sts["endpoint"],
            sts["fileKey"],
            {
                "partNumber": str(part_number),
                "uploadId": upload_id,
            },
        ),
        data=chunk,
        method="PUT",
        headers={
            **headers,
            "authorization": authorization,
            "content-md5": content_md5,
            "content-type": mime_type,
        },
    )
    with _open_request(req) as response:
        etag = response.headers.get("ETag")
    if not etag:
        raise RuntimeError(f"OSS upload part {part_number} missing ETag.")
    return etag


def complete_multipart_upload(sts: dict[str, Any], upload_id: str, parts: list[dict[str, Any]]) -> None:
    xml = "".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            "<CompleteMultipartUpload>",
            *[
                (
                    "<Part>"
                    f"<PartNumber>{part['partNumber']}</PartNumber>"
                    f"<ETag>{xml_escape(str(part['etag']))}</ETag>"
                    "</Part>"
                )
                for part in parts
            ],
            "</CompleteMultipartUpload>",
        ]
    ).encode("utf-8")
    content_md5 = md5_base64(xml)
    content_type = "application/xml"
    oss_date = formatdate(usegmt=True)
    headers = {
        "x-oss-date": oss_date,
        "x-oss-security-token": sts["securityToken"],
        "x-oss-user-agent": "qwen-web-capture/0.1",
    }
    authorization = sign_oss_request(
        method="POST",
        bucket=sts["bucket"],
        object_key=sts["fileKey"],
        access_key_id=sts["accessKeyId"],
        access_key_secret=sts["accessKeySecret"],
        content_md5=content_md5,
        content_type=content_type,
        date_value=oss_date,
        oss_headers=headers,
        subresources={"uploadId": upload_id},
    )
    req = urllib_request.Request(
        build_oss_url(
            sts["bucket"],
            sts["endpoint"],
            sts["fileKey"],
            {"uploadId": upload_id},
        ),
        data=xml,
        method="POST",
        headers={
            **headers,
            "authorization": authorization,
            "content-md5": content_md5,
            "content-type": content_type,
        },
    )
    with _open_request(req):
        return


def _resolve_part_size(file_size: int, override_mb: int) -> int:
    """决定 multipart 分片大小（字节）。override_mb > 0 时优先用它；否则按文件大小自动选：
    < 1 GB → 5 MB；< 5 GB → 16 MB；≥ 5 GB → 32 MB。
    """
    if override_mb > 0:
        return override_mb * 1024 * 1024
    if file_size < 1 * 1024 * 1024 * 1024:
        return 5 * 1024 * 1024
    if file_size < 5 * 1024 * 1024 * 1024:
        return 16 * 1024 * 1024
    return 32 * 1024 * 1024


async def upload_file_to_oss(
    *,
    token: dict[str, Any],
    file_buffer: bytes | None = None,
    file_path: str | Optional[Path] = None,
    mime_type: str,
    part_size: int = 0,
    on_progress: ProgressCallback | None = None,
    upload_mode: Optional[str] = None,
) -> None:
    """上传文件到OSS

    Args:
        token: OSS令牌
        file_buffer: 文件字节缓冲区（小文件使用）
        file_path: 文件路径（大文件使用，避免OOM）
        mime_type: MIME类型
        part_size: 分片大小（字节）。0 = 按文件大小自动选 + 受 QWEN_OSS_PART_SIZE_MB 配置控制
        on_progress: 进度回调
        upload_mode: 上传模式
    """
    token = normalize_oss_token(token)

    # 验证token的必需键
    required_keys = ["getLink", "sts", "bucket", "endpoint", "fileKey", "accessKeyId", "accessKeySecret", "securityToken"]
    for key in required_keys:
        if key not in token:
            raise ValueError(f"Token missing required key: {key}")

    callback = on_progress or (lambda _event: None)
    from media_tools.core.config import get_app_config
    app_config = get_app_config()
    mode = (upload_mode or app_config.qwen_oss_upload_mode).strip().lower()
    if mode not in {"multipart", "auto", "direct"}:
        raise ValueError(f"Unsupported OSS upload mode: {mode}")

    # 确定使用文件路径还是字节缓冲
    use_file_path = file_path is not None and file_buffer is None
    if use_file_path:
        assert file_path is not None
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        file_size = file_path_obj.stat().st_size
    elif file_buffer is not None:
        assert file_buffer is not None
        file_size = len(file_buffer)
    else:
        raise ValueError("Either file_buffer or file_path must be provided")

    # 调用方传非 0 优先；否则按 (env/SystemSetting 覆写 → 自动) 选
    if part_size <= 0:
        part_size = _resolve_part_size(file_size, app_config.qwen_oss_part_size_mb)
    concurrency = app_config.qwen_oss_upload_concurrency

    if mode in {"auto", "direct"}:
        try:
            if use_file_path:
                # 使用文件路径上传
                await asyncio.to_thread(_direct_upload_with_presigned_url_from_path, token["getLink"], file_path_obj, mime_type)
            else:
                assert file_buffer is not None
                await asyncio.to_thread(direct_upload_with_presigned_url, token["getLink"], file_buffer, mime_type)
            callback({"type": "direct-upload-complete"})
            return
        except (RuntimeError, OSError, ConnectionError, TimeoutError) as error:
            callback({"type": "direct-upload-failed", "error": error, "mode": mode})
            if mode == "direct":
                raise

    upload_id = await asyncio.to_thread(initiate_multipart_upload, token["sts"], mime_type)
    callback({"type": "multipart-started", "uploadId": upload_id})

    total_parts = (file_size + part_size - 1) // part_size

    # 并发上传：producer 顺序读文件 chunk 投到 queue（maxsize=concurrency 起背压作用，
    # 内存峰值 ≈ 2*concurrency*part_size）；N 个 consumer 并发跑 upload_part。
    # 任一 consumer 抛错 → asyncio.gather 取消所有兄弟 task → 外层 abort_multipart_upload 兜底清理。
    queue: asyncio.Queue = asyncio.Queue(maxsize=concurrency)
    parts_result: list[dict[str, Any]] = []
    done_counter = 0

    async def producer() -> None:
        if use_file_path:
            # 用 to_thread 包 read 避免阻塞事件循环
            f = open(file_path_obj, "rb")
            try:
                for part_number in range(1, total_parts + 1):
                    chunk = await asyncio.to_thread(f.read, part_size)
                    if not chunk:
                        break
                    await queue.put((part_number, chunk))
            finally:
                f.close()
        else:
            assert file_buffer is not None
            for offset, part_number in zip(
                range(0, len(file_buffer), part_size),
                range(1, total_parts + 1),
                strict=True,
            ):
                await queue.put((part_number, file_buffer[offset : offset + part_size]))
        # 投终止哨兵（每个 consumer 一个）
        for _ in range(concurrency):
            await queue.put(None)

    async def consumer() -> None:
        nonlocal done_counter
        while True:
            item = await queue.get()
            if item is None:
                return
            part_number, chunk = item
            etag = await asyncio.to_thread(
                upload_part, token["sts"], upload_id, part_number, chunk, mime_type,
            )
            parts_result.append({"partNumber": part_number, "etag": etag})
            done_counter += 1
            callback({
                "type": "part-uploaded",
                "partNumber": part_number,
                "completed": done_counter,
                "totalParts": total_parts,
            })

    try:
        await asyncio.gather(producer(), *(consumer() for _ in range(concurrency)))

        # OSS complete API 要求 parts 按 partNumber 升序
        parts_result.sort(key=lambda x: x["partNumber"])
        await asyncio.to_thread(complete_multipart_upload, token["sts"], upload_id, parts_result)
        callback({"type": "multipart-complete"})
    except BaseException:
        # 任何失败（含 asyncio.CancelledError、KeyboardInterrupt 等）都要尝试 abort multipart，
        # 否则 OSS 上的分片会持续占用直到 lifecycle 规则清掉，按量计费场景会累积成本。
        # 用 shield 防止 abort 在外层取消信号下被打断。
        if upload_id:
            try:
                await asyncio.shield(
                    asyncio.to_thread(abort_multipart_upload, token["sts"], upload_id)
                )
                callback({"type": "multipart-aborted", "uploadId": upload_id})
            except BaseException as abort_error:  # noqa: BLE001 - 必须吞掉避免掩盖原始异常
                callback({
                    "type": "multipart-abort-failed",
                    "uploadId": upload_id,
                    "error": str(abort_error),
                })
        raise

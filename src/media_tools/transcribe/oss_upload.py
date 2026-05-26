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

import oss2
import requests
from requests.adapters import HTTPAdapter

from .oss_sign import md5_base64, sign_oss_request, build_oss_url


ProgressCallback = Callable[[dict[str, Any]], None]


# checkpoint 目录:oss2.resumable_upload 用它存"已传 part" 状态,
# 网络中断 / 进程崩溃后下次重传可以跳过已传 part 继续。
_OSS2_CHECKPOINT_DIR = Path("data/.upload_cp")


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


def _build_oss2_bucket(token: dict[str, Any]) -> oss2.Bucket:
    """根据千问返回的 STS 临时凭证构造 oss2.Bucket。"""
    sts = token["sts"]
    auth = oss2.StsAuth(
        sts["accessKeyId"],
        sts["accessKeySecret"],
        sts["securityToken"],
    )
    # connect/read timeout 调大到 120s,给瞬时网络抖动留余地;
    # oss2 内部对单 part 写超时也会重试,不会因为一片慢就整次崩
    return oss2.Bucket(
        auth,
        sts["endpoint"],
        sts["bucket"],
        connect_timeout=120,
    )


def _resumable_upload_via_oss2(
    *,
    token: dict[str, Any],
    file_path: Path,
    mime_type: str,
    part_size: int,
    concurrency: int,
    callback: ProgressCallback,
) -> None:
    """用阿里官方 oss2.resumable_upload 上传大文件。

    特性:
    - **断点续传**: checkpoint 存到 data/.upload_cp/,网络中断 / 进程崩溃后下次重传
      自动跳过已传 part 继续;
    - **part 级重试**: oss2 内置失败 part 单独重试,不会因为一片崩就整次重来;
    - **进度回调**: 把 oss2 的 (bytes_consumed, total_bytes) 桥接成原 part-uploaded 事件。
    """
    _OSS2_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    bucket = _build_oss2_bucket(token)
    key = token["sts"]["fileKey"]
    file_size = file_path.stat().st_size
    total_parts = max(1, (file_size + part_size - 1) // part_size)

    store = oss2.ResumableStore(root=str(_OSS2_CHECKPOINT_DIR))

    # oss2 的 progress 是 byte 级单调,把它桥接成 part-uploaded 事件
    # (flow.py 的 _make_upload_progress_logger 按 part 级 bucket 打 10% 进度日志)
    last_emitted_part = 0

    def _progress_bridge(bytes_consumed: int, total_bytes: Optional[int]) -> None:
        nonlocal last_emitted_part
        if not total_bytes:
            return
        completed_parts = max(1, int(bytes_consumed * total_parts / total_bytes))
        completed_parts = min(completed_parts, total_parts)
        if completed_parts > last_emitted_part:
            last_emitted_part = completed_parts
            callback({
                "type": "part-uploaded",
                "partNumber": completed_parts,
                "completed": completed_parts,
                "totalParts": total_parts,
            })

    headers = {"Content-Type": mime_type}

    # oss2.resumable_upload 第一次会调 InitiateMultipartUpload 拿 uploadId,
    # 我们没办法直接拿到 uploadId 在 multipart-started 事件里上报。
    # 折中:用 file_key 的最后 16 字符当 placeholder,够追踪日志即可。
    callback({"type": "multipart-started", "uploadId": f"oss2:{key[-16:]}"})

    oss2.resumable_upload(
        bucket,
        key,
        str(file_path),
        store=store,
        multipart_threshold=part_size,
        part_size=part_size,
        num_threads=concurrency,
        progress_callback=_progress_bridge,
        headers=headers,
    )

    # 最终事件:确保 flow 看到 100% + complete
    if last_emitted_part < total_parts:
        callback({
            "type": "part-uploaded",
            "partNumber": total_parts,
            "completed": total_parts,
            "totalParts": total_parts,
        })
    callback({"type": "multipart-complete"})


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

    # multipart 模式 — 走阿里官方 oss2.resumable_upload(断点续传 + part 级重试)
    # 历史 v2026-05-26 之前是手写 producer/consumer + 单 part 30s 写超时,任一 part
    # 超时就 abort 整次上传,大文件极易失败。换 oss2 后:
    #   - 单 part 失败自动重试(默认 5 次),不影响其它已传 part
    #   - checkpoint 落盘,网断 / 进程崩了下次同 fileKey 上传从断点继续
    #   - connect/read timeout 调大到 120s,容忍瞬时抖动
    if not use_file_path:
        # 历史 buffer 模式只有小文件 direct 才用,multipart 必须走文件路径
        raise ValueError("multipart upload via oss2 requires file_path (not file_buffer)")

    await asyncio.to_thread(
        _resumable_upload_via_oss2,
        token=token,
        file_path=file_path_obj,
        mime_type=mime_type,
        part_size=part_size,
        concurrency=concurrency,
        callback=callback,
    )

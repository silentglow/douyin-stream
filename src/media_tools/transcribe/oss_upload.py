from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import oss2
import requests
from requests.adapters import HTTPAdapter


ProgressCallback = Callable[[dict[str, Any]], None]


# oss2.resumable_upload 写已传 part 状态的目录。网络中断 / 进程崩溃后下次同 fileKey
# 上传时,oss2 读这里跳过已传 part 从断点继续。
_OSS2_CHECKPOINT_DIR = Path("data/.upload_cp")


# direct 模式(预签名 URL PUT)共享的 requests.Session。multipart 模式由 oss2 自己管。
_SESSION: Optional[requests.Session] = None
_SESSION_LOCK = threading.Lock()


def _get_session() -> requests.Session:
    """direct PUT 用的共享 Session,跨 asyncio.to_thread worker 复用连接池。"""
    global _SESSION
    if _SESSION is None:
        with _SESSION_LOCK:
            if _SESSION is None:
                s = requests.Session()
                adapter = HTTPAdapter(pool_connections=10, pool_maxsize=50, max_retries=0)
                s.mount("https://", adapter)
                s.mount("http://", adapter)
                _SESSION = s
    return _SESSION


def normalize_oss_token(token: dict[str, Any]) -> dict[str, Any]:
    """兼容新版 token 结构:把 data.sts 里的字段平铺到顶层。"""
    normalized = dict(token or {})
    sts = normalized.get("sts")
    if isinstance(sts, dict):
        for key in ["bucket", "endpoint", "fileKey", "accessKeyId", "accessKeySecret", "securityToken"]:
            if key not in normalized and key in sts:
                normalized[key] = sts[key]
    return normalized


def _resolve_part_size(file_size: int, override_mb: int) -> int:
    """决定 multipart 分片大小(字节)。override_mb > 0 时优先用它;否则按文件大小自动选:
    < 1 GB → 5 MB;< 5 GB → 16 MB;≥ 5 GB → 32 MB。
    """
    if override_mb > 0:
        return override_mb * 1024 * 1024
    if file_size < 1 * 1024 * 1024 * 1024:
        return 5 * 1024 * 1024
    if file_size < 5 * 1024 * 1024 * 1024:
        return 16 * 1024 * 1024
    return 32 * 1024 * 1024


def _direct_put(url: str, data: bytes, mime_type: str, timeout: int = 120) -> None:
    """direct 模式:PUT 数据到千问预签名 URL。内置 3 次重试(指数退避 1s/2s/4s)。"""
    last_error: Optional[BaseException] = None
    for attempt in range(3):
        try:
            resp = _get_session().put(
                url, data=data,
                headers={"Content-Type": mime_type},
                timeout=timeout,
                allow_redirects=False,
            )
            try:
                if 200 <= resp.status_code < 300:
                    return
                detail = (resp.text or "")[:500]
                raise RuntimeError(f"HTTP {resp.status_code}: {detail}")
            finally:
                resp.close()
        except (requests.RequestException, OSError) as e:
            last_error = e
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"direct PUT 失败 (重试3次): {last_error}") from last_error


def _build_oss2_bucket(token: dict[str, Any]) -> oss2.Bucket:
    """根据千问返回的 STS 临时凭证构造 oss2.Bucket。
    connect/read timeout 120s,容忍瞬时网络抖动(默认 60s 偶尔被快网抖动触发)。
    """
    sts = token["sts"]
    auth = oss2.StsAuth(sts["accessKeyId"], sts["accessKeySecret"], sts["securityToken"])
    return oss2.Bucket(auth, sts["endpoint"], sts["bucket"], connect_timeout=120)


def _resumable_upload_via_oss2(
    *,
    token: dict[str, Any],
    file_path: Path,
    mime_type: str,
    part_size: int,
    concurrency: int,
    callback: ProgressCallback,
) -> None:
    """multipart 模式:直接调阿里官方 oss2.resumable_upload。

    全部健壮性来自 oss2 自身,我们只做格式适配:
      - **断点续传**: ResumableStore 把已传 part 写到 data/.upload_cp/,
        网断 / 进程崩了下次同 fileKey 上传自动从断点继续
      - **part 级重试**: 单片失败 oss2 内部重试(默认 3 次),不影响其它 part
      - **CRC64 + Content-MD5 校验**: oss2 默认开
      - **连接池**: oss2 内部 urllib3 PoolManager

    我们做的事情:
      1. 千问 STS token → oss2.Bucket
      2. oss2 的 byte 级 progress_callback → 我们的 part-uploaded 事件
         (给 flow.py 的 _make_upload_progress_logger 用)
    """
    _OSS2_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    bucket = _build_oss2_bucket(token)
    key = token["sts"]["fileKey"]
    file_size = file_path.stat().st_size
    total_parts = max(1, (file_size + part_size - 1) // part_size)

    store = oss2.ResumableStore(root=str(_OSS2_CHECKPOINT_DIR))

    last_emitted_part = 0

    def _progress_bridge(bytes_consumed: int, total_bytes: Optional[int]) -> None:
        nonlocal last_emitted_part
        if not total_bytes:
            return
        completed_parts = min(total_parts, max(1, int(bytes_consumed * total_parts / total_bytes)))
        if completed_parts > last_emitted_part:
            last_emitted_part = completed_parts
            callback({
                "type": "part-uploaded",
                "completed": completed_parts,
                "totalParts": total_parts,
            })

    oss2.resumable_upload(
        bucket,
        key,
        str(file_path),
        store=store,
        multipart_threshold=part_size,
        part_size=part_size,
        num_threads=concurrency,
        progress_callback=_progress_bridge,
        headers={"Content-Type": mime_type},
    )

    # 收尾:确保 flow 看到 100% + complete(progress_bridge 可能没推进到 totalParts)
    if last_emitted_part < total_parts:
        callback({
            "type": "part-uploaded",
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
    """上传文件到 OSS。

    根据 upload_mode 路由:
      - `direct`: 小文件直接 PUT 到 token['getLink'] 预签名 URL
      - `multipart`: 大文件走 oss2.resumable_upload(断点续传 + part 级重试)
      - `auto`: 先试 direct,失败回退 multipart
    """
    token = normalize_oss_token(token)

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

    use_file_path = file_path is not None and file_buffer is None
    if use_file_path:
        assert file_path is not None
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        file_size = file_path_obj.stat().st_size
    elif file_buffer is not None:
        file_size = len(file_buffer)
    else:
        raise ValueError("Either file_buffer or file_path must be provided")

    if part_size <= 0:
        part_size = _resolve_part_size(file_size, app_config.qwen_oss_part_size_mb)
    concurrency = app_config.qwen_oss_upload_concurrency

    if mode in {"auto", "direct"}:
        try:
            data = file_path_obj.read_bytes() if use_file_path else file_buffer
            assert data is not None
            await asyncio.to_thread(_direct_put, token["getLink"], data, mime_type)
            callback({"type": "direct-upload-complete"})
            return
        except (RuntimeError, OSError, ConnectionError, TimeoutError) as error:
            callback({"type": "direct-upload-failed", "error": error, "mode": mode})
            if mode == "direct":
                raise

    # multipart 模式 - 走 oss2.resumable_upload
    if not use_file_path:
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

from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


_HTTP_PREFIXES = ("http://", "https://")
_MAX_FILE_PATHS = 500
_MAX_BATCH_URLS = 200
_MAX_URL_LEN = 2048
_MAX_PATH_LEN = 4096


def _validate_http_url(value: str) -> str:
    v = (value or "").strip()
    if not v:
        raise ValueError("url 不能为空")
    if len(v) > _MAX_URL_LEN:
        raise ValueError(f"url 长度超出 {_MAX_URL_LEN} 字符")
    if not v.startswith(_HTTP_PREFIXES):
        raise ValueError("url 必须以 http:// 或 https:// 开头")
    return v


def _validate_path(value: str) -> str:
    v = (value or "").strip()
    if not v:
        raise ValueError("路径不能为空")
    if len(v) > _MAX_PATH_LEN:
        raise ValueError(f"路径长度超出 {_MAX_PATH_LEN} 字符")
    if "\x00" in v:
        raise ValueError("路径包含非法字符")
    return v


class PipelineRequest(BaseModel):
    url: str
    max_counts: int = Field(default=5, ge=1, le=1000)
    auto_delete: Optional[bool] = None

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        return _validate_http_url(v)


class BatchPipelineRequest(BaseModel):
    video_urls: list[str]
    auto_delete: Optional[bool] = None

    @field_validator("video_urls")
    @classmethod
    def _check_urls(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("video_urls 不能为空")
        if len(v) > _MAX_BATCH_URLS:
            raise ValueError(f"单次批量操作最多 {_MAX_BATCH_URLS} 条")
        return [_validate_http_url(u) for u in v]


class DownloadBatchRequest(BaseModel):
    video_urls: list[str]

    @field_validator("video_urls")
    @classmethod
    def _check_urls(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("video_urls 不能为空")
        if len(v) > _MAX_BATCH_URLS:
            raise ValueError(f"单次批量操作最多 {_MAX_BATCH_URLS} 条")
        return [_validate_http_url(u) for u in v]


SyncMode = Literal["incremental", "full"]


class CreatorDownloadRequest(BaseModel):
    uid: str = Field(min_length=1, max_length=200)
    mode: SyncMode = "incremental"
    batch_size: Optional[int] = Field(default=None, ge=1, le=1000)


class FullSyncRequest(BaseModel):
    mode: SyncMode = "incremental"
    batch_size: Optional[int] = Field(default=None, ge=1, le=1000)


class LocalTranscribeRequest(BaseModel):
    file_paths: list[str]
    delete_after: Optional[bool] = None
    directory_root: Optional[str] = None

    @field_validator("file_paths")
    @classmethod
    def _check_paths(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("file_paths 不能为空")
        if len(v) > _MAX_FILE_PATHS:
            raise ValueError(f"file_paths 最多 {_MAX_FILE_PATHS} 条")
        return [_validate_path(p) for p in v]

    @field_validator("directory_root")
    @classmethod
    def _check_dir(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return v
        return _validate_path(v)


class CreatorTranscribeRequest(BaseModel):
    uid: str = Field(min_length=1, max_length=200)
    delete_after: Optional[bool] = None


class ScanDirectoryRequest(BaseModel):
    directory: str

    @field_validator("directory")
    @classmethod
    def _check_dir(cls, v: str) -> str:
        return _validate_path(v)


class RecoverAwemeTranscribeRequest(BaseModel):
    creator_uid: str = Field(min_length=1, max_length=200)
    aweme_id: str = Field(min_length=1, max_length=200)
    title: str = Field(default="", max_length=500)

    @field_validator("aweme_id")
    @classmethod
    def _check_aweme_id(cls, v: str) -> str:
        # 抖音 aweme_id 是纯数字，约束防止后续 f"...video/{aweme_id}" 拼接被注入路径段
        v = (v or "").strip()
        if not v.isdigit():
            raise ValueError("aweme_id 必须是数字")
        return v

    @field_validator("creator_uid")
    @classmethod
    def _check_creator_uid(cls, v: str) -> str:
        v = (v or "").strip()
        # creator_uid 可能是 "uid" 或 "platform:uid" 格式，禁止路径分隔符避免注入
        if "/" in v or "\\" in v or "?" in v or "#" in v:
            raise ValueError("creator_uid 包含非法字符")
        return v


class CreatorTranscribeCleanupRetryRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=200)


class RetryFailedAssetsRequest(BaseModel):
    """重试 media_assets 中 transcript_status='failed' 的视频。

    空参数表示"重试所有失败的资产"；filter 组合生效。
    """
    creator_uid: Optional[str] = Field(default=None, max_length=200)
    platform: Optional[str] = Field(default=None, max_length=40)
    error_types: Optional[list[str]] = None
    limit: Optional[int] = Field(default=None, ge=1, le=5000)
    delete_after: Optional[bool] = None

    @field_validator("error_types")
    @classmethod
    def _check_error_types(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        if len(v) > 20:
            raise ValueError("error_types 最多 20 项")
        cleaned = [str(x).strip() for x in v if isinstance(x, str) and str(x).strip()]
        return cleaned or None


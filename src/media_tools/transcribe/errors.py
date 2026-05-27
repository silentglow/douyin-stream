from __future__ import annotations

"""转写模块的统一错误处理。

合并自历史的 3 个文件（REFACTOR 2026-05 任务 2）：
- errors.py        : QwenTranscribeError 异常类层级
- error_types.py   : ErrorType enum + classify_error 函数
- error_classifier.py : ErrorInfo dataclass + TranscribeError + TranscribeErrorClassifier

三个分类机制来自不同时期的迭代，本次合并保持公开 API 100% 兼容，仅消除"文件
分散导致调用方要 import 三个地方"的负担。后续如需进一步收敛到单一分类机制，
另起任务。

注意：本模块的 `TranscribeError` 与 `media_tools.core.exceptions.TranscribeApiError`
**不同类**（前者继承 RuntimeError 携带 ErrorInfo；后者继承 AppError 用于
HTTP 错误响应）——已在 core.exceptions 中重命名为 TranscribeApiError 消除歧义。
"""

from dataclasses import dataclass
from enum import Enum

# ═══════════════════════════════════════════════════════════════
# Section A — 异常类层级（用户面 / 配置面 / 鉴权面错误）
# 历史来源：errors.py
# ═══════════════════════════════════════════════════════════════


class QwenTranscribeError(Exception):
    exit_code = 1


class UserFacingError(QwenTranscribeError):
    exit_code = 2


class ConfigurationError(UserFacingError):
    """Raised when local configuration or environment values are invalid."""


class InputValidationError(UserFacingError):
    """Raised when the user provides invalid command input."""


class AuthenticationRequiredError(UserFacingError):
    """Raised when a command needs a saved auth state that does not exist."""


# ═══════════════════════════════════════════════════════════════
# Section B — Pipeline 错误类型分类（基于异常对象）
# 历史来源：error_types.py
# 输出：ErrorType enum（机器可读）
# ═══════════════════════════════════════════════════════════════


class ErrorType(Enum):
    UNKNOWN = "unknown"
    NETWORK = "network"
    QUOTA = "quota"
    AUTH = "auth"
    FILE_NOT_FOUND = "file_not_found"
    PERMISSION = "permission"
    TIMEOUT = "timeout"
    VALIDATION = "validation"
    CANCELLED = "cancelled"
    SERVICE_UNAVAILABLE = "service_unavailable"


def classify_error(error: Exception) -> ErrorType:
    error_msg = str(error).lower()
    error_type = type(error).__name__.lower()

    if any(kw in error_msg for kw in ["ssl", "eof occurred", "unexpected eof", "eof"]):
        return ErrorType.NETWORK
    if "token-get" in error_msg or "get token" in error_msg:
        return ErrorType.NETWORK

    if any(
        kw in error_msg
        for kw in ["auth", "unauthorized", "401", "403", "credential", "permission denied", "账号权限不足", "权限不足"]
    ):
        return ErrorType.AUTH
    if "token" in error_msg and any(kw in error_msg for kw in ["expired", "invalid", "unauthorized", "401", "403"]):
        return ErrorType.AUTH

    if any(kw in error_msg for kw in ["connection", "network", "socket", "dns", "resolve", "unreachable"]):
        return ErrorType.NETWORK
    if any(kw in error_type for kw in ["connection", "timeout", "network"]):
        return ErrorType.NETWORK

    if any(kw in error_msg for kw in ["timeout", "timed out", "deadline"]):
        return ErrorType.TIMEOUT

    if any(
        kw in error_msg
        for kw in [
            "service_unavailable",
            "service unavailable",
            "服务暂时不可用",
            "recordstatus=40",
            "recordstatus =40",
        ]
    ):
        return ErrorType.SERVICE_UNAVAILABLE

    if any(kw in error_msg for kw in ["quota", "limit", "rate limit", "429", "exceeded", "too many"]):
        return ErrorType.QUOTA

    if any(kw in error_msg for kw in ["not found", "no such file", "file not found", "does not exist", "找不到"]):
        return ErrorType.FILE_NOT_FOUND

    if any(kw in error_msg for kw in ["permission", "access denied", "forbidden"]):
        return ErrorType.PERMISSION

    if any(kw in error_msg for kw in ["invalid", "validation", "format", "parse"]):
        return ErrorType.VALIDATION

    return ErrorType.UNKNOWN


# ═══════════════════════════════════════════════════════════════
# Section C — 友好错误消息分类（基于错误字符串）
# 历史来源：error_classifier.py
# 输出：ErrorInfo dataclass（含中文 message + suggestion，给前端 UI）
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ErrorInfo:
    message: str
    suggestion: str
    retryable: bool
    error_code: str | None = None


class TranscribeError(RuntimeError):
    """携带完整错误上下文的转写异常，供上层做精准重试/账号切换决策。

    注意：与 `media_tools.core.exceptions.TranscribeApiError` 不同类——
    本类用于 worker 内部错误流，那个用于 HTTP 响应。"""

    def __init__(self, error_info: ErrorInfo, detail: str = ""):
        self.error_info = error_info
        detail_suffix = f": {detail}" if detail else ""
        super().__init__(f"{error_info.message}{detail_suffix}")


class TranscribeErrorClassifier:
    _error_mapping = {
        "40": ErrorInfo(
            message="转写失败：服务暂时不可用",
            suggestion="请稍后重试，或切换其他账号",
            retryable=True,
            error_code="SERVICE_UNAVAILABLE",
        ),
        "41": ErrorInfo(
            message="转写失败：视频内容无法识别",
            suggestion="请检查视频文件是否损坏或格式不支持",
            retryable=False,
            error_code="UNSUPPORTED_FORMAT",
        ),
        "network": ErrorInfo(
            message="网络连接失败", suggestion="请检查网络连接后重试", retryable=True, error_code="NETWORK_ERROR"
        ),
        "timeout": ErrorInfo(
            message="请求超时", suggestion="网络不稳定，请稍后重试", retryable=True, error_code="TIMEOUT"
        ),
        "auth": ErrorInfo(
            message="账号权限不足", suggestion="请更新 Cookie 或切换账号", retryable=True, error_code="AUTH_ERROR"
        ),
        "quota": ErrorInfo(
            message="API 配额不足",
            suggestion="账号额度已用完，请添加新账号",
            retryable=False,
            error_code="QUOTA_EXCEEDED",
        ),
        "rate_limit": ErrorInfo(
            message="触发频率限制", suggestion="请求太频繁，请稍后重试", retryable=True, error_code="RATE_LIMITED"
        ),
        "file_not_found": ErrorInfo(
            message="资源不存在", suggestion="视频可能已被删除或链接失效", retryable=False, error_code="NOT_FOUND"
        ),
        "disk_full": ErrorInfo(
            message="磁盘空间不足", suggestion="请清理磁盘空间后重试", retryable=False, error_code="DISK_FULL"
        ),
    }

    @classmethod
    def classify(cls, error_message: str) -> ErrorInfo:
        error_msg = str(error_message).lower()

        for code, info in cls._error_mapping.items():
            if code in error_msg or (info.error_code and info.error_code.lower() in error_msg):
                return info

        if "network" in error_msg or "connection" in error_msg:
            return cls._error_mapping["network"]
        if "timeout" in error_msg:
            return cls._error_mapping["timeout"]
        if "auth" in error_msg or "cookie" in error_msg or "permission" in error_msg or "权限" in error_msg:
            return cls._error_mapping["auth"]
        if "quota" in error_msg or ("limit" in error_msg and "exceed" in error_msg):
            return cls._error_mapping["quota"]
        if "rate" in error_msg or "frequency" in error_msg:
            return cls._error_mapping["rate_limit"]
        if "not found" in error_msg or "不存在" in error_msg:
            return cls._error_mapping["file_not_found"]
        if "disk" in error_msg or "space" in error_msg:
            return cls._error_mapping["disk_full"]

        return ErrorInfo(
            message=f"发生未知错误: {error_message[:50]}",
            suggestion="请联系开发者",
            retryable=False,
            error_code="UNKNOWN",
        )

from __future__ import annotations

"""应用异常定义 - 统一的错误格式

所有业务异常继承 AppError 基类，确保错误响应格式统一：
{
    "code": "ERROR_CODE",
    "message": "用户友好的错误消息",
    "details": { ... }
}
"""

from typing import Any


class AppError(Exception):
    """应用异常基类 - 所有业务异常继承此类

    Attributes:
        code: 错误代码，用于前端识别错误类型
        message: 用户友好的错误消息
        details: 额外详情（可选）
        status_code: HTTP 状态码（默认 400）
    """

    status_code: int = 400

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class AppConfigurationError(AppError):
    """配置错误 - 配置项缺失或无效"""

    status_code = 500

    def __init__(self, message: str, **kwargs):
        super().__init__("CONFIG_ERROR", message, kwargs)


class DownloadError(AppError):
    """下载错误 - 网络请求失败或文件下载失败"""

    def __init__(self, message: str, url: str | None = None, **kwargs):
        super().__init__("DOWNLOAD_ERROR", message, {"url": url, **kwargs})


class TranscribeApiError(AppError):
    """转写错误 - Qwen API 调用失败"""

    def __init__(self, message: str, file_path: str | None = None, **kwargs):
        super().__init__("TRANSCRIBE_ERROR", message, {"file_path": file_path, **kwargs})


class TaskCancelledError(AppError):
    """任务被取消"""

    def __init__(self, task_id: str):
        super().__init__("TASK_CANCELLED", f"任务 {task_id} 已取消", {"task_id": task_id})


class NotFoundError(AppError):
    """资源不存在"""

    status_code = 404

    def __init__(self, resource: str, identifier: str):
        super().__init__("NOT_FOUND", f"{resource} 不存在: {identifier}", {"resource": resource, "id": identifier})


class ValidationError(AppError):
    """参数校验失败"""

    status_code = 422

    def __init__(self, message: str, field: str | None = None, **kwargs):
        super().__init__("VALIDATION_ERROR", message, {"field": field, **kwargs})


class AuthenticationError(AppError):
    """认证错误 - 用户未登录或凭证无效"""

    status_code = 401

    def __init__(self, message: str = "认证失败"):
        super().__init__("AUTH_ERROR", message)


class AccessDeniedError(AppError):
    """权限错误 - 用户无权限执行操作"""

    status_code = 403

    def __init__(self, message: str = "无权限访问"):
        super().__init__("PERMISSION_ERROR", message)


class ExternalServiceError(AppError):
    """外部服务错误 - 调用第三方 API 失败"""

    status_code = 503

    def __init__(self, service: str, message: str, **kwargs):
        super().__init__("EXTERNAL_SERVICE_ERROR", f"{service} 服务调用失败: {message}", {"service": service, **kwargs})


class DatabaseError(AppError):
    """数据库错误 - 数据库操作失败"""

    status_code = 500

    def __init__(self, message: str, **kwargs):
        super().__init__("DATABASE_ERROR", message, kwargs)


class RateLimitError(AppError):
    """限流错误 - 请求过于频繁"""

    status_code = 429

    def __init__(self, message: str = "请求过于频繁，请稍后再试"):
        super().__init__("RATE_LIMIT_ERROR", message)


class ConflictError(AppError):
    """冲突错误 - 资源状态冲突"""

    status_code = 409

    def __init__(self, message: str):
        super().__init__("CONFLICT_ERROR", message)


# --- 错误响应工具函数 ---


def error_response(exc: AppError) -> dict[str, Any]:
    """生成标准错误响应字典"""
    return {
        "code": exc.code,
        "message": exc.message,
        "details": exc.details,
    }


def error_response_with_trace(exc: AppError, traceback: str) -> dict[str, Any]:
    """生成包含堆栈信息的错误响应（仅在调试模式使用）"""
    response = error_response(exc)
    response["traceback"] = traceback
    return response


# --- 向后兼容别名（旧名称 -> 新名称）---
# PermissionError 覆盖了 Python 内建异常，已重命名为 AccessDeniedError
# ConfigurationError 与 transcribe/errors.py 中同名类冲突，已重命名为 AppConfigurationError
# TranscribeError 与 transcribe/errors.py 中同名类冲突，已重命名为 TranscribeApiError
PermissionError = AccessDeniedError
ConfigurationError = AppConfigurationError
TranscribeError = TranscribeApiError

from __future__ import annotations
"""应用异常基类 — 统一的错误格式。

所有业务异常继承 AppError 基类，确保错误响应格式统一：
{
    "code": "ERROR_CODE",
    "message": "用户友好的错误消息",
    "details": { ... }
}
"""

from typing import Any, Optional


class AppError(Exception):
    """应用异常基类 — 所有业务异常继承此类。"""

    status_code: int = 400

    def __init__(self, code: str, message: str, details: Optional[dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)

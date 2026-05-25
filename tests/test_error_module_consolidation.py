"""REFACTOR 2026-05 任务 2 回归测试：transcribe/ 三个 error 模块合一。

验证：
1. 新统一的 `media_tools.transcribe.errors` 含原 3 个文件的所有 public API
2. 旧路径 `media_tools.transcribe.error_types` / `error_classifier` 已彻底删除（ImportError）
"""

from __future__ import annotations

import importlib

import pytest


def test_unified_errors_module_exports_all_legacy_apis():
    """合并后 errors.py 必须能 import 出原三模块的全部公开名字。"""
    from media_tools.transcribe.errors import (
        # 原 errors.py 异常类层级
        QwenTranscribeError,
        UserFacingError,
        ConfigurationError,
        InputValidationError,
        AuthenticationRequiredError,
        # 原 error_types.py
        ErrorType,
        classify_error,
        # 原 error_classifier.py
        ErrorInfo,
        TranscribeError,
        TranscribeErrorClassifier,
    )

    # 类型校验：拿到的确实是预期类型，不只是 None
    assert issubclass(QwenTranscribeError, Exception)
    assert issubclass(UserFacingError, QwenTranscribeError)
    assert issubclass(ConfigurationError, UserFacingError)
    assert issubclass(InputValidationError, UserFacingError)
    assert issubclass(AuthenticationRequiredError, UserFacingError)

    # ErrorType 是 Enum 且至少含核心成员
    assert ErrorType.NETWORK.value == "network"
    assert ErrorType.QUOTA.value == "quota"
    assert ErrorType.AUTH.value == "auth"
    assert ErrorType.TIMEOUT.value == "timeout"
    assert ErrorType.UNKNOWN.value == "unknown"

    # classify_error 是函数
    et = classify_error(ConnectionError("network down"))
    assert et == ErrorType.NETWORK

    # ErrorInfo / TranscribeError / TranscribeErrorClassifier 可实例化
    info = ErrorInfo(message="x", suggestion="y", retryable=True)
    assert info.retryable is True

    err = TranscribeError(info, detail="ctx")
    assert "x" in str(err) and "ctx" in str(err)

    # 分类器调用
    classified = TranscribeErrorClassifier.classify("network error")
    assert classified.error_code == "NETWORK_ERROR"


def test_legacy_error_types_module_is_gone():
    """`media_tools.transcribe.error_types` 必须彻底无法 import。"""
    with pytest.raises(ImportError):
        importlib.import_module("media_tools.transcribe.error_types")


def test_legacy_error_classifier_module_is_gone():
    """`media_tools.transcribe.error_classifier` 必须彻底无法 import。"""
    with pytest.raises(ImportError):
        importlib.import_module("media_tools.transcribe.error_classifier")

"""异常处理测试 - 验证服务层的降级策略和异常捕获"""

from unittest.mock import patch

import pytest


class TestErrorTypesCoverage:
    """验证异常类型覆盖范围"""

    def test_app_error_hierarchy(self):
        """验证应用异常层次结构"""
        from media_tools.core.exceptions import (
            AppConfigurationError,
            AppError,
            DownloadError,
            NotFoundError,
            TranscribeApiError,
            ValidationError,
        )

        assert issubclass(AppConfigurationError, AppError)
        assert issubclass(DownloadError, AppError)
        assert issubclass(TranscribeApiError, AppError)
        assert issubclass(NotFoundError, AppError)
        assert issubclass(ValidationError, AppError)

    def test_database_errors_are_handled(self):
        """验证数据库异常被正确处理"""
        import sqlite3

        from media_tools.store.db import get_db_connection, reset_db_cache

        reset_db_cache()

        with patch("sqlite3.connect") as mock_connect:
            mock_connect.side_effect = sqlite3.Error("数据库文件损坏")

            with pytest.raises(sqlite3.Error), get_db_connection():
                pass

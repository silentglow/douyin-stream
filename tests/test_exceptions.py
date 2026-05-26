"""Tests for the unified exception handling system."""
from __future__ import annotations

import unittest

from media_tools.core.exceptions import (
    AppError,
    AppConfigurationError,
    DownloadError,
    TranscribeApiError,
    TaskCancelledError,
    NotFoundError,
    ValidationError,
    AuthenticationError,
    AccessDeniedError,
    ExternalServiceError,
    DatabaseError,
    RateLimitError,
    ConflictError,
    error_response,
)


class AppErrorTests(unittest.TestCase):
    """Tests for AppError base class."""

    def test_app_error_default_status_code(self) -> None:
        """Test AppError default status code."""
        exc = AppError("TEST_ERROR", "test message")
        self.assertEqual(exc.status_code, 400)
        self.assertEqual(exc.code, "TEST_ERROR")
        self.assertEqual(exc.message, "test message")
        self.assertEqual(exc.details, {})

    def test_app_error_with_details(self) -> None:
        """Test AppError with details."""
        exc = AppError("TEST_ERROR", "test message", {"key": "value"})
        self.assertEqual(exc.details, {"key": "value"})


class ErrorStatusCodeTests(unittest.TestCase):
    """Tests for exception status codes."""

    def test_not_found_error_status_code(self) -> None:
        """Test NotFoundError status code."""
        exc = NotFoundError("resource", "id")
        self.assertEqual(exc.status_code, 404)

    def test_validation_error_status_code(self) -> None:
        """Test ValidationError status code."""
        exc = ValidationError("validation failed")
        self.assertEqual(exc.status_code, 422)

    def test_authentication_error_status_code(self) -> None:
        """Test AuthenticationError status code."""
        exc = AuthenticationError()
        self.assertEqual(exc.status_code, 401)

    def test_access_denied_error_status_code(self) -> None:
        """Test AccessDeniedError status code."""
        exc = AccessDeniedError()
        self.assertEqual(exc.status_code, 403)

    def test_configuration_error_status_code(self) -> None:
        """Test AppConfigurationError status code."""
        exc = AppConfigurationError("config error")
        self.assertEqual(exc.status_code, 500)

    def test_database_error_status_code(self) -> None:
        """Test DatabaseError status code."""
        exc = DatabaseError("db error")
        self.assertEqual(exc.status_code, 500)

    def test_external_service_error_status_code(self) -> None:
        """Test ExternalServiceError status code."""
        exc = ExternalServiceError("service", "error")
        self.assertEqual(exc.status_code, 503)

    def test_rate_limit_error_status_code(self) -> None:
        """Test RateLimitError status code."""
        exc = RateLimitError()
        self.assertEqual(exc.status_code, 429)

    def test_conflict_error_status_code(self) -> None:
        """Test ConflictError status code."""
        exc = ConflictError("conflict")
        self.assertEqual(exc.status_code, 409)


class ErrorResponseTests(unittest.TestCase):
    """Tests for error_response utility function."""

    def test_error_response_format(self) -> None:
        """Test error_response returns correct format."""
        exc = AppError("TEST_CODE", "test message", {"detail": "info"})
        response = error_response(exc)
        
        self.assertEqual(response["code"], "TEST_CODE")
        self.assertEqual(response["message"], "test message")
        self.assertEqual(response["details"], {"detail": "info"})

    def test_not_found_error_response(self) -> None:
        """Test NotFoundError response."""
        exc = NotFoundError("task", "task-123")
        response = error_response(exc)
        
        self.assertEqual(response["code"], "NOT_FOUND")
        self.assertIn("task", response["message"])
        self.assertIn("task-123", response["message"])
        self.assertEqual(response["details"]["resource"], "task")
        self.assertEqual(response["details"]["id"], "task-123")


class SpecificErrorTests(unittest.TestCase):
    """Tests for specific error types."""

    def test_download_error(self) -> None:
        """Test DownloadError."""
        exc = DownloadError("download failed", url="http://example.com")
        self.assertEqual(exc.code, "DOWNLOAD_ERROR")
        self.assertEqual(exc.details["url"], "http://example.com")

    def test_transcribe_error(self) -> None:
        """Test TranscribeApiError."""
        exc = TranscribeApiError("transcribe failed", file_path="/path/to/file.mp4")
        self.assertEqual(exc.code, "TRANSCRIBE_ERROR")
        self.assertEqual(exc.details["file_path"], "/path/to/file.mp4")

    def test_task_cancelled_error(self) -> None:
        """Test TaskCancelledError."""
        exc = TaskCancelledError("task-123")
        self.assertEqual(exc.code, "TASK_CANCELLED")
        self.assertIn("task-123", exc.message)
        self.assertEqual(exc.details["task_id"], "task-123")

    def test_external_service_error(self) -> None:
        """Test ExternalServiceError."""
        exc = ExternalServiceError("Qwen", "timeout", retry_after=30)
        self.assertEqual(exc.code, "EXTERNAL_SERVICE_ERROR")
        self.assertIn("Qwen", exc.message)
        self.assertEqual(exc.details["service"], "Qwen")
        self.assertEqual(exc.details["retry_after"], 30)


if __name__ == "__main__":
    unittest.main()
"""Tests for the unified AppConfig system."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from media_tools.core.config import (
    _get_env_bool,
    _get_env_int,
    _get_env_str,
    get_app_config,
    get_runtime_setting,
    get_runtime_setting_bool,
    get_runtime_setting_int,
    normalize_download_proxy,
    setup_system_proxies,
)


class AppConfigTests(unittest.TestCase):
    """Tests for AppConfig class."""

    def setUp(self) -> None:
        from media_tools.core.config import _invalidate_settings_cache

        _invalidate_settings_cache()

    def test_app_config_is_singleton(self) -> None:
        """Verify that get_app_config returns the same instance."""
        config1 = get_app_config()
        config2 = get_app_config()
        self.assertIs(config1, config2)

    def test_concurrency_default(self) -> None:
        """Test concurrency default value."""
        config = get_app_config()
        self.assertEqual(config.concurrency, 10)

    def test_auto_transcribe_default(self) -> None:
        """Test auto_transcribe returns bool value."""
        config = get_app_config()
        # Value may be True or False depending on database state
        # Just verify it returns a boolean
        self.assertIsInstance(config.auto_transcribe, bool)

    def test_auto_delete_default(self) -> None:
        """Test auto_delete default value."""
        config = get_app_config()
        self.assertTrue(config.auto_delete)

    def test_debug_mode_default(self) -> None:
        """Test debug_mode default value."""
        config = get_app_config()
        self.assertFalse(config.debug_mode)

    def test_log_level_default(self) -> None:
        """Test log_level default value."""
        config = get_app_config()
        self.assertEqual(config.log_level, "INFO")

    def test_output_path_returns_absolute_path(self) -> None:
        """Test output_path returns absolute path."""
        config = get_app_config()
        self.assertTrue(config.output_path.is_absolute())

    def test_describe_returns_dict(self) -> None:
        """Test describe method returns expected structure."""
        config = get_app_config()
        desc = config.describe()

        self.assertIn("runtime", desc)
        self.assertIn("static", desc)
        self.assertIn("environment", desc)

        # Verify runtime config
        self.assertIn("concurrency", desc["runtime"])
        self.assertIn("auto_transcribe", desc["runtime"])
        self.assertIn("auto_delete", desc["runtime"])
        self.assertIn("api_key_set", desc["runtime"])

        # Verify no sensitive data exposed
        self.assertNotIn("api_key", desc["runtime"])
        self.assertNotIn("cookie", desc["static"])

    def test_validate_returns_errors(self) -> None:
        """Test validate method returns validation errors."""
        config = get_app_config()
        errors = config.validate()
        # Should return a list (possibly empty)
        self.assertIsInstance(errors, list)


class EnvVarHelperTests(unittest.TestCase):
    """Tests for environment variable helper functions."""

    def test_get_env_bool_true_values(self) -> None:
        """Test _get_env_bool with various true values."""
        with patch.dict(os.environ, {"TEST_TRUE": "true"}):
            self.assertTrue(_get_env_bool("TEST_TRUE"))

        with patch.dict(os.environ, {"TEST_TRUE": "1"}):
            self.assertTrue(_get_env_bool("TEST_TRUE"))

        with patch.dict(os.environ, {"TEST_TRUE": "yes"}):
            self.assertTrue(_get_env_bool("TEST_TRUE"))

        with patch.dict(os.environ, {"TEST_TRUE": "on"}):
            self.assertTrue(_get_env_bool("TEST_TRUE"))

    def test_get_env_bool_false_values(self) -> None:
        """Test _get_env_bool with various false values."""
        with patch.dict(os.environ, {"TEST_FALSE": "false"}):
            self.assertFalse(_get_env_bool("TEST_FALSE"))

        with patch.dict(os.environ, {"TEST_FALSE": "0"}):
            self.assertFalse(_get_env_bool("TEST_FALSE"))

        with patch.dict(os.environ, {"TEST_FALSE": "no"}):
            self.assertFalse(_get_env_bool("TEST_FALSE"))

        with patch.dict(os.environ, {"TEST_FALSE": "off"}):
            self.assertFalse(_get_env_bool("TEST_FALSE"))

    def test_get_env_bool_default(self) -> None:
        """Test _get_env_bool returns default for missing env var."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(_get_env_bool("MISSING_VAR", True))
            self.assertFalse(_get_env_bool("MISSING_VAR", False))

    def test_get_env_int_valid(self) -> None:
        """Test _get_env_int with valid integer."""
        with patch.dict(os.environ, {"TEST_INT": "42"}):
            self.assertEqual(_get_env_int("TEST_INT"), 42)

    def test_get_env_int_invalid(self) -> None:
        """Test _get_env_int returns default for invalid value."""
        with patch.dict(os.environ, {"TEST_INT": "not_a_number"}):
            self.assertEqual(_get_env_int("TEST_INT", 10), 10)

    def test_get_env_int_default(self) -> None:
        """Test _get_env_int returns default for missing env var."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_get_env_int("MISSING_VAR", 99), 99)

    def test_get_env_str(self) -> None:
        """Test _get_env_str."""
        with patch.dict(os.environ, {"TEST_STR": "  hello  "}):
            self.assertEqual(_get_env_str("TEST_STR"), "hello")

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_get_env_str("MISSING_VAR", "default"), "default")

    def test_setup_system_proxies_syncs_no_proxy(self) -> None:
        """System proxy sync must preserve bypass rules for localhost/intranet hosts."""
        proxies = {
            "http": "http://127.0.0.1:7890",
            "https": "http://127.0.0.1:7890",
            "no": "localhost,127.0.0.1,*.local",
        }
        with patch.dict(os.environ, {}, clear=True), patch("urllib.request.getproxies", return_value=proxies):
            setup_system_proxies()

            self.assertEqual(os.environ["http_proxy"], "http://127.0.0.1:7890")
            self.assertEqual(os.environ["https_proxy"], "http://127.0.0.1:7890")
            self.assertEqual(os.environ["no_proxy"], "localhost,127.0.0.1,*.local")

    def test_setup_system_proxies_respects_explicit_env_even_if_empty(self) -> None:
        """An existing env var, including an empty one, is an explicit user choice."""
        proxies = {"http": "http://127.0.0.1:7890", "no": "localhost"}
        with (
            patch.dict(os.environ, {"HTTP_PROXY": "", "NO_PROXY": ""}, clear=True),
            patch(
                "urllib.request.getproxies",
                return_value=proxies,
            ),
        ):
            setup_system_proxies()

            self.assertNotIn("http_proxy", os.environ)
            self.assertNotIn("no_proxy", os.environ)
            self.assertEqual(os.environ["HTTP_PROXY"], "")
            self.assertEqual(os.environ["NO_PROXY"], "")

    def test_normalize_download_proxy(self) -> None:
        """Download proxy values distinguish inherit, direct, and explicit proxy."""
        self.assertIsNone(normalize_download_proxy(""))
        self.assertIsNone(normalize_download_proxy("   "))
        self.assertEqual(normalize_download_proxy("direct"), "")
        self.assertEqual(normalize_download_proxy("NO-PROXY"), "")
        self.assertEqual(normalize_download_proxy(" http://127.0.0.1:7890 "), "http://127.0.0.1:7890")


class RuntimeSettingTests(unittest.TestCase):
    """Tests for runtime setting functions."""

    @patch("media_tools.core.config._get_system_setting")
    def test_get_runtime_setting_returns_db_value(self, mock_get: MagicMock) -> None:
        """Test get_runtime_setting returns database value."""
        mock_get.return_value = "custom_value"
        result = get_runtime_setting("test_key")
        self.assertEqual(result, "custom_value")

    @patch("media_tools.core.config._get_system_setting")
    def test_get_runtime_setting_returns_default(self, mock_get: MagicMock) -> None:
        """Test get_runtime_setting returns default when DB returns None."""
        mock_get.return_value = None
        result = get_runtime_setting("concurrency")
        self.assertEqual(result, "10")  # From _RUNTIME_DEFAULTS

    @patch("media_tools.core.config._get_system_setting")
    def test_get_runtime_setting_bool(self, mock_get: MagicMock) -> None:
        """Test get_runtime_setting_bool."""
        mock_get.return_value = "true"
        self.assertTrue(get_runtime_setting_bool("test_key"))

        mock_get.return_value = "false"
        self.assertFalse(get_runtime_setting_bool("test_key"))

    @patch("media_tools.core.config._get_system_setting")
    def test_get_runtime_setting_int(self, mock_get: MagicMock) -> None:
        """Test get_runtime_setting_int."""
        mock_get.return_value = "42"
        self.assertEqual(get_runtime_setting_int("test_key"), 42)


if __name__ == "__main__":
    unittest.main()

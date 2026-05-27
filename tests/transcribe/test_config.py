from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from media_tools.transcribe.config import load_config
from media_tools.transcribe.errors import ConfigurationError


class ConfigTests(unittest.TestCase):
    def test_load_config_uses_expected_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = load_config()

        self.assertEqual(config.app_url, "https://www.qianwen.com/discover")
        self.assertEqual(config.default_account_strategy, "round-robin")
        self.assertEqual(config.export_concurrency, 2)
        self.assertEqual(config.paths.download_dir.name, "downloads")

    def test_load_config_rejects_invalid_export_concurrency(self) -> None:
        with patch.dict(os.environ, {"QWEN_EXPORT_CONCURRENCY": "bad"}, clear=True):
            with self.assertRaises(ConfigurationError):
                load_config()

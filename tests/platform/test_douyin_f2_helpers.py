from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from f2.apps.bark.utils import ClientConfManager as BarkClientConfManager

from media_tools.douyin.core.f2_helper import get_f2_kwargs
from media_tools.platform.douyin import _prepare_f2_temp_dir


class F2HelperTests(unittest.TestCase):
    def test_get_f2_kwargs_uses_short_temp_naming_and_all_interval(self) -> None:
        class FakeConfig:
            def __init__(self, downloads_path: Path) -> None:
                self._downloads_path = downloads_path
                self.project_root = downloads_path.parent

            def get_cookie(self) -> str:
                return "cookie-value"

            def get_download_path(self) -> Path:
                return self._downloads_path

        with tempfile.TemporaryDirectory() as tmp_dir:
            downloads_path = Path(tmp_dir) / "downloads"
            fake_config = FakeConfig(downloads_path)

            with (
                patch("media_tools.douyin.core.f2_helper.get_config", return_value=fake_config),
                patch("media_tools.douyin.core.f2_helper.ConfigManager") as mock_config_manager,
                patch("media_tools.core.cookie_manager.CookieManager.get_cookie", return_value=None),
            ):
                mock_config_manager.return_value.config = {
                    "douyin": {
                        "headers": {"X-F2": "1"},
                        "max_tasks": 10,
                    }
                }

                kwargs = get_f2_kwargs()

        self.assertEqual(kwargs["app_name"], "douyin")
        self.assertEqual(kwargs["mode"], "post")
        self.assertEqual(kwargs["path"], str(downloads_path))
        self.assertEqual(kwargs["cookie"], "cookie-value")
        self.assertEqual(kwargs["interval"], "all")
        self.assertEqual(kwargs["naming"], "{aweme_id}")
        self.assertEqual(kwargs["headers"]["X-F2"], "1")
        self.assertFalse(BarkClientConfManager.enable_bark())

    def test_prepare_f2_temp_dir_recreates_staging_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            downloads_path = Path(tmp_dir) / "downloads"
            stale_root = downloads_path / "douyin"
            (stale_root / "post").mkdir(parents=True)
            (stale_root / "post" / "stale.tmp").write_text("stale", encoding="utf-8")

            prepared = _prepare_f2_temp_dir(downloads_path)

            self.assertEqual(prepared, stale_root)
            self.assertTrue(prepared.exists())
            self.assertEqual(list(prepared.iterdir()), [])


if __name__ == "__main__":
    unittest.main()

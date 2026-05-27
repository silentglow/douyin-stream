from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_tools.transcribe.auth_state import (
    build_qwen_storage_state,
    build_qwen_storage_state_from_cookie_string,
    has_qwen_auth_state,
    persist_qwen_auth_state,
    resolve_qwen_auth_state,
)


class AuthStateTests(unittest.TestCase):
    def test_build_qwen_storage_state_keeps_core_and_marker_cookies(self) -> None:
        state = build_qwen_storage_state(
            {
                "tongyi_sso_ticket": "ticket-value",
                "cookie2": "cookie2-value",
                "random": "ignored",
                "csrf_token": "csrf-value",
            }
        )

        cookie_names = [cookie["name"] for cookie in state["cookies"]]
        self.assertIn("tongyi_sso_ticket", cookie_names)
        self.assertIn("cookie2", cookie_names)
        self.assertIn("csrf_token", cookie_names)
        self.assertNotIn("random", cookie_names)

    def test_build_qwen_storage_state_from_cookie_string_validates_required_fields(self) -> None:
        state = build_qwen_storage_state_from_cookie_string(
            "tongyi_sso_ticket=abc; login_aliyunid_ticket=def; cookie2=ghi"
        )
        self.assertTrue(state["cookies"])
        self.assertTrue(any(cookie["name"] == "tongyi_sso_ticket" for cookie in state["cookies"]))

    def test_has_qwen_auth_state_accepts_valid_file_without_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            auth_path = Path(tmp_dir) / "qwen-storage-state.json"
            auth_path.write_text(
                json.dumps({"cookies": [{"name": "tongyi_sso_ticket", "value": "abc"}], "origins": []}),
                encoding="utf-8",
            )
            self.assertTrue(has_qwen_auth_state(auth_path))

    def test_persist_qwen_auth_state_writes_file_for_default_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            auth_path = root / ".auth" / "qwen-storage-state.json"
            state = {"cookies": [{"name": "tongyi_sso_ticket", "value": "abc"}], "origins": []}

            with patch.dict(
                os.environ,
                {
                    "MEDIA_TOOLS_PROJECT_ROOT": str(root),
                    "QWEN_AUTH_STATE_PATH": str(auth_path),
                },
                clear=True,
            ):
                from media_tools.douyin.core.config_mgr import reset_config

                reset_config()
                persist_qwen_auth_state(state, auth_path)
                self.assertTrue(auth_path.exists())

    def test_resolve_qwen_auth_state_falls_back_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            auth_path = root / ".auth" / "qwen-storage-state.json"
            state = {"cookies": [{"name": "tongyi_sso_ticket", "value": "abc"}], "origins": []}

            with patch.dict(
                os.environ,
                {
                    "MEDIA_TOOLS_PROJECT_ROOT": str(root),
                    "QWEN_AUTH_STATE_PATH": str(auth_path),
                },
                clear=True,
            ):
                from media_tools.douyin.core.config_mgr import reset_config

                reset_config()
                persist_qwen_auth_state(state, auth_path)
                with patch("media_tools.transcribe.auth_state._get_active_qwen_cookie_from_pool", return_value=None):
                    resolved = resolve_qwen_auth_state(auth_path)
                self.assertEqual(resolved.source, "file")
                self.assertIsInstance(resolved.storage_state, dict)


if __name__ == "__main__":
    unittest.main()

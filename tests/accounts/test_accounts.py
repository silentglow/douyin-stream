from __future__ import annotations

from pathlib import Path
import json
import os
import tempfile
from unittest.mock import patch
import unittest

from media_tools.transcribe.accounts import load_accounts_config, resolve_auth_state_path
from media_tools.transcribe.errors import ConfigurationError


class AccountsTests(unittest.TestCase):
    def test_load_accounts_config_reads_json_array(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            accounts_path = Path(tmp_dir) / "accounts.json"
            accounts_path.write_text(
                json.dumps([{"id": "account-a", "label": "主账号", "storageStatePath": ".auth/account-a.json"}]),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"QWEN_ACCOUNTS_FILE": str(accounts_path)}, clear=True):
                path, accounts = load_accounts_config()
                self.assertTrue(path.samefile(accounts_path))
                self.assertEqual(len(accounts), 1)
                self.assertEqual(accounts[0].id, "account-a")

    def test_resolve_auth_state_path_rejects_unknown_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            accounts_path = Path(tmp_dir) / "accounts.json"
            accounts_path.write_text("[]", encoding="utf-8")

            with patch.dict(os.environ, {"QWEN_ACCOUNTS_FILE": str(accounts_path)}, clear=True):
                with self.assertRaises(ConfigurationError):
                    resolve_auth_state_path(account_id="missing")

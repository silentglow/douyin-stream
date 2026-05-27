from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from media_tools.transcribe.flow import build_export_output_path, record_flow_quota_usage, save_debug_artifacts
from media_tools.transcribe.quota import QuotaSnapshot
from media_tools.transcribe.runtime import ExportConfig


class FlowTests(unittest.TestCase):
    def test_build_export_output_path_uses_stem_stamp_and_extension(self) -> None:
        output = build_export_output_path(
            input_path="/tmp/demo/video.mp4",
            output_dir="/tmp/exports",
            export_config=ExportConfig(file_type=3, extension=".md", label="md"),
            run_stamp="2026-04-10T00-00-00",
        )

        self.assertEqual(output.name, "video-2026-04-10T00-00-00.md")
        self.assertEqual(output.parent.name, "exports")

    def test_save_debug_artifacts_writes_both_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifacts = save_debug_artifacts(
                output_dir=tmp_dir,
                output_base="sample",
                run_stamp="stamp",
                transcript_json={"a": 1},
                doc_edit_json={"b": 2},
            )

            self.assertTrue(artifacts.transcript_path.exists())
            self.assertTrue(artifacts.doc_edit_path.exists())
            self.assertIn('"a": 1', artifacts.transcript_path.read_text(encoding="utf-8"))
            self.assertIn('"b": 2', artifacts.doc_edit_path.read_text(encoding="utf-8"))

    def test_record_flow_quota_usage_returns_consumed_minutes_and_logs(self) -> None:
        messages: list[str] = []

        def log(message: str) -> None:
            messages.append(message)

        before = QuotaSnapshot(raw={}, used_upload=0, total_upload=100, remaining_upload=80, gratis_upload=False, free=False)
        after = QuotaSnapshot(raw={}, used_upload=0, total_upload=100, remaining_upload=72, gratis_upload=False, free=False)

        from unittest.mock import patch

        with patch("media_tools.transcribe.flow.record_quota_consumption") as mocked_record:
            consumed = record_flow_quota_usage(
                account_id="account-a",
                before_snapshot=before,
                after_snapshot=after,
                log=log,
            )

        self.assertEqual(consumed, 8)
        mocked_record.assert_called_once()
        self.assertTrue(any("tracked quota consumption" in message for message in messages))

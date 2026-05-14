from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from media_tools.transcribe.worker import run_pipeline_for_user


class PipelineWorkerRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_download_uses_router(self) -> None:
        update_progress = AsyncMock()
        download_mock = object()
        orchestrator = SimpleNamespace(transcribe_batch=AsyncMock(return_value=SimpleNamespace(success=1, failed=0, results=[])))
        fake_config = SimpleNamespace()

        with patch("media_tools.bilibili.core.downloader.download_up_by_url", download_mock), patch(
            "media_tools.transcribe.worker.asyncio.to_thread",
            new=AsyncMock(return_value={"success": True, "new_files": ["/tmp/video.mp4"]}),
        ) as mocked_to_thread, patch(
            "media_tools.core.config.load_pipeline_config",
            return_value=fake_config,
        ), patch(
            "media_tools.transcribe.service.create_orchestrator",
            return_value=orchestrator,
        ):
            result = await run_pipeline_for_user(
                url="https://space.bilibili.com/123",
                max_counts=1,
                update_progress_fn=update_progress,
                delete_after=False,
            )

        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["failed_count"], 0)
        mocked_to_thread.assert_awaited_once()
        self.assertIs(mocked_to_thread.await_args.args[0], download_mock)
        self.assertEqual(
            mocked_to_thread.await_args.args[1:],
            ("https://space.bilibili.com/123", 1, True, None, None),
        )


if __name__ == "__main__":
    unittest.main()


from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import unittest

from media_tools.transcribe.worker import run_pipeline_for_user


class PipelineWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_pipeline_for_user_uses_threaded_download_path(self) -> None:
        update_progress = AsyncMock()
        download_mock = object()
        orchestrator = SimpleNamespace(transcribe_batch=AsyncMock(return_value=SimpleNamespace(success=1, failed=0, results=[])))
        fake_config = SimpleNamespace()

        with patch("media_tools.transcribe.download_router.download_by_url", download_mock), patch(
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
                url="https://www.douyin.com/user/test",
                max_counts=1,
                update_progress_fn=update_progress,
                delete_after=False,
            )

        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["failed_count"], 0)
        mocked_to_thread.assert_awaited_once()
        self.assertIs(mocked_to_thread.await_args.args[0], download_mock)
        # Args: (url, max_counts, disable_auto_transcribe=True, skip_existing=True, task_id=None)
        self.assertEqual(mocked_to_thread.await_args.args[1:], ("https://www.douyin.com/user/test", 1, True, True, None))
        orchestrator.transcribe_batch.assert_awaited_once()
        # 下载和转写阶段现在带 pipeline_progress 计数器
        update_progress.assert_any_await(0.1, "正在下载视频...", "download", {"download": {"done": 0, "total": 1}})
        update_progress.assert_any_await(0.4, "下载完成，准备转写 1 个视频...", "transcribe", {"download": {"done": 1, "total": 1}})
        update_progress.assert_any_await(1.0, "流水线完成: 成功 1, 失败 0", "done", None)


if __name__ == "__main__":
    unittest.main()

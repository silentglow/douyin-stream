"""Tests for media_tools.scheduler.dispatcher."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from media_tools.scheduler.dispatcher import (
    _WORKER_DISPATCHERS,
    _retry_task_worker,
    _start_task_worker,
    dispatch_new_task,
)


# ---------------------------------------------------------------------------
# 1. _WorkerDispatch matching logic
# ---------------------------------------------------------------------------
class TestWorkerDispatchMatching(unittest.TestCase):
    """Verify that _WORKER_DISPATCHERS entries match the expected (task_type, params) pairs."""

    def test_pipeline_single_url_matches_entry_1(self):
        entry = _WORKER_DISPATCHERS[0]
        self.assertTrue(entry.match("pipeline", {"url": "https://example.com/v"}))
        self.assertFalse(entry.match("pipeline", {"video_urls": ["a"]}))

    def test_pipeline_batch_video_urls_matches_entry_2(self):
        entry = _WORKER_DISPATCHERS[1]
        self.assertTrue(entry.match("pipeline", {"video_urls": ["a", "b"]}))
        self.assertFalse(entry.match("pipeline", {"url": "x"}))

    def test_download_video_urls_matches_entry_3(self):
        entry = _WORKER_DISPATCHERS[2]
        self.assertTrue(entry.match("download", {"video_urls": ["a"]}))

    def test_creator_sync_incremental_matches_entry_4(self):
        entry = _WORKER_DISPATCHERS[3]
        self.assertTrue(entry.match("creator_sync_incremental", {"uid": "123"}))
        self.assertTrue(entry.match("creator_sync", {"uid": "123"}))

    def test_full_sync_incremental_matches_entry_5(self):
        entry = _WORKER_DISPATCHERS[4]
        self.assertTrue(entry.match("full_sync_incremental", {"mode": "incremental"}))
        self.assertTrue(entry.match("full_sync", {"mode": "full"}))

    def test_creator_transcribe_matches_entry_6(self):
        entry = _WORKER_DISPATCHERS[5]
        self.assertTrue(entry.match("creator_transcribe", {}))
        self.assertTrue(entry.match("creator_transcribe", {"creator_uid": "abc"}))

    def test_local_transcribe_matches_entry_7(self):
        entry = _WORKER_DISPATCHERS[6]
        self.assertTrue(entry.match("local_transcribe", {"file_paths": ["/tmp/a.mp4"]}))

    def test_recover_aweme_transcribe_matches_entry_8(self):
        entry = _WORKER_DISPATCHERS[7]
        self.assertTrue(entry.match("recover_aweme_transcribe", {}))

    def test_no_match_for_unknown_type(self):
        for entry in _WORKER_DISPATCHERS:
            self.assertFalse(entry.match("unknown_type", {}))

    def test_pipeline_single_does_not_match_batch(self):
        """Entry 1 should not match when only video_urls is present."""
        entry = _WORKER_DISPATCHERS[0]
        self.assertFalse(entry.match("pipeline", {"video_urls": ["x"]}))

    def test_pipeline_batch_does_not_match_single(self):
        """Entry 2 should not match when only url is present."""
        entry = _WORKER_DISPATCHERS[1]
        self.assertFalse(entry.match("pipeline", {"url": "https://x.com"}))


# ---------------------------------------------------------------------------
# 2. _start_task_worker
# ---------------------------------------------------------------------------
class TestStartTaskWorker(unittest.IsolatedAsyncioTestCase):
    @patch("media_tools.scheduler.dispatcher._register_background_task")
    @patch("media_tools.scheduler.dispatcher.PipelineWorker")
    async def test_matching_task_returns_expected_dict(self, mock_pw_cls, mock_register):
        mock_worker = MagicMock()
        mock_pw_cls.return_value = mock_worker
        mock_worker.execute.return_value = MagicMock()
        mock_register.return_value = MagicMock()

        result = await _start_task_worker("tid-1", "pipeline", {"url": "https://example.com"})

        self.assertEqual(result["task_id"], "tid-1")
        self.assertEqual(result["status"], "started")
        self.assertIn("Pipeline", result["message"])
        mock_register.assert_called_once()

    @patch("media_tools.scheduler.dispatcher._register_background_task")
    async def test_unknown_task_type_raises_400(self, mock_register):
        with self.assertRaises(HTTPException) as ctx:
            await _start_task_worker("tid-x", "no_such_type", {})
        self.assertEqual(ctx.exception.status_code, 400)
        mock_register.assert_not_called()

    @patch("media_tools.scheduler.dispatcher._register_background_task")
    @patch("media_tools.scheduler.dispatcher.CreatorSyncWorker")
    async def test_creator_sync_start(self, mock_cls, mock_register):
        mock_cls.return_value.execute.return_value = MagicMock()
        mock_register.return_value = MagicMock()

        result = await _start_task_worker("tid-cs", "creator_sync_incremental", {"uid": "u1"})
        self.assertEqual(result["task_id"], "tid-cs")
        self.assertEqual(result["status"], "started")

    @patch("media_tools.scheduler.dispatcher._register_background_task")
    @patch("media_tools.scheduler.dispatcher.AwemeRecoverWorker")
    async def test_recover_aweme_start(self, mock_cls, mock_register):
        mock_cls.return_value.execute.return_value = MagicMock()
        mock_register.return_value = MagicMock()

        result = await _start_task_worker(
            "tid-ar", "recover_aweme_transcribe", {"creator_uid": "c1", "aweme_id": "a1", "title": "t"}
        )
        self.assertEqual(result["task_id"], "tid-ar")
        self.assertIn("recover", result["message"].lower())


# ---------------------------------------------------------------------------
# 3. dispatch_new_task
# ---------------------------------------------------------------------------
class TestDispatchNewTask(unittest.IsolatedAsyncioTestCase):
    @patch("media_tools.scheduler.dispatcher._register_background_task")
    @patch("media_tools.scheduler.dispatcher.notify_task_update", new_callable=AsyncMock)
    @patch("media_tools.scheduler.dispatcher.TaskRepository.create_running")
    @patch("media_tools.scheduler.dispatcher.PipelineWorker")
    async def test_creates_task_and_starts_worker(
        self, mock_pw_cls, mock_create, mock_notify, mock_register
    ):
        mock_pw_cls.return_value.execute.return_value = MagicMock()
        mock_register.return_value = MagicMock()

        result = await dispatch_new_task("tid-d", "pipeline", {"url": "https://example.com"})

        mock_create.assert_called_once()
        mock_notify.assert_called_once()
        mock_register.assert_called_once()
        self.assertEqual(result["task_id"], "tid-d")
        self.assertEqual(result["status"], "started")

    @patch("media_tools.scheduler.dispatcher._register_background_task")
    @patch("media_tools.scheduler.dispatcher.notify_task_update", new_callable=AsyncMock)
    @patch("media_tools.scheduler.dispatcher.TaskRepository.create_running")
    async def test_unknown_type_raises_400(self, mock_create, mock_notify, mock_register):
        with self.assertRaises(HTTPException) as ctx:
            await dispatch_new_task("tid-y", "nope", {})
        self.assertEqual(ctx.exception.status_code, 400)


# ---------------------------------------------------------------------------
# 4. _retry_task_worker
# ---------------------------------------------------------------------------
class TestRetryTaskWorker(unittest.IsolatedAsyncioTestCase):
    @patch("media_tools.scheduler.dispatcher._register_background_task")
    @patch("media_tools.scheduler.dispatcher.notify_task_update", new_callable=AsyncMock)
    @patch("media_tools.scheduler.dispatcher.TaskRepository.create_running")
    @patch("media_tools.scheduler.dispatcher.PipelineWorker")
    async def test_retry_pipeline_generates_new_task_id(
        self, mock_pw_cls, mock_create, mock_notify, mock_register
    ):
        mock_pw_cls.return_value.execute.return_value = MagicMock()
        mock_register.return_value = MagicMock()

        result = await _retry_task_worker(
            "old-tid", "pipeline", {"url": "https://example.com", "max_counts": 3}
        )

        # New task_id should differ from old
        self.assertNotEqual(result["task_id"], "old-tid")
        self.assertEqual(result["status"], "started")
        self.assertIn("retry", result["message"].lower())
        mock_create.assert_called_once()
        mock_notify.assert_called_once()
        mock_register.assert_called_once()

    @patch("media_tools.scheduler.dispatcher._register_background_task")
    @patch("media_tools.scheduler.dispatcher.notify_task_update", new_callable=AsyncMock)
    @patch("media_tools.scheduler.dispatcher.TaskRepository.create_running")
    @patch("media_tools.scheduler.dispatcher.CreatorSyncWorker")
    async def test_retry_creator_sync_uses_retry_task_type(
        self, mock_cls, mock_create, mock_notify, mock_register
    ):
        mock_cls.return_value.execute.return_value = MagicMock()
        mock_register.return_value = MagicMock()

        result = await _retry_task_worker("old", "creator_sync_incremental", {"uid": "u1", "mode": "incremental"})

        # Verify create_running was called with the derived task_type
        call_args = mock_create.call_args
        self.assertEqual(call_args[0][1], "creator_sync_incremental")
        self.assertNotEqual(result["task_id"], "old")

    @patch("media_tools.scheduler.dispatcher._register_background_task")
    @patch("media_tools.scheduler.dispatcher.notify_task_update", new_callable=AsyncMock)
    @patch("media_tools.scheduler.dispatcher.TaskRepository.create_running")
    async def test_retry_unknown_type_raises_400(self, mock_create, mock_notify, mock_register):
        with self.assertRaises(HTTPException) as ctx:
            await _retry_task_worker("old", "nonexistent", {})
        self.assertEqual(ctx.exception.status_code, 400)

    @patch("media_tools.scheduler.dispatcher._register_background_task")
    @patch("media_tools.scheduler.dispatcher.notify_task_update", new_callable=AsyncMock)
    @patch("media_tools.scheduler.dispatcher.TaskRepository.create_running")
    @patch("media_tools.scheduler.dispatcher.DownloadWorker")
    async def test_retry_download(self, mock_cls, mock_create, mock_notify, mock_register):
        mock_cls.return_value.execute.return_value = MagicMock()
        mock_register.return_value = MagicMock()

        result = await _retry_task_worker("old-dl", "download", {"video_urls": ["https://example.com/a.mp4"]})
        self.assertEqual(result["status"], "started")
        self.assertIn("retry", result["message"].lower())


# ---------------------------------------------------------------------------
# 5. _create_task
# ---------------------------------------------------------------------------
class TestCreateTask(unittest.IsolatedAsyncioTestCase):
    @patch("media_tools.scheduler.dispatcher.notify_task_update", new_callable=AsyncMock)
    @patch("media_tools.scheduler.dispatcher.TaskRepository.create_running")
    async def test_creates_task_with_correct_params(self, mock_create, mock_notify):
        from media_tools.scheduler.dispatcher import _create_task

        await _create_task("tid-c", "pipeline", {"url": "https://x.com"})

        mock_create.assert_called_once()
        args = mock_create.call_args[0]
        self.assertEqual(args[0], "tid-c")
        self.assertEqual(args[1], "pipeline")
        # Payload should include the original params plus "msg"
        payload = args[2]
        self.assertIn("msg", payload)
        self.assertEqual(payload["url"], "https://x.com")

    @patch("media_tools.scheduler.dispatcher.notify_task_update", new_callable=AsyncMock)
    @patch("media_tools.scheduler.dispatcher.TaskRepository.create_running")
    async def test_notify_called_with_running_status(self, mock_create, mock_notify):
        from media_tools.scheduler.dispatcher import _create_task

        await _create_task("tid-n", "download", {"video_urls": ["a"]})

        mock_notify.assert_called_once()
        notify_args = mock_notify.call_args[0]
        self.assertEqual(notify_args[0], "tid-n")
        self.assertEqual(notify_args[3], "RUNNING")


if __name__ == "__main__":
    unittest.main()

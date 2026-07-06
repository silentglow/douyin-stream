from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from media_tools.download.service import resolve_platform
from media_tools.platform.youtube import fetch_youtube_channel_info


class YoutubePlatformTests(unittest.TestCase):
    def test_resolve_platform(self) -> None:
        self.assertEqual(resolve_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "youtube")
        self.assertEqual(resolve_platform("https://youtu.be/dQw4w9WgXcQ"), "youtube")
        self.assertEqual(resolve_platform("https://www.youtube.com/@GoogleDeepMind"), "youtube")
        self.assertEqual(resolve_platform("https://www.bilibili.com/video/BV1xx411c7m9"), "bilibili")
        self.assertEqual(resolve_platform("https://v.douyin.com/abc/"), "douyin")

    @patch("media_tools.platform.youtube.YoutubeDL")
    def test_fetch_youtube_channel_info(self, mock_ydl) -> None:
        # Mock YoutubeDL context manager behavior
        mock_instance = MagicMock()
        mock_ydl.return_value.__enter__.return_value = mock_instance
        
        # Setup mock return data
        mock_instance.extract_info.return_value = {
            "channel": "Test Channel",
            "channel_id": "UC1234567890",
            "channel_url": "https://www.youtube.com/channel/UC1234567890",
        }

        info = fetch_youtube_channel_info("https://www.youtube.com/@testchannel")
        
        self.assertEqual(info["nickname"], "Test Channel")
        self.assertEqual(info["channel_id"], "UC1234567890")
        self.assertEqual(info["homepage_url"], "https://www.youtube.com/channel/UC1234567890")
        mock_instance.extract_info.assert_called_once_with("https://www.youtube.com/@testchannel", download=False)


if __name__ == "__main__":
    unittest.main()

"""测试视频标题命名修复（LIMIT 10 + pipeline title passthrough）"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from media_tools.store.db import get_db_path, reset_db_cache, set_db_path
from media_tools.transcribe.flow import _get_video_title_from_db, build_export_output_path
from media_tools.transcribe.helpers import _clean_title_for_export, _lookup_video_title
from media_tools.common.runtime import ExportConfig


class CleanTitleForExportTests(unittest.TestCase):
    """测试 _clean_title_for_export 清洗逻辑"""

    def test_strips_hashtags(self):
        raw = "孩子并非是不会思考的未完成版成年人#纳瓦尔宝典 #思维龍卷風"
        result = _clean_title_for_export(raw)
        self.assertEqual(result, "孩子并非是不会思考的未完成版成年人")

    def test_strips_newlines(self):
        raw = "第一行内容\n第二行内容"
        result = _clean_title_for_export(raw)
        self.assertEqual(result, "第一行内容")

    def test_strips_br_tags(self):
        raw = "第一行内容<br>第二行内容"
        result = _clean_title_for_export(raw)
        self.assertEqual(result, "第一行内容")

    def test_truncates_long_titles(self):
        raw = "这是一个非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常长的标题"
        result = _clean_title_for_export(raw)
        self.assertLessEqual(len(result), 50)

    def test_returns_none_for_too_short(self):
        result = _clean_title_for_export("ab")
        self.assertIsNone(result)

    def test_strips_illegal_chars(self):
        raw = 'hello: "world" | test?'
        result = _clean_title_for_export(raw)
        self.assertNotIn(":", result)
        self.assertNotIn('"', result)
        self.assertNotIn("|", result)
        self.assertNotIn("?", result)


class LookupVideoTitleTests(unittest.TestCase):
    """测试 _lookup_video_title 从 DB 查标题"""

    def _create_test_db(self, db_path: Path, aweme_id: str, desc: str):
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS video_metadata (
                aweme_id TEXT PRIMARY KEY,
                uid TEXT,
                desc TEXT,
                fetch_time INTEGER
            )
        """)
        conn.execute(
            "INSERT INTO video_metadata (aweme_id, uid, desc) VALUES (?, ?, ?)",
            (aweme_id, "test_uid", desc),
        )
        conn.commit()
        conn.close()

    def test_finds_title_by_aweme_id_in_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            self._create_test_db(db_path, "7620767195682364133", "孩子并非是不会思考的未完成版成年人#纳瓦尔宝典")

            original = get_db_path()
            try:
                set_db_path(str(db_path))
                reset_db_cache()
                # 模拟 F2 原始格式
                video_path = Path("/downloads/user/7620767195682364133_video.mp4")
                title = _lookup_video_title(video_path)
            finally:
                set_db_path(original)
                reset_db_cache()

            self.assertIsNotNone(title)
            self.assertEqual(title, "孩子并非是不会思考的未完成版成年人")

    def test_returns_none_for_clean_filename(self):
        # 文件名没有 15+ 位数字，应返回 None
        video_path = Path("/downloads/user/孩子并非是不会思考的未完成版成年人.mp4")
        title = _lookup_video_title(video_path)
        self.assertIsNone(title)

    def test_returns_none_when_db_has_no_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            # 建表但不插入数据
            conn = sqlite3.connect(str(db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS video_metadata (
                    aweme_id TEXT PRIMARY KEY, uid TEXT, desc TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS media_assets (
                    asset_id TEXT PRIMARY KEY, title TEXT
                )
            """)
            conn.commit()
            conn.close()

            original = get_db_path()
            try:
                set_db_path(str(db_path))
                reset_db_cache()
                video_path = Path("/downloads/user/7620767195682364133_video.mp4")
                title = _lookup_video_title(video_path)
            finally:
                set_db_path(original)
                reset_db_cache()

            self.assertIsNone(title)


class BuildExportOutputPathWithTitleTests(unittest.TestCase):
    """测试 build_export_output_path 的 title 参数"""

    def test_title_overrides_filename(self):
        output = build_export_output_path(
            input_path="/tmp/7620767195682364133_video.mp4",
            output_dir="/tmp/exports",
            export_config=ExportConfig(file_type=3, extension=".md", label="md"),
            title="孩子并非是不会思考的未完成版成年人",
        )
        self.assertIn("孩子并非是不会思考的未完成版成年人", output.name)
        self.assertTrue(output.name.endswith(".md"))
        # 不应包含 aweme_id
        self.assertNotIn("7620767195682364133", output.name)

    def test_fallback_when_no_title(self):
        output = build_export_output_path(
            input_path="/tmp/7620767195682364133_video.mp4",
            output_dir="/tmp/exports",
            export_config=ExportConfig(file_type=3, extension=".md", label="md"),
            run_stamp="2026-04-15T00-00-00",
            title=None,
        )
        # 没有 title 时 fallback 到 stem-timestamp
        self.assertEqual(output.name, "7620767195682364133_video-2026-04-15T00-00-00.md")


class GetVideoTitleFromDbFallbackTests(unittest.TestCase):
    """测试 _get_video_title_from_db 作为 fallback 的行为"""

    def test_returns_clean_title_for_normal_filename(self):
        path = Path("/downloads/user/孩子并非是不会思考的未完成版成年人.mp4")
        title = _get_video_title_from_db(path)
        self.assertEqual(title, "孩子并非是不会思考的未完成版成年人")

    def test_returns_none_for_aweme_id_filename(self):
        path = Path("/downloads/user/7620767195682364133_video.mp4")
        title = _get_video_title_from_db(path)
        self.assertIsNone(title)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch


class LocalAssetsVisibilityTests(unittest.TestCase):
    def test_local_transcribe_registers_assets_under_local_creator(self) -> None:
        from media_tools.api.routers import creators as creators_router
        from media_tools.api.routers import assets as assets_router
        from media_tools.assets.local import LOCAL_CREATOR_UID, _register_local_assets

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        conn.execute(
            """
            CREATE TABLE creators (
              uid TEXT PRIMARY KEY,
              sec_user_id TEXT,
              nickname TEXT,
              avatar TEXT,
              bio TEXT,
              platform TEXT,
              sync_status TEXT,
              last_fetch_time DATETIME
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE media_assets (
              asset_id TEXT PRIMARY KEY,
              creator_uid TEXT,
              source_url TEXT,
              title TEXT,
              duration INTEGER,
              video_path TEXT,
              video_status TEXT,
              transcript_path TEXT,
              transcript_status TEXT,
              transcript_preview TEXT,
              folder_path TEXT DEFAULT '',
              is_read BOOLEAN DEFAULT 0,
              is_starred BOOLEAN DEFAULT 0,
              transcript_error_type TEXT,
              transcript_last_error TEXT,
              transcript_retry_count INTEGER DEFAULT 0,
              transcript_failed_at DATETIME,
              source_platform TEXT,
              last_task_id TEXT,
              create_time DATETIME,
              update_time DATETIME
            )
            """
        )
        conn.commit()

        tmp_file = Path("/tmp/local_asset_test.mp3")
        tmp_file.write_bytes(b"ok")

        with patch("media_tools.assets.local.get_db_connection", return_value=conn), patch(
            "media_tools.api.routers.creators.get_db_connection",
            return_value=conn,
        ), patch(
            "media_tools.api.routers.assets.get_db_connection",
            return_value=conn,
        ), patch(
            "media_tools.assets.repository.get_db_connection",
            return_value=conn,
        ), patch(
            "media_tools.repositories.creator_repository.get_db_connection",
            return_value=conn,
        ):
            _register_local_assets([str(tmp_file)], delete_after=False)
            creators = creators_router.list_creators()
            local_creator = next((c for c in creators if c["uid"] == LOCAL_CREATOR_UID), None)
            self.assertIsNotNone(local_creator)
            self.assertEqual(local_creator["asset_count"], 1)

            assets = assets_router.list_assets(creator_uid=LOCAL_CREATOR_UID)
            self.assertEqual(len(assets), 1)
            self.assertEqual(assets[0]["title"], tmp_file.stem)


if __name__ == "__main__":
    unittest.main()

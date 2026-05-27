import sqlite3
from datetime import datetime
from pathlib import Path

from media_tools.store.db import get_db_connection, local_asset_id

LOCAL_CREATOR_UID = "local:upload"
LOCAL_CREATOR_NAME = "本地上传"


def _compute_folder_path(file_path: Path, directory_root: str | None) -> str:
    try:
        p = file_path.resolve()
        parent_name = p.parent.name
        return parent_name if parent_name else "根目录"
    except (OSError, ValueError):
        return "(其他)"


def _register_local_assets(file_paths: list[str], delete_after: bool, directory_root: str | None = None) -> None:
    now = datetime.now().isoformat()
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT OR IGNORE INTO creators (uid, sec_user_id, nickname, platform, sync_status, last_fetch_time)
            VALUES (?, ?, ?, ?, 'active', ?)
            """,
            (LOCAL_CREATOR_UID, "", LOCAL_CREATOR_NAME, "local", now),
        )
        for raw_path in file_paths:
            path = Path(raw_path)
            if not path.exists():
                continue
            asset_id = local_asset_id(str(path))
            folder_path = _compute_folder_path(path, directory_root)
            conn.execute(
                """
                INSERT OR IGNORE INTO media_assets
                (asset_id, creator_uid, source_url, title, video_status, transcript_status, folder_path, create_time, update_time)
                VALUES (?, ?, ?, ?, 'downloaded', 'pending', ?, ?, ?)
                """,
                (asset_id, LOCAL_CREATOR_UID, str(path.resolve()), path.stem, folder_path, now, now),
            )
        conn.commit()

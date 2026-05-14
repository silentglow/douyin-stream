"""Backfill missing transcript_preview / transcript_text in the background.

New transcripts write both inline (orchestrator / local worker). This module
handles existing rows that predate those columns, and keeps the FTS5 search
index up to date.
"""
from typing import Optional, Union
import os.path
import sqlite3
import threading
from pathlib import Path

from media_tools.store.db import get_db_connection, update_fts_for_asset
from media_tools.logger import get_logger
from media_tools.transcribe.preview import extract_transcript_preview, extract_transcript_text

logger = get_logger("preview_backfill")

_BATCH = 50
_started = False
_lock = threading.Lock()


def _transcripts_dir() -> Path:
    from media_tools.common.paths import get_project_root
    return get_project_root() / "transcripts"


def _validate_path(base_dir: Path, transcript_path: str) -> Optional[Path]:
    """
    校验并安全拼接 transcript_path

    1. 禁止路径穿越序列 (..)
    2. 禁止空字节和换行符（防止注入）
    3. resolve() 后必须在 base_dir 内

    返回安全的绝对路径，或 None（校验失败）
    """
    base_resolved = base_dir.resolve()

    # 1. 基本校验：禁止空字节、换行符（防止注入）
    # 注：不再检查 ".." 因为文件名可能包含 "...." 这样的合法字符
    # 路径穿越检测由 commonpath 检查（下方的 #2）来完成
    if "\x00" in transcript_path or "\n" in transcript_path or "\r" in transcript_path:
        logger.warning(
            f"[SECURITY] Invalid chars in transcript_path: "
            f"db_value={transcript_path!r}"
        )
        return None

    # 2. 安全拼接 + 路径穿越校验
    try:
        full_path = (base_dir / transcript_path).resolve()

        # 校验路径前缀，禁止穿越到 base_dir 外
        # 使用 os.path.commonpath 而非字符串 startswith，避免符号链接导致误报
        try:
            common = os.path.commonpath([str(full_path), str(base_resolved)])
            if common != str(base_resolved):
                logger.warning(
                    f"[SECURITY] Path traversal attempt detected: "
                    f"db_value={transcript_path!r}, resolved={full_path}, "
                    f"base_dir={base_resolved}"
                )
                return None
        except ValueError:
            pass

        # 3. 校验文件存在且可读
        if not full_path.is_file():
            logger.warning(
                f"[AUDIT] Transcript file not accessible: "
                f"db_value={transcript_path!r}, resolved={full_path}, "
                f"exists={full_path.exists()}, is_file={full_path.is_file()}"
            )
            return None

        return full_path

    except (OSError, ValueError, TypeError) as e:
        logger.warning(
            f"[AUDIT] Path resolution failed: "
            f"db_value={transcript_path!r}, base_dir={base_resolved}, error={type(e).__name__}: {e}"
        )
        return None


def _run() -> None:
    base_dir = _transcripts_dir()
    total = 0
    failed = 0

    try:
        while True:
            with get_db_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT asset_id, title, transcript_path FROM media_assets
                    WHERE transcript_status = 'completed'
                      AND transcript_path IS NOT NULL AND transcript_path != ''
                      AND (transcript_preview IS NULL OR transcript_text IS NULL)
                    LIMIT ?
                    """,
                    (_BATCH,),
                )
                rows = cursor.fetchall()

            if not rows:
                break

            media_updates: list[tuple[str, str, str]] = []

            for row in rows:
                asset_id = row["asset_id"]
                title = row["title"]
                transcript_path = row["transcript_path"]

                # 安全校验路径
                file_path = _validate_path(base_dir, transcript_path)
                if file_path is None:
                    failed += 1
                    continue

                try:
                    preview = extract_transcript_preview(file_path)
                    full_text = extract_transcript_text(file_path)
                    media_updates.append((preview, full_text, asset_id))

                    # Sync to FTS5 index
                    update_fts_for_asset(asset_id, title or "", full_text)

                except (OSError, TypeError, ValueError) as e:
                    # 单条失败不影响批次
                    logger.warning(f"Failed to extract preview/text for {asset_id}: {e}")
                    failed += 1
                    continue

            # 批量更新 DB
            if media_updates:
                with get_db_connection() as conn:
                    conn.executemany(
                        "UPDATE media_assets SET transcript_preview = ?, transcript_text = ? WHERE asset_id = ?",
                        media_updates,
                    )
                    conn.commit()
                total += len(media_updates)

        if total:
            logger.info(f"Backfilled transcript preview/text for {total} rows, failed {failed}")
        elif failed:
            logger.warning(f"Preview/text backfill: {failed} rows failed")

    except (sqlite3.Error, OSError) as exc:
        logger.warning(f"Preview/text backfill aborted: {exc}")


def start_backfill_once() -> None:
    """Kick off backfill in a daemon thread; no-op on subsequent calls."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    t = threading.Thread(target=_run, name="transcript-preview-backfill", daemon=True)
    t.start()

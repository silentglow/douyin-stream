import sqlite3
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from media_tools.db.core import get_db_connection

logger = logging.getLogger(__name__)


def reconcile_transcripts():
    project_root = Path(__file__).parent.parent.parent.parent
    transcripts_dir = project_root / "transcripts"

    if not transcripts_dir.exists():
        raise RuntimeError(f"transcripts 目录不存在: {transcripts_dir}")

    results = {
        "creators_found": 0,
        "assets_created": 0,
        "assets_updated": 0,
        "creators_removed": 0,
        "assets_removed": 0,
        "ghosts_pruned": 0,
    }
    now = datetime.now().isoformat()

    actual_folders = set()
    try:
        for folder in list(transcripts_dir.iterdir()):
            if folder.is_dir() and not folder.name.startswith('.'):
                md_files = list(folder.glob("*.md"))
                if md_files:
                    actual_folders.add(folder.name)
    except FileNotFoundError:
        logger.warning(f"transcripts 目录在遍历时被删除: {transcripts_dir}")
        raise RuntimeError("transcripts 目录不存在")

    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row

        local_creators = conn.execute(
            "SELECT uid, nickname FROM creators WHERE platform='local' AND uid LIKE 'local:%'"
        ).fetchall()
        for creator in local_creators:
            nickname = creator['nickname']
            uid = creator['uid']
            if nickname not in actual_folders and nickname != "本地上传":
                # Capture asset_ids before deletion so we can clean up FTS index
                stale_assets = conn.execute(
                    "SELECT asset_id FROM media_assets WHERE creator_uid = ?",
                    (uid,),
                ).fetchall()
                stale_ids = [str(r['asset_id']) for r in stale_assets if r['asset_id']]
                if stale_ids:
                    placeholders = ",".join("?" * len(stale_ids))
                    conn.execute(f"DELETE FROM assets_fts WHERE asset_id IN ({placeholders})", stale_ids)
                deleted = conn.execute("DELETE FROM media_assets WHERE creator_uid = ?", (uid,))
                conn.execute("DELETE FROM creators WHERE uid = ?", (uid,))
                results['creators_removed'] += 1
                results['assets_removed'] += deleted.rowcount
                logger.info(f"Removed local creator '{nickname}' and {deleted.rowcount} assets")

        from media_tools.services.local_asset_service import LOCAL_CREATOR_UID as legacy_uid
        legacy_assets = conn.execute(
            "SELECT asset_id, title, transcript_path, folder_path FROM media_assets WHERE creator_uid = ?",
            (legacy_uid,)
        ).fetchall()

        creators = conn.execute("SELECT uid, nickname FROM creators").fetchall()
        # 使用 uid 优先，nickname 碰撞时保留最早插入的
        creator_map: dict[str, str] = {}
        for row in creators:
            nickname = row['nickname']
            if nickname not in creator_map:
                creator_map[nickname] = row['uid']

        for asset in legacy_assets:
            folder_name = asset['folder_path'] or ''
            if not folder_name and asset['transcript_path']:
                if '/' in asset['transcript_path']:
                    folder_name = asset['transcript_path'].split('/')[0]

            if not folder_name:
                continue

            target_uid = creator_map.get(folder_name)
            if not target_uid:
                target_uid = f"local:{hashlib.sha1(folder_name.encode()).hexdigest()[:16]}"
                conn.execute(
                    "INSERT OR IGNORE INTO creators (uid, nickname, platform, sync_status, last_fetch_time) VALUES (?, ?, 'local', 'active', ?)",
                    (target_uid, folder_name, now)
                )
                creator_map[folder_name] = target_uid
                results['creators_found'] += 1

            conn.execute(
                "UPDATE media_assets SET creator_uid = ?, folder_path = ? WHERE asset_id = ?",
                (target_uid, folder_name, asset['asset_id'])
            )
            results['assets_updated'] += 1

        conn.execute("DELETE FROM creators WHERE uid = ?", (legacy_uid,))

        for folder_name in actual_folders:
            folder_path = transcripts_dir / folder_name
            creator_uid = creator_map.get(folder_name)

            if not creator_uid:
                creator_uid = f"local:{hashlib.sha1(folder_name.encode()).hexdigest()[:16]}"
                conn.execute(
                    "INSERT OR IGNORE INTO creators (uid, nickname, platform, sync_status, last_fetch_time) VALUES (?, ?, 'local', 'active', ?)",
                    (creator_uid, folder_name, now)
                )
                creator_map[folder_name] = creator_uid
                results['creators_found'] += 1

            batch_count = 0
            for md_file in folder_path.glob("*.md"):
                title = md_file.stem
                asset_id = f"local:{hashlib.sha1(str(md_file.resolve()).encode()).hexdigest()[:24]}"
                relative_path = f"{folder_name}/{md_file.name}"

                existing = conn.execute(
                    "SELECT asset_id FROM media_assets WHERE asset_id = ?",
                    (asset_id,)
                ).fetchone()

                if existing:
                    conn.execute(
                        "UPDATE media_assets SET transcript_status='completed', transcript_path=?, folder_path=?, update_time=? WHERE asset_id=?",
                        (relative_path, folder_name, now, asset_id)
                    )
                    results['assets_updated'] += 1
                else:
                    conn.execute(
                        "INSERT INTO media_assets (asset_id, creator_uid, title, video_status, transcript_status, transcript_path, folder_path, create_time, update_time) VALUES (?, ?, ?, 'downloaded', 'completed', ?, ?, ?, ?)",
                        (asset_id, creator_uid, title, relative_path, folder_name, now, now)
                    )
                    results['assets_created'] += 1

                batch_count += 1
                if batch_count >= 100:
                    conn.commit()
                    batch_count = 0

        # prune：completed 但 transcript_path 指向的文件已不存在 → DB 行已无业务依据
        # 主要原因是用户在 FS 直接删/改名 .md，reconciler 此前只增不减
        completed_rows = conn.execute(
            "SELECT asset_id, transcript_path FROM media_assets "
            "WHERE transcript_status = 'completed' "
            "AND transcript_path IS NOT NULL AND transcript_path != ''"
        ).fetchall()
        ghost_ids: list[str] = []
        for row in completed_rows:
            rel_path = row["transcript_path"]
            full = Path(rel_path)
            if not full.is_absolute():
                full = transcripts_dir / full
            if not full.exists():
                ghost_ids.append(str(row["asset_id"]))
        if ghost_ids:
            placeholders = ",".join("?" * len(ghost_ids))
            conn.execute(f"DELETE FROM assets_fts WHERE asset_id IN ({placeholders})", ghost_ids)
            deleted = conn.execute(
                f"DELETE FROM media_assets WHERE asset_id IN ({placeholders})", ghost_ids
            )
            results["ghosts_pruned"] = deleted.rowcount
            logger.info(f"Pruned {deleted.rowcount} ghost transcripts (file missing on disk)")

        empty = conn.execute(
            "SELECT c.uid FROM creators c LEFT JOIN media_assets m ON c.uid=m.creator_uid WHERE c.platform='local' AND m.asset_id IS NULL"
        ).fetchall()
        for row in empty:
            conn.execute("DELETE FROM creators WHERE uid = ?", (row['uid'],))
            results['creators_removed'] += 1

        conn.commit()

    # 对账 media_assets 与 transcribe_runs 的状态一致性
    run_results = reconcile_transcribe_runs()
    results.update(run_results)

    return {"status": "success", **results}


def reconcile_transcribe_runs():
    """对账 media_assets 与 transcribe_runs 的状态一致性。

    修复三类漂移：
    1. media_assets completed 但 transcribe_runs 无 saved run → 重置为 pending
       （transcribe_runs 记录丢失，需要重新转写）
    2. media_assets 未 completed 但 transcribe_runs 有 saved run → 补全为 completed
       （转写成功但 media_assets 未同步更新）
    3. transcribe_runs saved 但转录文件不存在 → 标记为 failed（幽灵 run）
    """
    results = {
        "assets_reset_from_completed": 0,
        "assets_completed_from_saved": 0,
        "runs_marked_ghost": 0,
    }
    now = datetime.now().isoformat()
    project_root = Path(__file__).parent.parent.parent.parent
    transcripts_dir = project_root / "transcripts"

    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row

        # 1. media_assets completed 但 transcribe_runs 没有 saved run
        completed_assets = conn.execute(
            """
            SELECT ma.asset_id, ma.video_path
            FROM media_assets ma
            LEFT JOIN transcribe_runs tr
                ON ma.asset_id = tr.asset_id AND tr.stage = 'saved'
            WHERE ma.transcript_status = 'completed'
              AND tr.run_id IS NULL
            """
        ).fetchall()

        for row in completed_assets:
            conn.execute(
                "UPDATE media_assets SET transcript_status = 'pending', transcript_path = NULL, transcript_preview = NULL, transcript_text = NULL, update_time = ? WHERE asset_id = ?",
                (now, row["asset_id"]),
            )
            results["assets_reset_from_completed"] += 1
            logger.info(f"重置 media_assets: asset={row['asset_id']} (completed 但无 saved run)")

        # 2. media_assets 不是 completed 但 transcribe_runs 有 saved run
        pending_assets = conn.execute(
            """
            SELECT ma.asset_id, tr.transcript_path
            FROM media_assets ma
            JOIN transcribe_runs tr ON ma.asset_id = tr.asset_id AND tr.stage = 'saved'
            WHERE ma.transcript_status != 'completed'
            """
        ).fetchall()

        for row in pending_assets:
            transcript_path = row["transcript_path"] or ""
            conn.execute(
                "UPDATE media_assets SET transcript_status = 'completed', transcript_path = ?, update_time = ? WHERE asset_id = ?",
                (transcript_path, now, row["asset_id"]),
            )
            results["assets_completed_from_saved"] += 1
            logger.info(f"补全 media_assets: asset={row['asset_id']} (saved run 存在但未 completed)")

        # 3. transcribe_runs saved 但转录文件不存在
        saved_runs = conn.execute(
            """
            SELECT run_id, transcript_path, asset_id
            FROM transcribe_runs
            WHERE stage = 'saved'
              AND transcript_path IS NOT NULL AND transcript_path != ''
            """
        ).fetchall()

        for row in saved_runs:
            tp = row["transcript_path"]
            if not tp:
                continue
            path = Path(tp)
            if not path.is_absolute():
                path = transcripts_dir / path
            if not path.exists():
                conn.execute(
                    "UPDATE transcribe_runs SET stage = 'failed', error_stage = 'saved', error_type = 'ghost_file', last_error = ?, updated_at = ? WHERE run_id = ?",
                    ("转录文件在磁盘上已不存在", now, row["run_id"]),
                )
                results["runs_marked_ghost"] += 1
                logger.info(f"标记幽灵 run: run_id={row['run_id']} asset={row['asset_id']}")

        conn.commit()

    return results

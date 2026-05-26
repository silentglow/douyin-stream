from __future__ import annotations
from typing import Optional

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# 由 archive_old_logs 处理的扩展名（其他文件如 .DS_Store / .gz / .txt 不动）
LOG_SUFFIXES: set[str] = {".log", ".jsonl"}

# 归档子目录名（在 log_dir 下）
ARCHIVE_DIRNAME = "archive"


@dataclass(frozen=True)
class ArchiveOutcome:
    archived_count: int = 0
    failed_count: int = 0
    archive_dir: Optional[Path] = None
    failed_paths: list[str] = field(default_factory=list)


def archive_old_logs(log_dir: Path, days: int = 30) -> ArchiveOutcome:
    """归档 log_dir 顶层 mtime 早于 days 的 .log / .jsonl 文件到 archive 子目录。

    归档目标：log_dir / 'archive' / 'YYYY-MM' / <basename>。
    不删除——保留以供事故回放（CLAUDE.md "业务可靠性 > 工程规范"原则下，
    日志是事故回溯的关键素材，不能因清理需求误删）。

    archive 子目录不参与扫描（避免循环归档），其它子目录也不递归。
    """
    if not log_dir.exists() or not log_dir.is_dir():
        return ArchiveOutcome()

    cutoff_ts = (datetime.now() - timedelta(days=days)).timestamp()
    archive_root = log_dir / ARCHIVE_DIRNAME
    archived = 0
    failed: list[str] = []

    for entry in log_dir.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix not in LOG_SUFFIXES:
            continue
        try:
            mtime = entry.stat().st_mtime
            if mtime >= cutoff_ts:
                continue
            ts = datetime.fromtimestamp(mtime)
            target_dir = archive_root / ts.strftime("%Y-%m")
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / entry.name
            # 同名文件已存在时加 epoch 后缀，避免覆盖
            if target.exists():
                target = target_dir / f"{entry.stem}.{int(mtime)}{entry.suffix}"
            shutil.move(str(entry), str(target))
            archived += 1
        except OSError as e:
            logger.warning(f"归档日志失败 {entry}: {e}")
            failed.append(str(entry))

    return ArchiveOutcome(
        archived_count=archived,
        failed_count=len(failed),
        archive_dir=archive_root if archived > 0 else None,
        failed_paths=failed,
    )

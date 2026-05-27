from __future__ import annotations

import shutil
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from media_tools.transcribe.media_extensions import MEDIA_EXTENSIONS

CleanupFailureReason = Literal[
    "path_outside_root",
    "permission_denied",
    "not_found",
    "unknown",
]

# 派生自 MEDIA_EXTENSIONS 以避免漂移：每加一种媒体格式（如 .mkv/.mov/.webm）都自动可清理。
# 额外补 .wav/.m4a/.aac 是历史上转写产物用过的音频中间格式；.tmp/.part 是下载未完成残片。
ALLOW_SUFFIXES: set[str] = MEDIA_EXTENSIONS | {
    ".wav",
    ".m4a",
    ".aac",
    ".tmp",
    ".part",
}


@dataclass(frozen=True)
class CleanupFailedPath:
    path: str
    reason: CleanupFailureReason


@dataclass(frozen=True)
class CleanupOutcome:
    deleted_count: int = 0
    failed_count: int = 0
    failed_paths: list[CleanupFailedPath] = field(default_factory=list)


def _classify_unlink_error(exc: BaseException) -> CleanupFailureReason:
    if isinstance(exc, PermissionError):
        return "permission_denied"
    if isinstance(exc, FileNotFoundError):
        return "not_found"
    return "unknown"


def _is_under_root(path: Path, root: Path) -> bool:
    try:
        return path.is_relative_to(root)
    except ValueError:
        return False


def _is_under_any_root(path: Path, roots: Iterable[Path]) -> bool:
    return any(_is_under_root(path, root) for root in roots)


def cleanup_paths_allowlist(
    paths: Iterable[Path],
    *,
    downloads_root: Path,
    transcripts_root: Path,
) -> CleanupOutcome:
    downloads_root_resolved = downloads_root.resolve()
    transcripts_root_resolved = transcripts_root.resolve()

    deleted_count = 0
    failed_paths: list[CleanupFailedPath] = []

    for raw_path in paths:
        resolved = raw_path.resolve()
        if not _is_under_any_root(resolved, [downloads_root_resolved, transcripts_root_resolved]):
            failed_paths.append(CleanupFailedPath(path=str(resolved), reason="path_outside_root"))
            continue

        suffix = resolved.suffix.lower()
        if suffix in {".md", ".docx"}:
            continue
        if suffix not in ALLOW_SUFFIXES:
            continue

        try:
            resolved.unlink()
            deleted_count += 1
        except OSError as exc:
            failed_paths.append(CleanupFailedPath(path=str(resolved), reason=_classify_unlink_error(exc)))

    return CleanupOutcome(
        deleted_count=deleted_count,
        failed_count=len(failed_paths),
        failed_paths=failed_paths,
    )


def _count_files_under_dir(root: Path) -> int:
    if not root.exists():
        return 0
    if root.is_file():
        return 1
    return sum(1 for p in root.rglob("*") if p.is_file())


def cleanup_task_cache_dir(cache_dir: Path) -> CleanupOutcome:
    resolved = cache_dir.resolve()
    deleted_count = _count_files_under_dir(resolved)
    failed_paths: list[CleanupFailedPath] = []

    try:
        if resolved.is_file():
            resolved.unlink()
        else:
            shutil.rmtree(resolved, ignore_errors=False)
    except FileNotFoundError:
        return CleanupOutcome(deleted_count=0, failed_count=0, failed_paths=[])
    except OSError as exc:
        failed_paths.append(CleanupFailedPath(path=str(resolved), reason=_classify_unlink_error(exc)))
        deleted_count = 0

    return CleanupOutcome(
        deleted_count=deleted_count,
        failed_count=len(failed_paths),
        failed_paths=failed_paths,
    )

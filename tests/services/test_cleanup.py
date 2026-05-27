from __future__ import annotations

from pathlib import Path

from media_tools.services.cleanup import (
    cleanup_paths_allowlist,
    cleanup_task_cache_dir,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")


def test_cleanup_deletes_only_allowlisted_suffixes(tmp_path: Path) -> None:
    downloads_root = tmp_path / "downloads"
    transcripts_root = tmp_path / "transcripts"

    video = downloads_root / "c1" / "a.mp4"
    wav = downloads_root / "c1" / "a.wav"
    md = transcripts_root / "c1" / "a.md"
    docx = transcripts_root / "c1" / "a.docx"
    png = downloads_root / "c1" / "a.png"

    for p in [video, wav, md, docx, png]:
        _touch(p)

    outcome = cleanup_paths_allowlist(
        [video, wav, md, docx, png],
        downloads_root=downloads_root,
        transcripts_root=transcripts_root,
    )

    assert outcome.deleted_count == 2
    assert not video.exists()
    assert not wav.exists()
    assert md.exists()
    assert docx.exists()
    assert png.exists()


def test_cleanup_blocks_path_traversal(tmp_path: Path) -> None:
    downloads_root = tmp_path / "downloads"
    transcripts_root = tmp_path / "transcripts"
    outside = tmp_path / "outside.mp4"
    _touch(outside)

    outcome = cleanup_paths_allowlist(
        [outside],
        downloads_root=downloads_root,
        transcripts_root=transcripts_root,
    )

    assert outcome.deleted_count == 0
    assert outcome.failed_count == 1
    assert outside.exists()


def test_cleanup_cache_dir_removed(tmp_path: Path) -> None:
    cache_dir = tmp_path / "transcripts" / "c1" / ".cache" / "t1"
    _touch(cache_dir / "x.tmp")
    outcome = cleanup_task_cache_dir(cache_dir)
    assert outcome.deleted_count == 1
    assert not cache_dir.exists()

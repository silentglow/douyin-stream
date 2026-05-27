from __future__ import annotations

from pathlib import Path

from media_tools.platform.douyin import (
    MIN_VIDEO_BYTES,
    _scan_local_aweme_files,
    _select_videos_to_download,
)


def _write_valid_mp4(path: Path) -> None:
    header = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00"
    padding = b"\x00" * max(MIN_VIDEO_BYTES - len(header), 0)
    path.write_bytes(header + padding)


def test_full_download_treats_corrupt_as_missing_and_overwrites(tmp_path: Path) -> None:
    user_path = tmp_path / "user"
    user_path.mkdir(parents=True, exist_ok=True)

    ok_id = "123456789012345"
    corrupt_id = "999999999999999"
    new_id = "888888888888888"

    _write_valid_mp4(user_path / f"{ok_id}.mp4")
    (user_path / f"{corrupt_id}.mp4").write_bytes(b"bad")

    existing, corrupt, corrupt_files = _scan_local_aweme_files(user_path)
    assert ok_id in existing
    assert corrupt_id in existing
    assert corrupt_id in corrupt
    assert corrupt_files[corrupt_id][0].exists()

    existing -= corrupt

    video_list = [
        {"aweme_id": ok_id, "desc": "ok"},
        {"aweme_id": corrupt_id, "desc": "corrupt"},
        {"aweme_id": new_id, "desc": "new"},
    ]
    new_videos, skipped = _select_videos_to_download(video_list, existing, corrupt_files)

    assert skipped == 1
    assert [v["aweme_id"] for v in new_videos] == [corrupt_id, new_id]
    assert not (user_path / f"{corrupt_id}.mp4").exists()

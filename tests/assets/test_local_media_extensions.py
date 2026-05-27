from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from media_tools.api.app import app
from media_tools.transcribe.media_extensions import MEDIA_EXTENSIONS
from media_tools.transcribe.worker import filter_supported_media_paths


client = TestClient(app)


def test_media_extensions_contains_mp3() -> None:
    assert ".mp3" in MEDIA_EXTENSIONS


def test_scan_directory_returns_mp3_files() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as temp_dir:
        mp3_path = Path(temp_dir) / "a.mp3"
        mp3_path.write_bytes(b"fake mp3 content")

        response = client.post("/api/v1/tasks/transcribe/scan", json={"directory": temp_dir})
        assert response.status_code == 200
        payload = response.json()
        paths = {f["path"] for f in payload["files"]}
        assert str(mp3_path) in paths


def test_filter_supported_media_paths_keeps_mp3() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as temp_dir:
        mp3_path = Path(temp_dir) / "b.mp3"
        mp3_path.write_bytes(b"fake" * 3000)  # 12KB, above MIN_VIDEO_BYTES
        paths = filter_supported_media_paths([str(mp3_path)])
        assert paths == [mp3_path]

from __future__ import annotations

from pathlib import Path

from media_tools.platform.bilibili import download_up_by_url


def test_download_up_returns_requested_filepaths(tmp_path: Path, monkeypatch) -> None:
    expected_file = tmp_path / "out.mp4"
    expected_file.write_bytes(b"ok")

    captured_opts: dict = {}

    class FakeYDL:
        def __init__(self, opts: dict):
            captured_opts.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url: str, download: bool):
            if not download:
                return {"uploader": "test", "uploader_id": "123"}
            return {"requested_downloads": [{"filepath": str(expected_file)}]}

    monkeypatch.setattr("media_tools.platform.bilibili.YoutubeDL", FakeYDL)
    monkeypatch.setattr("media_tools.platform.bilibili.get_bilibili_cookie_string", lambda: "")
    monkeypatch.setattr("media_tools.platform.bilibili.get_download_path", lambda: tmp_path)

    result = download_up_by_url("https://space.bilibili.com/123", max_counts=None, skip_existing=True)
    assert result["success"] is True
    assert result["new_files"] == [str(expected_file)]
    assert "format" in captured_opts


def test_download_up_adds_cookiefile_when_available(tmp_path: Path, monkeypatch) -> None:
    captured_opts: dict = {}

    class FakeYDL:
        def __init__(self, opts: dict):
            captured_opts.update(opts)
            assert "cookiefile" in opts
            assert Path(opts["cookiefile"]).exists()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url: str, download: bool):
            return {"requested_downloads": []}

    monkeypatch.setattr("media_tools.platform.bilibili.YoutubeDL", FakeYDL)
    monkeypatch.setattr("media_tools.platform.bilibili.get_bilibili_cookie_string", lambda: "SESSDATA=xxx")
    monkeypatch.setattr("media_tools.platform.bilibili.get_download_path", lambda: tmp_path)

    download_up_by_url("https://space.bilibili.com/123", max_counts=None, skip_existing=True)


def test_download_up_direct_proxy_forces_no_proxy(tmp_path: Path, monkeypatch) -> None:
    captured_opts: dict = {}

    class FakeYDL:
        def __init__(self, opts: dict):
            captured_opts.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url: str, download: bool):
            return {"requested_downloads": []}

    class FakeConfig:
        bilibili_proxy = "direct"

    monkeypatch.setattr("media_tools.platform.bilibili.YoutubeDL", FakeYDL)
    monkeypatch.setattr("media_tools.platform.bilibili.get_bilibili_cookie_string", lambda: "")
    monkeypatch.setattr("media_tools.platform.bilibili.get_download_path", lambda: tmp_path)
    monkeypatch.setattr("media_tools.core.config.get_app_config", lambda: FakeConfig())

    download_up_by_url("https://space.bilibili.com/123", max_counts=None, skip_existing=True)

    assert captured_opts["proxy"] == ""


def test_download_up_empty_proxy_inherits_environment(tmp_path: Path, monkeypatch) -> None:
    captured_opts: dict = {}

    class FakeYDL:
        def __init__(self, opts: dict):
            captured_opts.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url: str, download: bool):
            return {"requested_downloads": []}

    class FakeConfig:
        bilibili_proxy = ""

    monkeypatch.setattr("media_tools.platform.bilibili.YoutubeDL", FakeYDL)
    monkeypatch.setattr("media_tools.platform.bilibili.get_bilibili_cookie_string", lambda: "")
    monkeypatch.setattr("media_tools.platform.bilibili.get_download_path", lambda: tmp_path)
    monkeypatch.setattr("media_tools.core.config.get_app_config", lambda: FakeConfig())

    download_up_by_url("https://space.bilibili.com/123", max_counts=None, skip_existing=True)

    assert "proxy" not in captured_opts

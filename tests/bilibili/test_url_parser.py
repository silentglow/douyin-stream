from media_tools.bilibili.url_parser import BilibiliUrlKind, normalize_bilibili_url


def test_normalize_space_url() -> None:
    parsed = normalize_bilibili_url("https://space.bilibili.com/123456")
    assert parsed.kind is BilibiliUrlKind.SPACE
    assert parsed.mid == "123456"


def test_normalize_video_url() -> None:
    parsed = normalize_bilibili_url("https://www.bilibili.com/video/BV1xx411c7mD")
    assert parsed.kind is BilibiliUrlKind.VIDEO
    assert parsed.bvid == "BV1xx411c7mD"


def test_normalize_short_url_is_detected() -> None:
    parsed = normalize_bilibili_url("https://b23.tv/abcd")
    assert parsed.kind is BilibiliUrlKind.SHORT
    assert parsed.original_url == "https://b23.tv/abcd"

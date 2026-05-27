from __future__ import annotations

from media_tools.bilibili.naming import build_bilibili_asset_id, build_bilibili_creator_uid, sanitize_filename


def test_creator_uid_prefix() -> None:
    assert build_bilibili_creator_uid("123") == "bilibili:123"


def test_asset_id_single() -> None:
    assert build_bilibili_asset_id("BV1xx411c7mD", None) == "bilibili:BV1xx411c7mD"


def test_asset_id_multip() -> None:
    assert build_bilibili_asset_id("BV1xx411c7mD", 2) == "bilibili:BV1xx411c7mD:p2"


def test_sanitize_filename() -> None:
    assert sanitize_filename('a/b:c*?"<>|') == "abc"

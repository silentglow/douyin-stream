"""_short_title 日志截断辅助测试。"""

from __future__ import annotations

from media_tools.platform.douyin import _short_title


def test_short_title_keeps_short_text_without_ellipsis() -> None:
    assert _short_title("算鸟") == "算鸟"


def test_short_title_truncates_long_text_with_ellipsis() -> None:
    result = _short_title("长" * 60)
    assert len(result) == 50
    assert result.endswith("…")


def test_short_title_collapses_whitespace_and_newlines() -> None:
    assert _short_title("标题\n带  换行 和 空格") == "标题 带 换行 和 空格"


def test_short_title_handles_empty() -> None:
    assert _short_title("") == ""

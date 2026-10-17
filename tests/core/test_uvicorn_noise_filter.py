"""uvicorn 断连噪音过滤器测试。"""

from __future__ import annotations

import logging

from media_tools.logger import _ConnectionNoiseFilter


def _record(message: str, level: int = logging.INFO) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.error",
        level=level,
        pathname="",
        lineno=0,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_info_connection_closed_is_filtered() -> None:
    f = _ConnectionNoiseFilter()
    assert f.filter(_record("connection closed")) is False
    assert f.filter(_record("connection open")) is False


def test_warning_and_above_pass_through() -> None:
    f = _ConnectionNoiseFilter()
    assert f.filter(_record("connection closed", logging.WARNING)) is True
    assert f.filter(_record("connection closed", logging.ERROR)) is True


def test_normal_info_passes_through() -> None:
    f = _ConnectionNoiseFilter()
    assert f.filter(_record("Started server process")) is True

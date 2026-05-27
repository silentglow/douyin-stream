"""Per-directory fixture: 给 tests/core/ 下任何测试一个独立、已建表的临时 DB。

历史教训：之前这些测试在 tests/ 根目录跑得过，靠的是本地 data/media_tools.db
已存在；在 CI 干净 checkout 下 SQLite auto-create 一个空库，没有 SystemSettings
表，test_settings_change_via_api_invalidates_cache_immediately 直接挂。
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from media_tools.store.db import get_db_path, init_db, reset_db_cache, set_db_path


@pytest.fixture(autouse=True)
def _isolated_test_db() -> Iterator[None]:
    original = get_db_path()
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test_core.db")
        set_db_path(db_path)
        reset_db_cache()
        init_db(db_path)
        try:
            yield
        finally:
            set_db_path(original)
            reset_db_cache()

from __future__ import annotations

"""数据库路径和查询工具"""
from typing import Optional, Union

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_safe_path(base_dir: Path, relative_path: Optional[str]) -> Optional[Path]:
    """Resolve a path and ensure it stays within base_dir."""
    if not relative_path:
        return None
    try:
        base = base_dir.resolve()
        target = (base / relative_path).resolve()
        import os
        if not str(target).startswith(str(base) + os.sep) and str(target) != str(base):
            logger.warning(f"Path traversal blocked: {relative_path} -> {target}")
            return None
        return target
    except (OSError, ValueError):
        return None


def resolve_query_value(val, default):
    """Convert FastAPI Query object to actual value."""
    if hasattr(val, 'default'):
        return val.default if val.default is not None else default
    return val if val is not None else default


def local_asset_id(file_path: Union[str, Path]) -> str:
    """Generate a stable asset ID for local files."""
    import hashlib
    path = Path(file_path).resolve()
    return f"local:{hashlib.sha1(str(path).encode()).hexdigest()[:24]}"

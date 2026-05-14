"""Compatibility shim: media_tools.db.core -> media_tools.store.db

All functions re-exported from store.db. New code should import from store.db directly.
This file will be removed in a future cleanup phase.
"""

from media_tools.store.db import (  # noqa: F401
    get_db,
    get_db_connection,
    get_db_path,
    set_db_path,
    close_db_connection,
    close_all_cached_connections,
    DBConnection,
    get_table_columns,
    validate_identifier,
    _check_table_name,
    init_db,
    resolve_safe_path,
    resolve_query_value,
    local_asset_id,
    _db_path,
)
from media_tools.store.fts import (  # noqa: F401
    ensure_fts_populated,
    update_fts_for_asset,
    rebuild_fts_index,
)


def reset_db_cache() -> None:
    """Clear current thread's DB connection cache."""
    close_all_cached_connections()

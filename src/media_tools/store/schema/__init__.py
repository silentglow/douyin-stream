from .creators import create_table as create_creators_table, create_indexes as create_creators_indexes
from .assets import create_table as create_assets_table, create_indexes as create_assets_indexes
from .tasks import create_table as create_tasks_table, create_indexes as create_tasks_indexes
from .auth import create_table as create_auth_table, create_indexes as create_auth_indexes
from .accounts import create_table as create_accounts_table, create_indexes as create_accounts_indexes
from .settings import create_table as create_settings_table, create_indexes as create_settings_indexes
from .scheduled import create_table as create_scheduled_table, create_indexes as create_scheduled_indexes
from .video_meta import create_table as create_video_meta_table, create_indexes as create_video_meta_indexes
from .user_info import create_table as create_user_info_table, create_indexes as create_user_info_indexes
from .transcribe import create_table as create_transcribe_table, create_indexes as create_transcribe_indexes


def init_schema(conn):
    create_creators_table(conn)
    create_creators_indexes(conn)
    create_assets_table(conn)
    create_assets_indexes(conn)
    create_tasks_table(conn)
    create_tasks_indexes(conn)
    create_auth_table(conn)
    create_auth_indexes(conn)
    create_accounts_table(conn)
    create_accounts_indexes(conn)
    create_settings_table(conn)
    create_settings_indexes(conn)
    create_scheduled_table(conn)
    create_scheduled_indexes(conn)
    create_video_meta_table(conn)
    create_video_meta_indexes(conn)
    create_user_info_table(conn)
    create_user_info_indexes(conn)
    create_transcribe_table(conn)
    create_transcribe_indexes(conn)

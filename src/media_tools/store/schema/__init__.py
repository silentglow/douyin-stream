from .accounts import create_indexes as create_accounts_indexes
from .accounts import create_table as create_accounts_table
from .assets import create_indexes as create_assets_indexes
from .assets import create_table as create_assets_table
from .auth import create_indexes as create_auth_indexes
from .auth import create_table as create_auth_table
from .creators import create_indexes as create_creators_indexes
from .creators import create_table as create_creators_table
from .scheduled import create_indexes as create_scheduled_indexes
from .scheduled import create_table as create_scheduled_table
from .settings import create_indexes as create_settings_indexes
from .settings import create_table as create_settings_table
from .tasks import create_indexes as create_tasks_indexes
from .tasks import create_table as create_tasks_table
from .transcribe import create_indexes as create_transcribe_indexes
from .transcribe import create_table as create_transcribe_table
from .user_info import create_indexes as create_user_info_indexes
from .user_info import create_table as create_user_info_table
from .video_meta import create_indexes as create_video_meta_indexes
from .video_meta import create_table as create_video_meta_table


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

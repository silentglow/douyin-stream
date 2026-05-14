from .creators import create_table as create_creators_table
from .assets import create_table as create_assets_table
from .tasks import create_table as create_tasks_table
from .auth import create_table as create_auth_table
from .accounts import create_table as create_accounts_table
from .settings import create_table as create_settings_table
from .scheduled import create_table as create_scheduled_table
from .video_meta import create_table as create_video_meta_table
from .user_info import create_table as create_user_info_table
from .transcribe import create_table as create_transcribe_table


def init_schema(conn):
    create_creators_table(conn)
    create_assets_table(conn)
    create_tasks_table(conn)
    create_auth_table(conn)
    create_accounts_table(conn)
    create_settings_table(conn)
    create_scheduled_table(conn)
    create_video_meta_table(conn)
    create_user_info_table(conn)
    create_transcribe_table(conn)

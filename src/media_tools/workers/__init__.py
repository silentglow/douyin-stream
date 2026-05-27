"""后台工作者模块 - 所有异步后台任务"""

# 主动导入所有 worker 模块，触发 @register_worker 装饰器注册到全局注册表
from media_tools.download.worker import DownloadWorker  # noqa: F401
from media_tools.scheduler.base import BaseWorker, register_worker  # noqa: F401

from .aweme_recover_worker import AwemeRecoverWorker  # noqa: F401
from .creator_transcribe_worker import CreatorTranscribeWorker  # noqa: F401
from .full_sync_worker import FullSyncWorker  # noqa: F401
from .local_transcribe_worker import LocalTranscribeWorker  # noqa: F401
from .pipeline_worker import PipelineWorker  # noqa: F401
from .transcribe import transcribe_files  # noqa: F401

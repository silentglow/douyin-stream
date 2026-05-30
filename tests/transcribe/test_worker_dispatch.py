"""_dispatch_progress 线程投递单测。

验证转写进度推送在「没有运行事件循环的上传工作线程」里不会抛
`no running event loop`，而是通过 call_soon_threadsafe 投递回主循环；
在主循环线程内则直接创建任务。
"""

import asyncio
from unittest.mock import MagicMock, patch

from media_tools.transcribe import worker


def test_dispatch_progress_no_loop_uses_call_soon_threadsafe():
    """无运行事件循环（模拟上传工作线程）时，应投递回主循环而非直接 create_task。"""

    async def _noop():
        pass

    coro = _noop()
    fake_loop = MagicMock()
    # pytest 主线程默认没有 running event loop，等价于 asyncio.to_thread 的上传工作线程
    with patch.object(worker, "create_managed_task") as m_create:
        worker._dispatch_progress(coro, fake_loop)
        m_create.assert_not_called()
        fake_loop.call_soon_threadsafe.assert_called_once_with(m_create, coro)
    coro.close()


def test_dispatch_progress_in_loop_creates_task_directly():
    """有运行事件循环时，直接 create_managed_task。"""

    async def _main():
        loop = asyncio.get_running_loop()

        async def _noop():
            pass

        coro = _noop()
        with patch.object(worker, "create_managed_task") as m_create:
            worker._dispatch_progress(coro, loop)
            m_create.assert_called_once_with(coro)
        coro.close()

    asyncio.run(_main())

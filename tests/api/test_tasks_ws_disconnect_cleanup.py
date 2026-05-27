from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_ws_disconnect_cleanup_on_runtime_error() -> None:
    import media_tools.api.websocket_manager as ws

    class FakeWebSocket:
        async def accept(self) -> None:
            return None

        async def receive_text(self) -> str:
            raise RuntimeError("boom")

        async def send_json(self, _message) -> None:
            raise OSError("closed")

    manager = ws.ConnectionManager()
    fake_ws = FakeWebSocket()

    async def _fast_sleep(_seconds: float) -> None:
        return None

    with (
        patch.object(ws, "manager", manager),
        patch.object(ws.asyncio, "sleep", new=AsyncMock(side_effect=_fast_sleep)),
    ):
        await ws.websocket_endpoint(fake_ws)  # should swallow errors and exit

    stats = manager.get_stats()
    assert stats["connected"] == 1
    assert stats["disconnected"] == 1
    assert stats["active_connections"] == 0

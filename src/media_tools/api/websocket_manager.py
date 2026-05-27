import asyncio
import contextlib
import logging
import time

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from media_tools.core import background

logger = logging.getLogger(__name__)

# 半开连接检测：超过此时间无活动的连接将被清理（秒）
_STALE_CONNECTION_TIMEOUT = 120


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._connect_times: dict[int, float] = {}
        self._last_activity: dict[int, float] = {}
        self._stats = {"connected": 0, "disconnected": 0, "broadcast_success": 0, "broadcast_failed": 0}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        ws_id = id(websocket)
        self._connect_times[ws_id] = time.monotonic()
        self._last_activity[ws_id] = time.monotonic()
        self._stats["connected"] += 1

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            ws_id = id(websocket)
            self._connect_times.pop(ws_id, None)
            self._last_activity.pop(ws_id, None)
            self._stats["disconnected"] += 1

    def _touch(self, websocket: WebSocket) -> None:
        """更新连接的最后活动时间"""
        self._last_activity[id(websocket)] = time.monotonic()

    def cleanup_stale_connections(self) -> int:
        """清理超过超时时间无活动的连接，返回清理数量"""
        now = time.monotonic()
        stale = []
        for conn in self.active_connections:
            ws_id = id(conn)
            last = self._last_activity.get(ws_id, 0)
            if now - last > _STALE_CONNECTION_TIMEOUT:
                stale.append(conn)
        for conn in stale:
            logger.info(f"清理超时 WebSocket 连接: {id(conn)}")
            self.disconnect(conn)
        return len(stale)

    def get_stats(self) -> dict:
        return {"active_connections": len(self.active_connections), **self._stats}

    async def broadcast(self, message: dict):
        # 先清理标记为 DISCONNECTED 的连接
        snapshot = list(self.active_connections)
        dead_connections: list[WebSocket] = []
        for conn in snapshot:
            try:
                if conn.client_state == WebSocketState.DISCONNECTED:
                    dead_connections.append(conn)
            except (AttributeError, RuntimeError):
                dead_connections.append(conn)
        for conn in dead_connections:
            self.disconnect(conn)

        live = [c for c in snapshot if c not in dead_connections]
        if not live:
            return

        # 并发推送：慢连接不会拖累快连接
        results = await asyncio.gather(
            *(c.send_json(message) for c in live),
            return_exceptions=True,
        )
        for conn, result in zip(live, results, strict=False):
            if isinstance(result, BaseException):
                if isinstance(result, (ConnectionResetError, OSError, BrokenPipeError, RuntimeError)):
                    logger.info(f"WebSocket 连接已关闭，移除连接: {id(conn)}")
                    self.disconnect(conn)
                    self._stats["broadcast_failed"] += 1
                else:
                    logger.exception(
                        f"WebSocket 广播未预期异常: {id(conn)}",
                        exc_info=result,
                    )
                    self.disconnect(conn)
                    self._stats["broadcast_failed"] += 1
            else:
                self._touch(conn)
                self._stats["broadcast_success"] += 1


manager = ConnectionManager()


async def stale_connection_sweeper(interval_seconds: int = 60) -> None:
    """后台任务：周期性清理无活动 WebSocket 连接。

    `cleanup_stale_connections` 原本只在 broadcast 时调用，空闲期不会触发；
    本任务由 lifespan 拉起，确保任何时段半开连接都会被回收。
    """
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            removed = manager.cleanup_stale_connections()
            if removed:
                logger.info(f"stale_connection_sweeper 清理 {removed} 个连接")
        except asyncio.CancelledError:
            logger.debug("stale_connection_sweeper cancelled")
            return
        except (RuntimeError, OSError) as e:
            logger.warning(f"stale_connection_sweeper iteration failed: {e}")


async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    async def _heartbeat():
        try:
            while True:
                await asyncio.sleep(20)
                try:
                    await websocket.send_json({"type": "ping"})
                except (ConnectionResetError, OSError, BrokenPipeError) as e:
                    logger.warning(f"WebSocket ping failed: {e}")
                    break
        except asyncio.CancelledError:
            logger.debug("Heartbeat task cancelled")
        except (RuntimeError, OSError):
            logger.exception("Heartbeat task unexpected error")

    heartbeat_task = background.create(_heartbeat(), name=f"ws_heartbeat:{id(websocket)}")

    try:
        while True:
            data = await websocket.receive_text()
            # 收到任何客户端消息（含 pong）都视作连接活跃
            manager._touch(websocket)
            if data:
                logger.debug(f"WebSocket received: {data[:50]}...")
    except WebSocketDisconnect:
        pass
    except (RuntimeError, OSError) as e:
        logger.exception(f"WebSocket unexpected error: {e}")
    finally:
        manager.disconnect(websocket)
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task

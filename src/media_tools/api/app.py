import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager, suppress

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from media_tools.api.routers import assets, creators, douyin, metrics, scheduler, search, settings, tasks
from media_tools.api.websocket_manager import stale_connection_sweeper
from media_tools.core import background
from media_tools.core.exceptions import AppError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure DB schema is up to date (adds new columns to existing tables)
    from media_tools.common.paths import get_db_path
    from media_tools.store.db import init_db

    init_db(get_db_path())

    from media_tools.store.db import ensure_fts_populated

    ensure_fts_populated()

    scheduler.startup_scheduler()

    # 记录主 loop 引用，供 APScheduler 等线程通过 run_coroutine_threadsafe 派发协程回主 loop
    background.set_main_loop(asyncio.get_running_loop())

    # Kick off the transcript preview backfill in the background
    from media_tools.transcribe.preview_backfill import start_backfill_once

    start_backfill_once()

    # 启动时清理孤儿任务：服务重启后内存中的后台任务全部丢失，
    # 数据库里残留的 RUNNING/PENDING 任务实际上已经无人执行。
    try:
        import sqlite3

        from media_tools.scheduler.ops import cleanup_stale_tasks
        from media_tools.store.db import get_db_connection

        with get_db_connection() as conn:
            cleanup_stale_tasks(conn, is_startup=True)
            conn.commit()
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"startup cleanup failed: {e}")

    # 启动时归档 30 天前的日志文件（只 mv 不删，保留事故回溯能力）
    try:
        from pathlib import Path

        from media_tools.services.log_rotation import archive_old_logs

        outcome = archive_old_logs(Path("logs"), days=30)
        if outcome.archived_count:
            logger.info(f"startup: archived {outcome.archived_count} old log file(s) to {outcome.archive_dir}")
    except OSError as e:
        logger.warning(f"startup log archive failed: {e}")

    # 后台清扫 WebSocket 半开连接（每 60s）
    sweeper_task = asyncio.create_task(stale_connection_sweeper(60))

    yield
    # Shutdown
    sweeper_task.cancel()
    with suppress(asyncio.CancelledError):
        await sweeper_task
    # 取消 registry 中所有 in-flight 后台任务（worker / heartbeat / auto_retry / ...）
    cancelled = await background.cancel_all(timeout=5.0)
    if cancelled:
        logger.info(f"shutdown: cancelled {cancelled} background task(s)")
    # 关闭共享 HTTP 客户端，避免连接泄漏
    try:
        from media_tools.bilibili.nickname import close_bilibili_client

        await close_bilibili_client()
    except Exception as e:
        logger.warning(f"shutdown: close bilibili client failed: {e}")

    # 关闭主线程缓存的 DB 连接
    from media_tools.store.db import close_all_cached_connections

    closed = close_all_cached_connections()
    if closed:
        logger.info(f"shutdown: closed {closed} cached DB connection(s)")
    scheduler.shutdown_scheduler()


app = FastAPI(title="Media Tools API", version="1.0.0", lifespan=lifespan, redirect_slashes=False)


class UnhandledApiErrorsMiddleware(BaseHTTPMiddleware):
    """捕获所有 sync 路由中未处理的 sqlite3.Error / OSError / RuntimeError，
    返回 500 并记录完整 traceback。路由层不再需要重复写 try/except 模板。"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        try:
            return await call_next(request)
        except (sqlite3.Error, OSError, RuntimeError):
            # 不重复处理已声明 HTTPException 的路径（中间件在外层，
            # HTTPException 会被 FastAPI 捕获，不会走到这里；能到这里
            # 说明是真正的未处理异常）
            logger.exception(f"未处理 API 异常: {request.url.path}")
            return JSONResponse(
                status_code=500,
                content={
                    "code": "INTERNAL_ERROR",
                    "message": "服务器内部错误",
                    "details": {},
                },
            )


app.add_middleware(UnhandledApiErrorsMiddleware)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """为每个请求生成唯一 request_id 并注入日志上下文。"""
    import uuid

    from media_tools.core.logging_context import set_logging_context

    request_id = str(uuid.uuid4())[:8]
    set_logging_context(request_id=request_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        from media_tools.core.logging_context import clear_logging_context

        clear_logging_context()


_api_key_cache: str | None = None
_api_key_cache_time: float = 0.0


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    """Optional API key authentication middleware."""
    global _api_key_cache, _api_key_cache_time

    import time

    now = time.monotonic()
    if now - _api_key_cache_time > 10.0:
        from media_tools.core.config import get_runtime_setting

        _api_key_cache = get_runtime_setting("api_key", "")
        _api_key_cache_time = now
    api_key = _api_key_cache

    # Skip auth if no API key is configured
    if not api_key:
        return await call_next(request)

    # Skip auth for health check, WebSocket, and docs
    skip_paths = ("/api/health", "/api/v1/tasks/ws", "/docs", "/openapi.json", "/redoc")
    if request.url.path in skip_paths or request.url.path.startswith("/docs"):
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header[7:]  # Remove "Bearer " prefix
    # 用 compare_digest 做常量时间比较，避免本地/同机时序侧信道泄漏 API key
    import hmac

    if not hmac.compare_digest(token, api_key):
        raise HTTPException(status_code=403, detail="Invalid API key")

    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    """处理应用自定义异常 - 返回结构化错误"""
    logger.warning(f"AppError: {exc.code} - {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """处理 HTTP 异常 - 统一格式"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": f"HTTP_{exc.status_code}",
            "message": exc.detail,
            "details": {},
        },
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    """处理未捕获异常 - 不暴露内部信息"""
    logger.exception(f"Unhandled exception at {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "服务器内部错误",
            "details": {},
        },
    )


app.include_router(creators.router)
app.include_router(assets.router)
app.include_router(assets.transcripts_router)
app.include_router(tasks.router)
app.include_router(settings.router)
app.include_router(douyin.router)
app.include_router(scheduler.router)
app.include_router(metrics.router)
app.include_router(search.router)

import shutil

from media_tools.scheduler.repository import TaskRepository
from media_tools.store.db import get_db_connection


@app.get("/api/health")
def health_check():
    result = {"status": "ok"}

    # DB 连接状态
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT 1")
        result["db"] = "ok"
    except (OSError, RuntimeError, sqlite3.Error) as e:
        result["db"] = f"error: {e}"
        result["status"] = "degraded"

    # 磁盘空间
    try:
        stat = shutil.disk_usage(".")
        result["disk"] = {
            "total_gb": round(stat.total / (1024**3), 2),
            "free_gb": round(stat.free / (1024**3), 2),
            "used_percent": round((stat.used / stat.total) * 100, 1),
        }
    except OSError as e:
        result["disk"] = f"error: {e}"

    # 活跃任务数
    try:
        active = TaskRepository.find_active()
        result["active_tasks"] = len(active)
    except sqlite3.Error as e:
        result["active_tasks"] = f"error: {e}"

    return result


# Serve frontend static files in Docker/Production if built
import os
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

frontend_dist = os.getenv("FRONTEND_DIST_DIR", "/app/frontend/dist")
if os.path.exists(frontend_dist):
    # Mount /assets specifically so StaticFiles can handle content-types and caching
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{fallback_path:path}")
    def spa_fallback(fallback_path: str):
        # If the path matches an actual file in dist (e.g. logo.png, favicon.ico), serve it
        target_file = os.path.join(frontend_dist, fallback_path)
        if os.path.exists(target_file) and os.path.isfile(target_file):
            return FileResponse(target_file)

        # Do not fallback for API requests
        if (
            fallback_path.startswith("api/")
            or fallback_path.startswith("docs")
            or fallback_path.startswith("redoc")
            or fallback_path == "openapi.json"
        ):
            raise HTTPException(status_code=404, detail="Not Found")

        # Otherwise fallback to index.html for SPA routing
        index_file = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)

        raise HTTPException(status_code=404, detail="Not Found")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

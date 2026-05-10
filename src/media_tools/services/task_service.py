from __future__ import annotations
"""TaskService - 任务管理服务层（迁移过渡版本）

本文件作为迁移过渡层，逐步将业务逻辑委托给新的领域驱动架构。
最终目标是完全移除本文件，直接使用新架构。
"""

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from media_tools.api.schemas import (
    PipelineRequest,
    BatchPipelineRequest,
    DownloadBatchRequest,
    CreatorDownloadRequest,
    FullSyncRequest,
    LocalTranscribeRequest,
    CreatorTranscribeRequest,
    ScanDirectoryRequest,
    RecoverAwemeTranscribeRequest,
    CreatorTranscribeCleanupRetryRequest,
    RetryFailedAssetsRequest,
)
from media_tools.workers.task_dispatcher import _start_task_worker, _create_task, _retry_task_worker
from media_tools.douyin.core.cancel_registry import set_cancel_event, clear_cancel_event, clear_download_progress
from media_tools.common.paths import get_download_path, get_project_root
from media_tools.db.core import get_db_connection
from media_tools.repositories.task_repository import TaskRepository
from media_tools.core.config import get_runtime_setting_bool

# Task operations
from media_tools.services.task_ops import (
    cleanup_stale_tasks,
    _mark_task_cancelled,
)
from media_tools.services.task_state import (
    _active_tasks,
    _register_background_task,
)
from media_tools.services.local_asset_service import _register_local_assets
from media_tools.services.pipeline_progress import build_pipeline_progress
from media_tools.services.transcript_reconciler import reconcile_transcripts
from media_tools.services.file_browser import select_folder, scan_directory
from media_tools.services.cleanup import cleanup_paths_allowlist

# Workers
from media_tools.workers.pipeline_worker import (
    _background_pipeline_worker,
    _background_batch_worker,
    _background_download_worker,
)
from media_tools.workers.full_sync_worker import _background_full_sync_worker
from media_tools.workers.local_transcribe_worker import _background_local_transcribe_worker

# 新架构导入（迁移使用）
from media_tools.migration import get_migration_service, get_task_service as get_new_task_service

logger = logging.getLogger(__name__)


class TaskService:
    """任务管理服务 - 封装任务相关业务逻辑"""
    
    @staticmethod
    def _get_global_setting_bool(key: str, default: bool = False) -> bool:
        """从数据库 SystemSettings 表读取布尔配置。"""
        return get_runtime_setting_bool(key, default)
    
    @staticmethod
    async def create_pipeline_task(req: PipelineRequest) -> Dict[str, str]:
        """创建管道任务"""
        task_id = str(uuid.uuid4())
        await _create_task(task_id, "pipeline", {
            "url": req.url, 
            "max_counts": req.max_counts, 
            "auto_delete": req.auto_delete
        })
        _register_background_task(task_id, _background_pipeline_worker(task_id, req))
        return {"task_id": task_id, "status": "started"}
    
    @staticmethod
    def get_active_tasks() -> List[Dict[str, Any]]:
        """获取活跃任务列表（使用新架构）"""
        try:
            new_service = get_new_task_service()
            tasks = new_service.list_active_tasks()
            return [TaskService._task_entity_to_dict(task) for task in tasks]
        except Exception as e:
            logger.exception(f"get_active_tasks failed: {e}")
            # 降级到旧实现
            return TaskRepository.find_active()
    
    @staticmethod
    def get_task_history(limit: int = 200) -> List[Dict[str, Any]]:
        """获取任务历史"""
        try:
            tasks = TaskRepository.list_recent(limit)
            for task in tasks:
                payload_raw = task.get("payload")
                payload: Dict[str, Any] = {}
                if isinstance(payload_raw, str) and payload_raw:
                    try:
                        parsed = json.loads(payload_raw)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        parsed = {}
                    if isinstance(parsed, dict):
                        payload = parsed
                task["payload"] = payload
                if "progress" in task and isinstance(task["progress"], str):
                    try:
                        task["progress"] = json.loads(task["progress"])
                    except (json.JSONDecodeError, TypeError, ValueError):
                        task["progress"] = {}
            return tasks
        except sqlite3.Error as e:
            logger.exception(f"get_task_history failed: {e}")
            raise
    
    @staticmethod
    def clear_task_history() -> Dict[str, str]:
        """清空任务历史（使用新架构）"""
        try:
            new_service = get_new_task_service()
            new_service.clear_task_history()
            return {"status": "ok"}
        except Exception as e:
            logger.exception(f"clear_task_history failed: {e}")
            raise
    
    @staticmethod
    async def cancel_task(task_id: str) -> Dict[str, str]:
        """取消任务（使用新架构）"""
        try:
            # 使用新架构取消任务
            new_service = get_new_task_service()
            new_service.cancel_task(task_id)
            
            # 同时清理旧架构的取消事件
            set_cancel_event(task_id)
            await _mark_task_cancelled(task_id)
            clear_download_progress(task_id)
            
            return {"status": "cancelling"}
        except Exception as e:
            logger.exception(f"cancel_task failed for {task_id}: {e}")
            raise
    
    @staticmethod
    def get_task_status(task_id: str) -> Dict[str, Any]:
        """获取任务状态（使用新架构）"""
        try:
            new_service = get_new_task_service()
            task = new_service.get_task(task_id)
            
            if not task:
                return {"task_id": task_id, "status": "not_found"}
            
            return TaskService._task_entity_to_dict(task)
        except Exception as e:
            logger.exception(f"get_task_status failed for {task_id}: {e}")
            raise
    
    @staticmethod
    async def retry_task(task_id: str) -> Dict[str, str]:
        """重试任务"""
        try:
            task = TaskRepository.find_by_id(task_id)
            if not task:
                return {"error": "任务不存在"}
            
            payload_raw = task.get("payload", "{}")
            try:
                payload = json.loads(payload_raw) if isinstance(payload_raw, str) else {}
            except json.JSONDecodeError:
                payload = {}
            
            new_task_id = str(uuid.uuid4())
            await _create_task(new_task_id, task.get("task_type", "pipeline"), payload)
            
            task_type = task.get("task_type")
            if task_type == "pipeline":
                req = PipelineRequest(**payload)
                _register_background_task(new_task_id, _background_pipeline_worker(new_task_id, req))
            else:
                _register_background_task(new_task_id, _retry_task_worker(new_task_id, payload))
            
            return {"task_id": new_task_id, "status": "started"}
        except Exception as e:
            logger.exception(f"retry_task failed for {task_id}: {e}")
            raise
    
    @staticmethod
    def cleanup_stale_tasks() -> Dict[str, int]:
        """清理过期任务"""
        try:
            with get_db_connection() as conn:
                removed = cleanup_stale_tasks(conn, is_startup=False)
                return {"removed": removed}
        except Exception as e:
            logger.exception(f"cleanup_stale_tasks failed: {e}")
            raise
    
    @staticmethod
    async def full_sync(req: FullSyncRequest) -> Dict[str, str]:
        """执行全量同步"""
        task_id = str(uuid.uuid4())
        await _create_task(task_id, "full_sync", {})
        _register_background_task(task_id, _background_full_sync_worker(task_id, req))
        return {"task_id": task_id, "status": "started"}
    
    @staticmethod
    async def batch_pipeline(req: BatchPipelineRequest) -> Dict[str, str]:
        """批量管道任务"""
        task_id = str(uuid.uuid4())
        await _create_task(task_id, "batch_pipeline", {
            "urls": req.urls,
            "max_counts": req.max_counts,
            "auto_delete": req.auto_delete,
        })
        _register_background_task(task_id, _background_batch_worker(task_id, req))
        return {"task_id": task_id, "status": "started"}
    
    @staticmethod
    async def download_batch(req: DownloadBatchRequest) -> Dict[str, str]:
        """批量下载任务"""
        task_id = str(uuid.uuid4())
        await _create_task(task_id, "download_batch", {
            "urls": req.urls,
        })
        _register_background_task(task_id, _background_download_worker(task_id, req))
        return {"task_id": task_id, "status": "started"}
    
    @staticmethod
    async def local_transcribe(req: LocalTranscribeRequest) -> Dict[str, str]:
        """本地上传转写"""
        task_id = str(uuid.uuid4())
        await _create_task(task_id, "local_transcribe", {
            "file_paths": req.file_paths,
        })
        _register_background_task(task_id, _background_local_transcribe_worker(task_id, req))
        return {"task_id": task_id, "status": "started"}
    
    @staticmethod
    def scan_directory(req: ScanDirectoryRequest) -> Dict[str, Any]:
        """扫描目录"""
        try:
            result = scan_directory(req.path)
            return result
        except Exception as e:
            logger.exception(f"scan_directory failed for {req.path}: {e}")
            raise
    
    @staticmethod
    def select_folder_dialog() -> Dict[str, Any]:
        """选择文件夹对话框"""
        try:
            folder = select_folder()
            if folder:
                return {"path": folder, "success": True}
            return {"success": False}
        except Exception as e:
            logger.exception(f"select_folder_dialog failed: {e}")
            raise
    
    @staticmethod
    def _task_entity_to_dict(task) -> Dict[str, Any]:
        """将新架构的 Task 实体转换为字典格式（兼容旧 API）"""
        return {
            "task_id": task.task_id,
            "task_type": task.task_type.value,
            "status": task.status.value,
            "payload": task.payload,
            "progress": task.progress,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        }


# 全局实例（保持向后兼容）
_task_service: Optional[TaskService] = None


def get_task_service() -> TaskService:
    """获取 TaskService 实例（保持向后兼容）"""
    global _task_service
    if _task_service is None:
        _task_service = TaskService()
    return _task_service
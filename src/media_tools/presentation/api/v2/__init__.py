from __future__ import annotations
"""表示层 - REST API 路由"""

from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, List, Optional

from media_tools.domain.entities import TaskType
from media_tools.domain.services import AssetDomainService, CreatorDomainService, TaskDomainService
from media_tools.infrastructure.db import (
    create_asset_repository,
    create_creator_repository,
    create_task_repository,
)

router = APIRouter(prefix="/api/v2", tags=["v2"], redirect_slashes=False)


# 领域服务实例
_asset_service = AssetDomainService(
    create_asset_repository(),
    create_creator_repository(),
)
_creator_service = CreatorDomainService(
    create_creator_repository(),
    create_asset_repository(),
)
_task_service = TaskDomainService(create_task_repository())


@router.get("/assets")
def list_assets(
    creator_uid: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[Dict[str, Any]]:
    """获取素材列表"""
    assets = _asset_service.list_assets(creator_uid)
    # 分页处理
    assets = assets[offset : offset + limit]
    return [_asset_to_dict(asset) for asset in assets]


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str) -> Dict[str, Any]:
    """获取单个素材"""
    asset = _asset_service.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="素材不存在")
    return _asset_to_dict(asset)


@router.post("/assets")
def create_asset(creator_uid: str, title: str) -> Dict[str, Any]:
    """创建素材"""
    asset = _asset_service.create_asset(creator_uid, title)
    return _asset_to_dict(asset)


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: str) -> Dict[str, str]:
    """删除素材"""
    _asset_service.delete_asset(asset_id)
    return {"status": "ok"}


@router.get("/creators")
def list_creators() -> List[Dict[str, Any]]:
    """获取创作者列表"""
    creators = _creator_service.list_creators()
    return [_creator_to_dict(creator) for creator in creators]


@router.get("/creators/{uid}")
def get_creator(uid: str) -> Dict[str, Any]:
    """获取单个创作者"""
    creator = _creator_service.get_creator(uid)
    if not creator:
        raise HTTPException(status_code=404, detail="创作者不存在")
    return _creator_to_dict(creator)


@router.post("/creators")
def create_creator(uid: str, nickname: str, avatar_url: Optional[str] = None) -> Dict[str, Any]:
    """创建创作者"""
    creator = _creator_service.create_creator(uid, nickname, avatar_url)
    return _creator_to_dict(creator)


@router.put("/creators/{uid}")
def update_creator(uid: str, nickname: Optional[str] = None, avatar_url: Optional[str] = None) -> Dict[str, Any]:
    """更新创作者"""
    updates = {}
    if nickname:
        updates["nickname"] = nickname
    if avatar_url:
        updates["avatar_url"] = avatar_url
    
    creator = _creator_service.update_creator(uid, **updates)
    if not creator:
        raise HTTPException(status_code=404, detail="创作者不存在")
    return _creator_to_dict(creator)


@router.delete("/creators/{uid}")
def delete_creator(uid: str) -> Dict[str, str]:
    """删除创作者"""
    _creator_service.delete_creator(uid)
    return {"status": "ok"}


@router.get("/tasks")
def list_tasks(active_only: bool = Query(False)) -> List[Dict[str, Any]]:
    """获取任务列表"""
    if active_only:
        tasks = _task_service.list_active_tasks()
    else:
        tasks = _task_service.list_tasks()
    return [_task_to_dict(task) for task in tasks]


@router.get("/tasks/{task_id}")
def get_task(task_id: str) -> Dict[str, Any]:
    """获取单个任务"""
    task = _task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _task_to_dict(task)


@router.post("/tasks/download")
def create_download_task(creator_uid: str, video_url: str, title: str) -> Dict[str, Any]:
    """创建下载任务"""
    task = _task_service.create_task(TaskType.DOWNLOAD, {
        "creator_uid": creator_uid,
        "video_url": video_url,
        "title": title,
    })
    return _task_to_dict(task)


@router.post("/tasks/transcribe")
def create_transcribe_task(asset_id: str) -> Dict[str, Any]:
    """创建转写任务"""
    task = _task_service.create_task(TaskType.TRANSCRIBE, {
        "asset_id": asset_id,
    })
    return _task_to_dict(task)


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str) -> Dict[str, str]:
    """取消任务"""
    _task_service.cancel_task(task_id)
    return {"status": "cancelling"}


@router.delete("/tasks/history")
def clear_task_history() -> Dict[str, str]:
    """清空任务历史"""
    _task_service.clear_task_history()
    return {"status": "ok"}


# 辅助函数
def _asset_to_dict(asset) -> Dict[str, Any]:
    """将 Asset 实体转换为字典"""
    return {
        "asset_id": asset.asset_id,
        "creator_uid": asset.creator_uid,
        "title": asset.title,
        "video_path": str(asset.video_path) if asset.video_path else None,
        "video_status": asset.video_status.value,
        "transcript_path": str(asset.transcript_path) if asset.transcript_path else None,
        "transcript_status": asset.transcript_status.value,
        "transcript_preview": asset.transcript_preview,
        "source_platform": asset.source_platform,
        "source_url": asset.source_url,
        "is_read": asset.is_read,
        "is_starred": asset.is_starred,
        "create_time": asset.create_time.isoformat(),
        "update_time": asset.update_time.isoformat(),
    }


def _creator_to_dict(creator) -> Dict[str, Any]:
    """将 Creator 实体转换为字典"""
    return {
        "uid": creator.uid,
        "sec_user_id": creator.sec_user_id,
        "nickname": creator.nickname,
        "avatar": creator.avatar,
        "platform": creator.platform.value,
        "sync_status": creator.sync_status.value,
        "homepage_url": creator.homepage_url,
        "bio": creator.bio,
        "downloaded_count": creator.downloaded_count,
        "transcript_count": creator.transcript_count,
        "last_fetch_time": creator.last_fetch_time.isoformat() if creator.last_fetch_time else None,
    }


def _task_to_dict(task) -> Dict[str, Any]:
    """将 Task 实体转换为字典"""
    return {
        "task_id": task.task_id,
        "task_type": task.task_type.value,
        "status": task.status.value,
        "payload": task.payload,
        "progress": task.progress,
        "error_msg": task.error_msg,
        "create_time": task.create_time.isoformat(),
        "update_time": task.update_time.isoformat(),
        "start_time": task.start_time.isoformat() if task.start_time else None,
        "end_time": task.end_time.isoformat() if task.end_time else None,
        "cancel_requested": task.cancel_requested,
        "auto_retry": task.auto_retry,
    }
"""搜索 API 路由"""
from fastapi import APIRouter, Query

from media_tools.assets.repository import AssetRepository
from media_tools.creators.repository import CreatorRepository
from media_tools.scheduler.repository import TaskRepository

router = APIRouter(prefix="/api", tags=["search"], redirect_slashes=False)


@router.get("/search")
def search(
    query: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(10, ge=1, le=50),
):
    """全局搜索接口

    支持搜索素材标题、创作者昵称、任务等内容。
    使用 SQLite FTS5 全文索引进行高效搜索。

    Args:
        query: 搜索关键词
        limit: 返回结果数量限制

    Returns:
        搜索结果列表，包含素材、创作者、任务类型
    """
    results: list[dict] = []
    per_type_limit = limit // 3

    # 搜索素材（FTS5）
    cleaned = "".join(c for c in query if c.isprintable() or c.isspace()).strip()
    if cleaned:
        results.extend(AssetRepository.search_fts_lite(cleaned, per_type_limit))

    # 搜索创作者
    results.extend(CreatorRepository.search_by_name_or_bio(query, per_type_limit))

    # 搜索任务
    results.extend(TaskRepository.search_by_type_or_payload(query, per_type_limit))

    # 合并结果并排序（素材优先）
    results.sort(key=lambda x: {"asset": 0, "creator": 1, "task": 2}[x["type"]])

    return {"results": results[:limit]}

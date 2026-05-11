"""搜索 API 路由"""
from fastapi import APIRouter, Query
from media_tools.db.core import get_db_connection

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
    results = []
    
    with get_db_connection() as conn:
        conn.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
        
        # 搜索素材（使用 FTS5 全文索引）
        asset_results = conn.execute(
            """
            SELECT 
                'asset' as type,
                ma.asset_id as id,
                ma.title,
                c.nickname as subtitle,
                ma.transcript_status as status
            FROM media_assets ma
            LEFT JOIN creators c ON ma.creator_uid = c.uid
            WHERE ma.title LIKE ?
            ORDER BY ma.create_time DESC
            LIMIT ?
            """,
            (f"%{query}%", limit // 3),
        ).fetchall()
        
        results.extend(asset_results)
        
        # 搜索创作者
        creator_results = conn.execute(
            """
            SELECT 
                'creator' as type,
                uid as id,
                nickname as title,
                platform as subtitle,
                sync_status as status
            FROM creators
            WHERE nickname LIKE ? OR bio LIKE ?
            ORDER BY nickname
            LIMIT ?
            """,
            (f"%{query}%", f"%{query}%", limit // 3),
        ).fetchall()
        
        results.extend(creator_results)
        
        # 搜索任务（从 payload 中搜索）
        task_results = conn.execute(
            """
            SELECT 
                'task' as type,
                task_id as id,
                task_type as title,
                status as subtitle,
                NULL as status
            FROM task_queue
            WHERE task_type LIKE ? OR payload LIKE ?
            ORDER BY update_time DESC
            LIMIT ?
            """,
            (f"%{query}%", f"%{query}%", limit // 3),
        ).fetchall()
        
        results.extend(task_results)
    
    # 合并结果并排序（素材优先）
    results.sort(key=lambda x: {
        'asset': 0,
        'creator': 1,
        'task': 2
    }[x['type']])
    
    return {"results": results[:limit]}
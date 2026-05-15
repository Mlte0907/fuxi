"""伏羲 v1.0 — /api/v2/graph 路由（记忆图谱 API）"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.requests import Request

from fuxi.auth.acl import Permission, get_acl
from fuxi.config import config
from fuxi.memory.graph import MemoryGraph
from fuxi.models import ApiResponse

logger = logging.getLogger("fuxi.api.graph")
router = APIRouter(tags=["graph"])

_graph = MemoryGraph()


async def _require_write(request: Request):
    """验证写权限"""
    api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if api_key != config.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    # admin 角色有写权限
    agent_id = request.headers.get("X-Agent-ID", "admin")
    acl = get_acl()
    if not acl.check(agent_id, Permission.ADMIN):
        raise HTTPException(status_code=403, detail="Admin permission required")


@router.get("/graph/edges")
async def get_edges(
    limit: int = Query(500, ge=1, le=2000),
    drawer_id: Optional[str] = None,
):
    """获取所有边（用于图谱可视化）"""
    edges = _graph.get_edges(limit=limit, drawer_id=drawer_id)
    return ApiResponse.ok({"edges": edges, "count": len(edges)})

@router.get("/graph/stats")
async def graph_stats():
    """图谱统计"""
    return ApiResponse.ok(_graph.get_graph_stats())


@router.get("/graph/neighbors/{item_id}")
async def get_neighbors(
    item_id: str,
    edge_type: Optional[str] = None,
    direction: str = Query("both", pattern="^(outgoing|incoming|both)$"),
    max_depth: int = Query(1, ge=1, le=5),
    min_weight: float = Query(0.0, ge=0.0, le=1.0),
):
    """获取记忆节点的邻居"""
    neighbors = _graph.get_neighbors(
        item_id, edge_type=edge_type, direction=direction,
        max_depth=max_depth, min_weight=min_weight
    )
    return ApiResponse.ok({"item_id": item_id, "neighbors": neighbors, "count": len(neighbors)})


@router.get("/graph/bfs/{start_id}")
async def bfs_traverse(
    start_id: str,
    max_depth: int = Query(3, ge=1, le=6),
    edge_types: Optional[str] = None,
    min_weight: float = Query(0.3, ge=0.0, le=1.0),
):
    """BFS 图谱遍历"""
    etypes = edge_types.split(",") if edge_types else None
    result = _graph.bfs(start_id, max_depth=max_depth, edge_types=etypes, min_weight=min_weight)
    return ApiResponse.ok({"start_id": start_id, "nodes": result, "count": len(result)})


@router.get("/graph/causal/{item_id}")
async def causal_chain(
    item_id: str,
    max_length: int = Query(5, ge=1, le=10),
):
    """追溯因果链"""
    chain = _graph.causal_chain(item_id, max_length=max_length)
    return ApiResponse.ok({"item_id": item_id, "chain": chain, "length": len(chain)})


@router.post("/graph/edges")
async def add_edge(
    source_id: str,
    target_id: str,
    edge_type: str,
    weight: float = Query(0.5, ge=0.0, le=1.0),
    _auth=Depends(_require_write),
):
    """创建边（需要 admin 权限）"""
    try:
        edge_id = _graph.add_edge(source_id, target_id, edge_type, weight=weight)
        return ApiResponse.ok({"edge_id": edge_id, "source": source_id, "target": target_id, "type": edge_type})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/graph/edges/{edge_id}")
async def remove_edge(edge_id: str, _auth=Depends(_require_write)):
    """删除边（需要 admin 权限）"""
    _graph.remove_edge(edge_id)
    return ApiResponse.ok({"status": "deleted", "edge_id": edge_id})

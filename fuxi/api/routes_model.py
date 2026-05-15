"""伏羲 v1.0 — /api/v2/models 路由（模型路由配置 API）"""
import json
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from fuxi.models import ApiResponse
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.api.models")
router = APIRouter(tags=["models"])


class UpdateRouteRequest(BaseModel):
    rule_name: Optional[str] = None
    task_types: Optional[List[str]] = None
    agent_ids: Optional[List[str]] = None
    model_name: Optional[str] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None


class AddRouteRequest(BaseModel):
    rule_id: str = Field(..., min_length=1, max_length=64)
    rule_name: str = Field(..., min_length=1, max_length=128)
    task_types: List[str] = Field(default_factory=lambda: ["*"])
    agent_ids: List[str] = Field(default_factory=lambda: ["*"])
    model_name: str = Field(default="minimax/MiniMax-M2.7")
    priority: int = 0
    enabled: bool = True


@router.get("/models/routes")
async def list_routes(enabled_only: bool = True):
    pool = get_pool()
    clause = "WHERE enabled = 1" if enabled_only else ""
    rows = pool.fetchall(
        f"SELECT * FROM model_routing {clause} ORDER BY priority DESC, rule_name"
    )
    routes = []
    for r in rows:
        d = dict(r)
        for f in ("task_types", "agent_ids"):
            try:
                d[f] = json.loads(d[f]) if isinstance(d[f], str) else d[f]
            except (json.JSONDecodeError, TypeError):
                d[f] = []
        routes.append(d)
    return ApiResponse.ok({"routes": routes, "count": len(routes)})


@router.get("/models/routes/{rule_id}")
async def get_route(rule_id: str):
    pool = get_pool()
    row = pool.fetchone("SELECT * FROM model_routing WHERE rule_id = ?", (rule_id,))
    if not row:
        raise HTTPException(status_code=404, detail=f"Route not found: {rule_id}")
    d = dict(row)
    for f in ("task_types", "agent_ids"):
        try:
            d[f] = json.loads(d[f]) if isinstance(d[f], str) else d[f]
        except (json.JSONDecodeError, TypeError):
            d[f] = []
    return ApiResponse.ok(d)


@router.post("/models/routes")
async def add_route(req: AddRouteRequest):
    pool = get_pool()
    now = datetime.now().isoformat()
    with pool.connection() as c:
        c.execute(
            "INSERT OR REPLACE INTO model_routing "
            "(rule_id, rule_name, task_types, agent_ids, model_name, priority, enabled, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (req.rule_id, req.rule_name,
             json.dumps(req.task_types), json.dumps(req.agent_ids),
             req.model_name, req.priority, 1 if req.enabled else 0, now)
        )
    # 刷新内存缓存
    from fuxi.agent.model_router import reload_routes
    reload_routes()
    return ApiResponse.ok({"rule_id": req.rule_id, "status": "created"})


@router.patch("/models/routes/{rule_id}")
async def update_route(rule_id: str, req: UpdateRouteRequest):
    pool = get_pool()
    updates = {}
    if req.rule_name is not None:
        updates["rule_name"] = req.rule_name
    if req.task_types is not None:
        updates["task_types"] = json.dumps(req.task_types)
    if req.agent_ids is not None:
        updates["agent_ids"] = json.dumps(req.agent_ids)
    if req.model_name is not None:
        updates["model_name"] = req.model_name
    if req.priority is not None:
        updates["priority"] = req.priority
    if req.enabled is not None:
        updates["enabled"] = 1 if req.enabled else 0
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updated_at"] = datetime.now().isoformat()
    sets = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [rule_id]
    with pool.connection() as c:
        cur = c.execute(f"UPDATE model_routing SET {sets} WHERE rule_id=?", values)
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Route not found: {rule_id}")
    from fuxi.agent.model_router import reload_routes
    reload_routes()
    return ApiResponse.ok({"rule_id": rule_id, "status": "updated"})


@router.delete("/models/routes/{rule_id}")
async def delete_route(rule_id: str):
    pool = get_pool()
    with pool.connection() as c:
        cur = c.execute("DELETE FROM model_routing WHERE rule_id = ?", (rule_id,))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Route not found: {rule_id}")
    from fuxi.agent.model_router import reload_routes
    reload_routes()
    return ApiResponse.ok({"rule_id": rule_id, "status": "deleted"})


@router.get("/models/available")
async def list_available_models():
    """列出当前系统可用的模型"""
    from fuxi.config import config
    return ApiResponse.ok({
        "models": [
            {"name": "minimax/MiniMax-M2.7", "type": "chat/completion", "status": "available"},
        ],
        "default_model": config.openclaw_llm_model,
        "gateway": config.openclaw_gateway,
    })

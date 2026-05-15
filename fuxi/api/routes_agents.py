"""伏羲 v1.0 — /api/v2/agents 路由"""
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from fuxi.auth.acl import get_acl
from fuxi.models import ApiResponse
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.api.agents")
router = APIRouter(tags=["agents"])


@router.get("/agents")
async def list_agents():
    pool = get_pool()
    rows = pool.fetchall("SELECT * FROM agent_views")
    acl = get_acl()
    acl_agents = acl.list_agents()
    return ApiResponse.ok({
        "agents": [dict(r) for r in rows],
        "acl": acl_agents
    })


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    pool = get_pool()
    row = pool.fetchone(
        "SELECT * FROM unified_acl WHERE agent_id = ?", (agent_id,)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")
    result = dict(row)
    result["permissions"] = json.loads(result.get("permissions", "[]"))
    result["agent_domains"] = json.loads(result.get("agent_domains", "[]"))
    return ApiResponse.ok(result)


class SetAgentViewRequest(BaseModel):
    item_ids: List[str] = []
    perspective: str = ""


@router.put("/agents/{agent_id}/view")
async def set_agent_view(
    agent_id: str,
    drawer_id: Optional[str] = Query(default=None),
    req: Optional[SetAgentViewRequest] = Body(default=None),
):
    pool = get_pool()
    if req is None:
        req = SetAgentViewRequest()
    with pool.connection() as c:
        if req.item_ids:
            for item_id in req.item_ids:
                c.execute(
                    "INSERT OR IGNORE INTO agent_views (agent_id, item_id, drawer_id, perspective) VALUES (?,?,?,?)",
                    (agent_id, item_id, drawer_id or "default", req.perspective)
                )
        elif drawer_id:
            c.execute(
                "INSERT OR IGNORE INTO agent_views (agent_id, item_id, drawer_id, perspective) VALUES (?,?,?,?)",
                (agent_id, "", drawer_id, req.perspective)
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="At least one of item_ids or drawer_id required"
            )
    return ApiResponse.ok({"status": "ok", "agent_id": agent_id})


@router.get("/agents/{agent_id}/view")
async def get_agent_view(agent_id: str, limit: int = 20):
    pool = get_pool()
    rows = pool.fetchall(
        "SELECT i.*, av.drawer_id, av.perspective FROM items i "
        "JOIN agent_views av ON av.item_id = i.id "
        "WHERE av.agent_id = ? AND i.archived = 0 ORDER BY i.updated_at DESC LIMIT ?",
        (agent_id, limit)
    )
    view_row = pool.fetchone(
        "SELECT drawer_id, perspective FROM agent_views "
        "WHERE agent_id = ? AND item_id = '' LIMIT 1",
        (agent_id,)
    )
    return ApiResponse.ok({
        "agent_id": agent_id,
        "items": [dict(r) for r in rows],
        "drawer_id": view_row["drawer_id"] if view_row else None,
        "perspective": view_row["perspective"] if view_row else "",
    })


# ── OpenClaw Gateway 集成 ──

@router.get("/agents/openclaw/health")
async def openclaw_health():
    from fuxi.agent.integration import OpenClawAdapter
    adapter = OpenClawAdapter()
    return ApiResponse.ok(adapter.health())


@router.get("/agents/openclaw/agents")
async def openclaw_list_agents():
    from fuxi.agent.integration import OpenClawAdapter
    adapter = OpenClawAdapter()
    agents = adapter.list_openclaw_agents()
    return ApiResponse.ok({"agents": agents})


@router.post("/agents/openclaw/{agent_id}/invoke")
async def openclaw_invoke(agent_id: str, message: str = Query(...), model: Optional[str] = None):
    from fuxi.agent.integration import OpenClawAdapter
    adapter = OpenClawAdapter()
    result = adapter.call_agent(agent_id, message, model)
    if result is None:
        raise HTTPException(status_code=502, detail="OpenClaw gateway unreachable")
    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])
    return ApiResponse.ok(result)

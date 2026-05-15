"""伏羲 v1.0 — /api/v2/tools 路由（工具注册表 API）"""
import logging
import os
import re
import subprocess
import tempfile
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from fuxi.models import ApiResponse
from fuxi.tools.registry import get_tool_registry

logger = logging.getLogger("fuxi.api.tools")
router = APIRouter(tags=["tools"])


class RegisterToolRequest(BaseModel):
    tool_id: str = Field(..., min_length=1, max_length=64)
    tool_name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    backend: str = Field("local", pattern="^(local|docker|api)$")
    need_confirmation: bool = False
    config_json: Optional[dict] = None


class InvokeToolRequest(BaseModel):
    params: dict = Field(default_factory=dict)
    agent_id: str = "system"


@router.get("/tools")
async def list_tools(backend: Optional[str] = None, active_only: bool = True):
    """列出所有已注册的工具"""
    reg = get_tool_registry()
    tools = reg.list_tools(backend=backend, active_only=active_only)
    return ApiResponse.ok({"tools": tools, "count": len(tools)})


@router.get("/tools/stats")
async def tool_stats():
    reg = get_tool_registry()
    return ApiResponse.ok(reg.get_tool_stats())


@router.get("/tools/{tool_id}")
async def get_tool(tool_id: str):
    reg = get_tool_registry()
    tool = reg.get_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_id}")
    return ApiResponse.ok(tool)


@router.post("/tools")
async def register_tool(req: RegisterToolRequest):
    reg = get_tool_registry()
    reg.register(
        tool_id=req.tool_id, tool_name=req.tool_name,
        description=req.description, backend=req.backend,
        need_confirmation=req.need_confirmation,
        config_json=req.config_json
    )
    return ApiResponse.ok({"tool_id": req.tool_id, "status": "registered"})


@router.patch("/tools/{tool_id}")
async def update_tool(tool_id: str, req: RegisterToolRequest):
    reg = get_tool_registry()
    existing = reg.get_tool(tool_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_id}")
    reg.update_tool(tool_id,
                    tool_name=req.tool_name,
                    description=req.description,
                    backend=req.backend,
                    need_confirmation=req.need_confirmation,
                    config_json=req.config_json)
    return ApiResponse.ok({"tool_id": tool_id, "status": "updated"})


@router.post("/tools/{tool_id}/invoke")
async def invoke_tool(tool_id: str, req: InvokeToolRequest, request: Request):
    """调用工具 — 通过 OpenClaw Gateway 执行"""
    import time
    reg = get_tool_registry()
    tool = reg.get_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_id}")

    t0 = time.time()
    try:
        if tool["tool_id"] == "fuxi_memory_write" and req.params.get("text"):
            from fuxi.memory.ingestion import remember
            item_id = remember(
                raw_text=req.params["text"],
                drawer_id=req.params.get("drawer_id", "default"),
                importance=req.params.get("importance", 0.5),
                tags=req.params.get("tags", []),
                source=req.params.get("source", "tool"),
                created_by=req.agent_id,
            )
            result = {"status": "ok", "item_id": item_id}
        elif tool["tool_id"] == "fuxi_memory_search" and req.params.get("query"):
            from fuxi.memory.search import search
            items = search(
                query=req.params["query"],
                drawer_id=req.params.get("drawer_id"),
                limit=req.params.get("limit", 10),
            )
            result = {"status": "ok", "items": items, "count": len(items)}
        elif tool["tool_id"] == "web_search" and req.params.get("query"):
            query = req.params["query"]
            max_results = req.params.get("max_results", 5)
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(
                        "https://html.duckduckgo.com/html/",
                        params={"q": query},
                        headers={"User-Agent": "FuxiMemory/1.0"}
                    )
                    resp.raise_for_status()
                    snippets = re.findall(
                        r'class="result__snippet"[^>]*>(.*?)</a>',
                        resp.text, re.DOTALL
                    )
                    results = []
                    for s in snippets[:max_results]:
                        clean = re.sub(r'<[^>]+>', '', s).strip()[:500]
                        if clean:
                            results.append({"snippet": clean})
                    result = {"status": "ok", "results": results, "count": len(results)}
            except Exception as e:
                logger.warning(f"web_search failed for '{query}': {e}")
                result = {"status": "error", "error": f"Web search failed: {e}"}

        elif tool["tool_id"] == "code_execute" and req.params.get("code"):
            code = req.params["code"]
            timeout_sec = req.params.get("timeout", 30)
            if tool.get("backend") == "docker":
                result = {
                    "status": "not_implemented",
                    "message": "Docker backend for code_execute not yet available"
                }
            else:
                try:
                    with tempfile.NamedTemporaryFile(
                        mode='w', suffix='.py', delete=False
                    ) as f:
                        f.write(code)
                        tmp_path = f.name
                    proc = subprocess.run(
                        ["python3", tmp_path],
                        capture_output=True, text=True, timeout=timeout_sec
                    )
                    os.unlink(tmp_path)
                    result = {
                        "status": "ok",
                        "stdout": proc.stdout[-2000:],
                        "stderr": proc.stderr[-2000:],
                        "returncode": proc.returncode,
                    }
                except subprocess.TimeoutExpired:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    result = {"status": "error", "error": f"Code execution timed out after {timeout_sec}s"}
                except Exception as e:
                    result = {"status": "error", "error": str(e)}

        else:
            result = {
                "status": "not_implemented",
                "message": f"Tool '{tool_id}' requires params or is not invocable",
                "backend": tool["backend"],
            }
    except Exception as e:
        result = {"status": "error", "error": str(e)}

    duration_ms = (time.time() - t0) * 1000
    reg.record_usage(tool_id, agent_id=req.agent_id, params=req.params,
                     result=result, duration_ms=duration_ms)
    return ApiResponse.ok({"tool_id": tool_id, "result": result, "duration_ms": round(duration_ms, 1)})

"""伏羲跨工具兼容路由 - /api/v2/compat/*"""
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fuxi.models import ApiResponse
from fuxi.compat.adapters import CursorAdapter, CodexAdapter, OpenCodeAdapter

logger = logging.getLogger("fuxi.compat")
router = APIRouter(prefix="/api/v2/compat", tags=["compat"])


class GenerateConfigRequest(BaseModel):
    tool: str  # "cursor" | "codex" | "opencode"
    project_path: str = None


@router.post("/generate")
async def generate_tool_config(req: GenerateConfigRequest):
    """为指定工具生成配置文件"""
    adapter_map = {
        "cursor": CursorAdapter,
        "codex": CodexAdapter,
        "opencode": OpenCodeAdapter,
    }

    adapter_cls = adapter_map.get(req.tool.lower())
    if not adapter_cls:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {req.tool}")

    adapter = adapter_cls(project_path=req.project_path)
    results = adapter.write_configs()

    return ApiResponse.ok({"tool": req.tool, "generated": results})


@router.get("/tools")
async def list_supported_tools():
    """列出支持的工具"""
    return ApiResponse.ok({
        "tools": ["cursor", "codex", "opencode"],
        "capabilities": {
            "cursor": ["hooks", "rules", "agents"],
            "codex": ["config.toml", "agents"],
            "opencode": ["opencode.json", "plugins"],
        }
    })


@router.get("/status")
async def compat_status():
    """兼容层状态检查"""
    return ApiResponse.ok({
        "enabled": True,
        "adapters": ["cursor", "codex", "opencode"],
        "fuxi_endpoint": "http://localhost:19528",
    })

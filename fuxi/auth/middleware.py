"""伏羲 v1.0 — FastAPI 权限中间件"""
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from fuxi.auth.acl import Permission, get_acl
from fuxi.config import config

logger = logging.getLogger("fuxi.auth.middleware")

PUBLIC_PATHS = {"/health", "/health/deep", "/docs", "/openapi.json", "/metrics", "/dashboard", "/favicon.ico", "/anthropic"}
PUBLIC_PREFIXES = {"/static/", "/anthropic/"}

PATH_PERMISSION_MAP = {
    # Memories
    "GET /api/v2/memories": Permission.READ,
    "POST /api/v2/memories": Permission.WRITE,
    "PUT /api/v2/memories": Permission.WRITE,
    "DELETE /api/v2/memories": Permission.DELETE,
    # Engines
    "GET /api/v2/engines": Permission.READ,
    "POST /api/v2/engines": Permission.ENGINE_CONTROL,
    # Agents
    "GET /api/v2/agents": Permission.READ,
    "POST /api/v2/agents": Permission.AGENT_IMPERSONATE,
    # Tasks
    "GET /api/v2/tasks": Permission.READ,
    "POST /api/v2/tasks": Permission.WRITE,
    "PATCH /api/v2/tasks": Permission.WRITE,
    "DELETE /api/v2/tasks": Permission.DELETE,
    # Collaboration
    "POST /api/v2/collaboration": Permission.AGENT_IMPERSONATE,
    "GET /api/v2/collaboration": Permission.READ,
    # Graph
    "GET /api/v2/graph": Permission.READ,
    "POST /api/v2/graph": Permission.WRITE,
    # Admin & System
    "GET /api/v2/admin": Permission.ADMIN,
    "POST /api/v2/admin": Permission.ADMIN,
    "GET /api/v2/system": Permission.ADMIN,
    # Cron
    "GET /api/v2/cron": Permission.READ,
    "POST /api/v2/cron": Permission.WRITE,
    "PATCH /api/v2/cron": Permission.WRITE,
    "DELETE /api/v2/cron": Permission.DELETE,
    # Models
    "GET /api/v2/models": Permission.READ,
    "POST /api/v2/models": Permission.ADMIN,
    # Memory Judge (Nudge)
    "POST /api/v2/memory/judge": Permission.WRITE,
    "GET /api/v2/memory/judge": Permission.READ,
    # Profile
    "GET /api/v2/profile": Permission.READ,
    "PUT /api/v2/profile": Permission.WRITE,
    # Tools
    "GET /api/v2/tools": Permission.READ,
    "POST /api/v2/tools": Permission.WRITE,
    "PATCH /api/v2/tools": Permission.WRITE,
    # Adaptive
    "GET /api/v2/adaptive/params": Permission.READ,
    "GET /api/v2/adaptive/signals": Permission.READ,
    "POST /api/v2/adaptive/evaluate": Permission.ADMIN,
    # Decisions
    "GET /api/v2/decisions": Permission.READ,
    "POST /api/v2/decisions/evaluate": Permission.ADMIN,
    "GET /api/v2/decisions/experiences": Permission.READ,
    "GET /api/v2/decisions/advice": Permission.READ,
}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        if any(request.url.path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)

        api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        expected_key = config.api_key
        if not expected_key:
            # 未配置 API key 时拒绝所有受保护路径
            return JSONResponse(status_code=401, content={"detail": "API key not configured"})
        if api_key != expected_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"}
            )

        agent_id = request.headers.get("X-Agent-ID", "")
        if agent_id:
            required_perm = None
            for path, perm in PATH_PERMISSION_MAP.items():
                route_path = path.split(" ", 1)[1]
                if request.url.path.startswith(route_path) and path.startswith(request.method + " "):
                    required_perm = perm
                    break

            if required_perm:
                acl = get_acl()
                if not acl.check(agent_id, required_perm):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": f"Agent {agent_id} lacks permission"}
                    )

        return await call_next(request)

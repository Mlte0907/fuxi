"""伏羲 v1.0 — /api/v2/engines 路由"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fuxi.engines.base import get_engine_registry
from fuxi.models import ApiResponse

logger = logging.getLogger("fuxi.api.engines")
router = APIRouter(tags=["engines"])


@router.get("/engines")
async def list_engines():
    return ApiResponse.ok(get_engine_registry().list_all())


class TierChangeRequest(BaseModel):
    tier: str  # "essential", "standard", "advanced", "all"


@router.post("/engines/tier")
async def set_engine_tier(req: TierChangeRequest):
    """切换引擎分层"""
    from fuxi.config import config
    valid = ["essential", "standard", "advanced", "all"]
    if req.tier not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {req.tier}")
    config.engine_tier = req.tier
    return ApiResponse.ok({"tier": req.tier, "enabled_engines": get_engine_registry().list_all()})


@router.get("/engines/tier")
async def get_engine_tier():
    """获取当前引擎分层"""
    from fuxi.config import config
    from fuxi.engines import ENGINE_TIERS
    tier = config.engine_tier
    enabled = ENGINE_TIERS.get(tier, ENGINE_TIERS["standard"])
    return ApiResponse.ok({"tier": tier, "enabled_engines": enabled})


@router.get("/engines/health")
async def bulk_engine_health():
    """批量查询所有引擎健康状态"""
    registry = get_engine_registry()
    all_engines = registry.list_all()
    health_results = []
    error_count = 0
    for e in all_engines:
        name = e["name"]
        engine = registry.get(name)
        hc = engine.health_check() if engine else {"error": "not_found"}
        # 兼容不同引擎的 health_check 字段差异
        ec = hc.get("error_count", 0) or hc.get("alert_count", 0) or 0
        rc = hc.get("run_count", 0) or hc.get("observations_count", 0) or 0
        health_results.append({
            "name": name,
            "running": e["running"],
            "experimental": e["experimental"],
            "health": {**hc, "error_count": ec, "run_count": rc},
        })
        if ec > 0:
            error_count += ec

    return ApiResponse.ok({
        "total": len(health_results),
        "running": sum(1 for h in health_results if h["running"]),
        "stopped": sum(1 for h in health_results if not h["running"]),
        "total_errors": error_count,
        "engines": health_results,
    })


@router.get("/engines/{engine_name}")
async def get_engine(engine_name: str):
    engine = get_engine_registry().get(engine_name)
    if not engine:
        raise HTTPException(status_code=404, detail=f"Engine '{engine_name}' not found")
    return ApiResponse.ok({
        "name": engine_name,
        "state": engine.get_state(),
        "health": engine.health_check()
    })


class EngineControlRequest(BaseModel):
    action: str  # "start", "stop", "pause", "resume"


@router.post("/engines/{engine_name}/control")
async def control_engine(engine_name: str, req: EngineControlRequest):
    engine = get_engine_registry().get(engine_name)
    if not engine:
        raise HTTPException(status_code=404, detail=f"Engine '{engine_name}' not found")

    action = req.action
    if action == "start":
        engine.start()
    elif action == "stop":
        engine.stop()
    elif action == "pause":
        engine.pause()
    elif action == "resume":
        engine.resume()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

    return ApiResponse.ok({"engine": engine_name, "action": action, "status": "ok"})


@router.get("/engines/{engine_name}/health")
async def engine_health(engine_name: str):
    engine = get_engine_registry().get(engine_name)
    if not engine:
        raise HTTPException(status_code=404, detail=f"Engine '{engine_name}' not found")
    return ApiResponse.ok(engine.health_check())

@router.post("/engines/{engine_name}/run")
async def run_engine(engine_name: str):
    """手动触发引擎执行一次"""
    engine = get_engine_registry().get(engine_name)
    if not engine:
        raise HTTPException(status_code=404, detail=f"Engine '{engine_name}' not found")
    try:
        result = engine._execute()
        return ApiResponse.ok({"engine": engine_name, "status": "ok", "result": result})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/engines/run_all")
async def run_all_engines(include_experimental: bool = False):
    """批量运行所有引擎"""
    try:
        results = get_engine_registry().run_all(include_experimental=include_experimental)
        return ApiResponse.ok({"status": "ok", "results": results})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


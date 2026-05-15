"""伏羲 v1.0 — /api/v2/system 路由"""
import logging
import platform
import time

from fastapi import APIRouter

from fuxi.config import config
from fuxi.models import ApiResponse

logger = logging.getLogger("fuxi.api.system")
router = APIRouter(tags=["system"])

_START_TIME = time.time()


@router.get("/system/info")
async def system_info():
    import sys

    return ApiResponse.ok({
        "version": "1.0.0",
        "python": sys.version,
        "platform": platform.platform(),
        "uptime_seconds": round(time.time() - _START_TIME),
        "host": config.host,
        "port": config.port,
    })


@router.get("/system/config")
async def get_config():
    result = config.model_dump()
    for k in list(result.keys()):
        if "key" in k.lower() and result[k]:
            v = result[k]
            result[k] = v[:8] + "***" if len(v) > 8 else "***"
    return ApiResponse.ok(result)

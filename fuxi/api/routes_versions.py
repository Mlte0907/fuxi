"""伏羲 v1.0 — /api/versions 路由"""
from fastapi import APIRouter, Request

from fuxi.api.versioning import get_version_info
from fuxi.models import ApiResponse

router = APIRouter(tags=["versions"])


@router.get("/api/versions")
async def list_versions(request: Request):
    """返回 API 版本信息"""
    info = get_version_info()
    # 在响应中附加当前版本标头
    response = ApiResponse.ok(info)
    return response


@router.get("/api/versions/deprecated")
async def list_deprecated():
    """列出已弃用的端点及迁移路径"""
    from fuxi.api.versioning import DEPRECATED_PATHS
    return ApiResponse.ok({
        "deprecated": DEPRECATED_PATHS,
        "count": len(DEPRECATED_PATHS),
    })

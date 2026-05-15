"""伏羲 v1.0 — /metrics Prometheus 端点"""
from fastapi import APIRouter, Response

from fuxi.observability.metrics import get_metrics_response

router = APIRouter(tags=["observability"])


@router.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus 指标导出端点"""
    content, media_type = get_metrics_response()
    return Response(content=content, media_type=media_type)

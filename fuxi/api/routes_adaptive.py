"""伏羲 v1.0 — /api/v2/adaptive 路由"""
import logging

from fastapi import APIRouter, HTTPException

from fuxi.models import ApiResponse

logger = logging.getLogger("fuxi.api.adaptive")
router = APIRouter(tags=["adaptive"])


@router.get("/adaptive/params")
async def get_adaptive_params():
    """获取当前自适应参数"""
    from fuxi.engines.base import get_engine_registry
    engine = get_engine_registry().get("adaptive")
    if not engine:
        raise HTTPException(status_code=503, detail="Adaptive engine not available")
    params = engine._load_params()
    return ApiResponse.ok({
        "decay_base": params.decay_base,
        "touch_boost_short": params.touch_boost_short,
        "touch_boost_long": params.touch_boost_long,
        "decay_floor": params.decay_floor,
        "vector_weight": params.vector_weight,
        "fts_weight": params.fts_weight,
        "similarity_threshold": params.similarity_threshold,
        "wm_capacity": params.wm_capacity,
        "wm_decay_rate": params.wm_decay_rate,
        "attention_replenish_rate": params.attention_replenish_rate,
        "dedup_boost_importance": params.dedup_boost_importance,
        "dedup_boost_decay": params.dedup_boost_decay,
        "last_updated": params.last_updated,
        "update_reason": params.update_reason,
        "confidence": params.confidence,
    })


@router.post("/adaptive/evaluate")
async def evaluate_adaptive():
    """手动触发自适应评估"""
    from fuxi.engines.base import get_engine_registry
    engine = get_engine_registry().get("adaptive")
    if not engine:
        raise HTTPException(status_code=503, detail="Adaptive engine not available")
    result = engine.run()
    return ApiResponse.ok(result)


@router.get("/adaptive/signals")
async def get_behavior_signals():
    """获取当前行为信号"""
    from fuxi.adaptive.signals import get_behavior_collector
    collector = get_behavior_collector()
    signals = collector.get_user_profile_signals()
    return ApiResponse.ok(signals)

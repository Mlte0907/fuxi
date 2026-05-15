"""伏羲 v1.0 — /api/v2/persona 路由"""
import json
import logging

from fastapi import APIRouter, HTTPException

from fuxi.models import ApiResponse
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.api.persona")
router = APIRouter(tags=["persona"])


@router.get("/persona")
async def get_persona_state():
    """获取完整人格状态"""
    pool = get_pool()
    row = pool.fetchone(
        "SELECT state_json FROM engine_states WHERE engine_name='persona'"
    )

    from fuxi.engines.persona import PersonaEngine
    defaults = dict(PersonaEngine.PERSONALITY_DEFAULTS)

    if row:
        try:
            data = json.loads(row["state_json"])
            return ApiResponse.ok({
                "traits": data.get("personality_traits", defaults),
                "mood": data.get("mood", "平静"),
                "report_history": data.get("report_history", []),
                "updated_at": data.get("updated_at", ""),
            })
        except Exception:
            pass

    return ApiResponse.ok({
        "traits": defaults,
        "mood": "平静",
        "report_history": [],
        "updated_at": "",
        "note": "Persona engine has not yet initialized",
    })


@router.get("/persona/reports")
async def get_persona_reports(limit: int = 10):
    """获取报告历史"""
    pool = get_pool()
    row = pool.fetchone(
        "SELECT state_json FROM engine_states WHERE engine_name='persona'"
    )
    if not row:
        return ApiResponse.ok({"reports": [], "count": 0})

    try:
        data = json.loads(row["state_json"])
        history = data.get("report_history", [])
        return ApiResponse.ok({
            "reports": history[-limit:],
            "count": len(history),
        })
    except Exception:
        return ApiResponse.ok({"reports": [], "count": 0})


@router.post("/persona/speak")
async def force_persona_speak():
    """强制人格化身立即生成一份报告"""
    from fuxi.engines.base import get_engine_registry
    engine = get_engine_registry().get("persona")
    if not engine:
        raise HTTPException(status_code=503, detail="Persona engine not available")

    result = engine.run()
    return ApiResponse.ok(result)


@router.get("/persona/traits")
async def get_persona_traits():
    """获取人格特质"""
    pool = get_pool()
    row = pool.fetchone(
        "SELECT state_json FROM engine_states WHERE engine_name='persona'"
    )
    from fuxi.engines.persona import PersonaEngine
    defaults = dict(PersonaEngine.PERSONALITY_DEFAULTS)

    if row:
        try:
            data = json.loads(row["state_json"])
            return ApiResponse.ok(data.get("personality_traits", defaults))
        except Exception:
            pass

    return ApiResponse.ok(defaults)


@router.put("/persona/traits")
async def update_persona_traits(traits: dict):
    """更新人格特质（admin）"""
    pool = get_pool()
    from fuxi.engines.persona import PersonaEngine
    valid_keys = set(PersonaEngine.PERSONALITY_DEFAULTS.keys())

    cleaned = {}
    for k, v in traits.items():
        if k in valid_keys and isinstance(v, (int, float)):
            cleaned[k] = round(max(0.05, min(1.0, float(v))), 4)

    if not cleaned:
        raise HTTPException(status_code=400, detail="No valid trait keys provided")

    with pool.connection() as c:
        existing = c.execute(
            "SELECT state_json FROM engine_states WHERE engine_name='persona'"
        ).fetchone()

        if existing:
            data = json.loads(existing["state_json"])
            current = data.get("personality_traits", dict(PersonaEngine.PERSONALITY_DEFAULTS))
        else:
            data = {"report_history": [], "mood": "平静"}
            current = dict(PersonaEngine.PERSONALITY_DEFAULTS)

        current.update(cleaned)
        data["personality_traits"] = current

        from datetime import datetime
        c.execute(
            "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
            "VALUES (?,?,?)",
            ("persona", json.dumps(data, ensure_ascii=False), datetime.now().isoformat())
        )

    return ApiResponse.ok({
        "traits": current,
        "updated": list(cleaned.keys()),
    })


@router.get("/persona/mood")
async def get_persona_mood():
    """获取当前语气"""
    pool = get_pool()
    row = pool.fetchone(
        "SELECT state_json FROM engine_states WHERE engine_name='persona'"
    )
    if row:
        try:
            data = json.loads(row["state_json"])
            return ApiResponse.ok({
                "mood": data.get("mood", "平静"),
                "updated_at": data.get("updated_at", ""),
            })
        except Exception:
            pass

    return ApiResponse.ok({"mood": "平静", "updated_at": ""})


@router.post("/persona/deliver")
async def persona_deliver(message: str = None):
    """手动推送消息到 fuxi 出口 Agent（测试/手动触发用）"""
    from fuxi.engines.base import get_engine_registry
    engine = get_engine_registry().get("persona")
    if not engine:
        raise HTTPException(status_code=503, detail="Persona engine not available")

    if not message:
        # 使用模板生成一份报告作为消息
        message = engine._template_report()

    ctx = engine._gather_context()
    engine._deliver_to_fuxi_agent(message, "manual", ctx)

    return ApiResponse.ok({
        "delivered": True,
        "message_preview": message[:120],
        "agent": "fuxi",
    })

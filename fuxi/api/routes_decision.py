"""伏羲 v1.0 — /api/v2/decisions 路由"""
import logging

from fastapi import APIRouter, Query

from fuxi.models import ApiResponse

logger = logging.getLogger("fuxi.api.decisions")
router = APIRouter(tags=["decisions"])


@router.get("/decisions")
async def list_decisions(
    limit: int = Query(20, ge=1, le=100),
    status: str = Query("", description="Filter by status"),
):
    """列出最近的决策记录"""
    from fuxi.store.connection import get_pool
    pool = get_pool()
    if status:
        rows = pool.fetchall(
            "SELECT id, event_type, source, event_data, created_at "
            "FROM event_log WHERE event_type='decision' AND json_extract(event_data, '$.status')=? "
            "ORDER BY created_at DESC LIMIT ?",
            (status, limit)
        )
    else:
        rows = pool.fetchall(
            "SELECT id, event_type, source, event_data, created_at "
            "FROM event_log WHERE event_type='decision' "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
    import json
    decisions = []
    for row in rows:
        data = json.loads(row["event_data"]) if isinstance(row["event_data"], str) else row["event_data"]
        data["record_id"] = row["id"]
        data["created_at"] = row["created_at"]
        decisions.append(data)
    return ApiResponse.ok({"decisions": decisions, "total": len(decisions)})


@router.get("/decisions/{decision_id}")
async def get_decision(decision_id: str):
    """获取单条决策详情"""
    import json

    from fuxi.store.connection import get_pool
    pool = get_pool()
    row = pool.fetchone(
        "SELECT id, event_type, source, event_data, created_at "
        "FROM event_log WHERE event_type='decision' AND json_extract(event_data, '$.id')=?",
        (decision_id,)
    )
    if not row:
        return ApiResponse.error(404, f"Decision {decision_id} not found")
    data = json.loads(row["event_data"]) if isinstance(row["event_data"], str) else row["event_data"]
    data["record_id"] = row["id"]
    data["created_at"] = row["created_at"]
    return ApiResponse.ok(data)


@router.post("/decisions/evaluate")
async def trigger_decision_evaluation():
    """手动触发自主决策评估"""
    from fuxi.engines.decision import DecisionEngine
    engine = DecisionEngine()
    result = engine.run()
    return ApiResponse.ok(result)


@router.get("/decisions/experiences")
async def list_experiences(
    limit: int = Query(20, ge=1, le=100),
):
    """列出经验库中的经验记录"""
    from fuxi.store.connection import get_pool
    pool = get_pool()
    rows = pool.fetchall(
        "SELECT id, task_type, input_desc, reasoning_summary, conclusion, outcome, created_at "
        "FROM experience_bank ORDER BY created_at DESC LIMIT ?",
        (limit,)
    )
    experiences = []
    for row in rows:
        experiences.append({
            "id": row["id"],
            "task_type": row["task_type"],
            "input_desc": row["input_desc"],
            "reasoning_summary": row["reasoning_summary"],
            "conclusion": row["conclusion"],
            "outcome": row["outcome"],
            "created_at": row["created_at"],
        })
    return ApiResponse.ok({"experiences": experiences, "total": len(experiences)})

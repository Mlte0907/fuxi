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


@router.get("/decisions/advice")
async def get_decision_advice(
    task: str = Query(..., description="任务描述"),
    context: str = Query("", description="额外上下文"),
):
    """基于记忆系统获取决策建议（供 Hook 调用）"""
    import json
    from fuxi.store.connection import get_pool
    from datetime import datetime

    logger.warning(f"[UNIQUE_MARKER_168161] Decision advice endpoint hit, task={task}")

    # 1. 查询相关决策经验
    decision_rows = pool.fetchall(
        "SELECT event_data, created_at FROM event_log "
        "WHERE event_type='decision' AND created_at > datetime('now', '-30 days') "
        "ORDER BY created_at DESC LIMIT 20"
    )

    # 2. 查询相关技能进化记录
    skill_rows = pool.fetchall(
        "SELECT raw_text, importance, tags, created_at FROM items "
        "WHERE drawer_id IN ('instincts', 'skills') AND archived=0 "
        "AND created_at > datetime('now', '-30 days') "
        "ORDER BY importance DESC LIMIT 10"
    )

    # 3. 构造建议
    suggestions = []
    keywords = task.lower().split()

    for row in decision_rows:
        data = json.loads(row["event_data"]) if isinstance(row["event_data"], str) else row["event_data"]
        decision_text = data.get("decision", "") or data.get("description", "")
        if any(kw in decision_text.lower() for kw in keywords if len(kw) > 3):
            suggestions.append({
                "type": "decision",
                "source": data.get("source", "unknown"),
                "advice": decision_text[:200],
                "outcome": data.get("outcome", "unknown"),
                "date": row["created_at"],
            })

    for row in skill_rows:
        tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else row.get("tags", [])
        text_lower = row["raw_text"].lower()
        if any(kw in text_lower for kw in keywords if len(kw) > 3):
            suggestions.append({
                "type": "skill",
                "source": row["raw_text"][:50],
                "advice": row["raw_text"][:200],
                "confidence": row["importance"],
                "tags": tags,
                "date": row["created_at"],
            })

    # 4. 去重并限制数量
    seen = set()
    unique = []
    for s in suggestions:
        key = s["advice"][:50]
        if key not in seen:
            seen.add(key)
            unique.append(s)
    unique = unique[:5]

    return ApiResponse.ok({
        "task": task,
        "context": context,
        "suggestions": unique,
        "count": len(unique),
        "timestamp": datetime.now().isoformat(),
    })

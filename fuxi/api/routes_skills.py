"""伏羲 v1.0 — Skill 生态市场 CRUD API

基于 experience_bank 表实现技能的管理、搜索、审核与绑定。
"""
import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from fuxi.models import ApiResponse
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.api.skills")
router = APIRouter(tags=["skills"])


# ── Pydantic 模型 ──


class SkillCreate(BaseModel):
    skill_name: str
    task_type: str = ""
    description: str = ""
    trigger_keywords: list[str] = []
    agent_id: str = ""
    quality_score: float = 0.5
    skill_file_path: str = ""
    reasoning_summary: str = ""


class SkillUpdate(BaseModel):
    skill_name: Optional[str] = None
    task_type: Optional[str] = None
    description: Optional[str] = None
    trigger_keywords: Optional[list[str]] = None
    agent_id: Optional[str] = None
    quality_score: Optional[float] = None
    skill_file_path: Optional[str] = None
    reasoning_summary: Optional[str] = None


class SkillReview(BaseModel):
    status: str  # approved | rejected
    reviewer: str = ""
    note: str = ""


def _row_to_skill(row: dict) -> dict:
    """将 sqlite3.Row 转为 API 响应格式。"""
    return {
        "id": row["id"],
        "skill_name": row.get("skill_name", ""),
        "task_type": row.get("task_type", ""),
        "description": row.get("input_desc", ""),
        "trigger_keywords": json.loads(row.get("trigger_keywords", "[]")),
        "agent_id": row.get("agent_id", ""),
        "quality_score": row.get("quality_score", 0.5),
        "review_status": row.get("review_status", "pending"),
        "reviewed_by": row.get("reviewed_by", ""),
        "review_note": row.get("review_note", ""),
        "skill_file_path": row.get("skill_file_path", ""),
        "reasoning_summary": row.get("reasoning_summary", ""),
        "outcome": row.get("outcome", "unknown"),
        "created_at": row.get("created_at", ""),
    }


# ── CRUD 端点 ──


@router.post("/skills")
async def create_skill(skill: SkillCreate):
    """创建新技能。"""
    pool = get_pool()
    skill_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    pool.execute(
        """INSERT INTO experience_bank
           (id, skill_name, task_type, input_desc, trigger_keywords,
            agent_id, quality_score, skill_file_path, reasoning_summary,
            review_status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
        (
            skill_id,
            skill.skill_name,
            skill.task_type,
            skill.description,
            json.dumps(skill.trigger_keywords),
            skill.agent_id,
            skill.quality_score,
            skill.skill_file_path,
            skill.reasoning_summary,
            now,
        ),
    )
    logger.info(f"Skill created: {skill_id} — {skill.skill_name}")
    return ApiResponse.ok({"id": skill_id, "skill_name": skill.skill_name})


@router.get("/skills")
async def list_skills(
    agent_id: Optional[str] = Query(None),
    task_type: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    min_quality: float = Query(0.0),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """搜索/列出技能市场。支持按 agent、类型、审核状态、关键词、质量分过滤。"""
    pool = get_pool()
    conditions = []
    params = []

    if agent_id:
        conditions.append("agent_id = ?")
        params.append(agent_id)
    if task_type:
        conditions.append("task_type = ?")
        params.append(task_type)
    if review_status:
        conditions.append("review_status = ?")
        params.append(review_status)
    if keyword:
        conditions.append("(skill_name LIKE ? OR input_desc LIKE ? OR trigger_keywords LIKE ?)")
        kw = f"%{keyword}%"
        params.extend([kw, kw, kw])
    if min_quality > 0:
        conditions.append("quality_score >= ?")
        params.append(min_quality)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # 确保 sort_by 是安全列名
    allowed_sort = {"created_at", "quality_score", "skill_name", "review_status"}
    sort_col = sort_by if sort_by in allowed_sort else "created_at"
    order_dir = "DESC" if order.lower() == "desc" else "ASC"

    sql_count = f"SELECT COUNT(*) as cnt FROM experience_bank {where}"
    sql_data = f"SELECT * FROM experience_bank {where} ORDER BY {sort_col} {order_dir} LIMIT ? OFFSET ?"

    total = pool.fetchone(sql_count, tuple(params))["cnt"]
    rows = pool.fetchall(sql_data, tuple(params) + (limit, offset))

    skills = [_row_to_skill(dict(r)) for r in rows]
    return ApiResponse.ok({
        "total": total,
        "limit": limit,
        "offset": offset,
        "skills": skills,
    })


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str):
    """获取单个技能详情。"""
    pool = get_pool()
    row = pool.fetchone("SELECT * FROM experience_bank WHERE id = ?", (skill_id,))
    if not row:
        return ApiResponse.error(404, f"Skill not found: {skill_id}")
    return ApiResponse.ok(_row_to_skill(dict(row)))


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: str, update: SkillUpdate):
    """更新技能信息。"""
    pool = get_pool()
    existing = pool.fetchone("SELECT * FROM experience_bank WHERE id = ?", (skill_id,))
    if not existing:
        return ApiResponse.error(404, f"Skill not found: {skill_id}")

    fields = []
    params = []
    for field, col in [
        ("skill_name", "skill_name"),
        ("task_type", "task_type"),
        ("description", "input_desc"),
        ("agent_id", "agent_id"),
        ("quality_score", "quality_score"),
        ("skill_file_path", "skill_file_path"),
        ("reasoning_summary", "reasoning_summary"),
    ]:
        val = getattr(update, field, None)
        if val is not None:
            fields.append(f"{col} = ?")
            params.append(val)

    if update.trigger_keywords is not None:
        fields.append("trigger_keywords = ?")
        params.append(json.dumps(update.trigger_keywords))

    if not fields:
        return ApiResponse.ok({"status": "no_change"})

    fields.append("outcome = 'updated'")
    params.append(skill_id)

    pool.execute(
        f"UPDATE experience_bank SET {', '.join(fields)} WHERE id = ?",
        tuple(params),
    )
    logger.info(f"Skill updated: {skill_id}")
    return ApiResponse.ok({"status": "updated", "id": skill_id})


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str):
    """删除技能。"""
    pool = get_pool()
    existing = pool.fetchone("SELECT * FROM experience_bank WHERE id = ?", (skill_id,))
    if not existing:
        return ApiResponse.error(404, f"Skill not found: {skill_id}")

    pool.execute("DELETE FROM experience_bank WHERE id = ?", (skill_id,))
    logger.info(f"Skill deleted: {skill_id} — {dict(existing).get('skill_name', '')}")
    return ApiResponse.ok({"status": "deleted", "id": skill_id})


# ── 审核端点 ──


@router.put("/skills/{skill_id}/review")
async def review_skill(skill_id: str, review: SkillReview):
    """审核技能（approved / rejected）。"""
    if review.status not in ("approved", "rejected"):
        return ApiResponse.error(400, "Status must be 'approved' or 'rejected'")

    pool = get_pool()
    existing = pool.fetchone("SELECT * FROM experience_bank WHERE id = ?", (skill_id,))
    if not existing:
        return ApiResponse.error(404, f"Skill not found: {skill_id}")

    pool.execute(
        "UPDATE experience_bank SET review_status = ?, reviewed_by = ?, review_note = ? WHERE id = ?",
        (review.status, review.reviewer, review.note, skill_id),
    )
    logger.info(f"Skill reviewed: {skill_id} → {review.status}")
    return ApiResponse.ok({"status": review.status, "id": skill_id})


# ── Agent 绑定端点 ──


@router.post("/skills/{skill_id}/bind")
async def bind_skill_to_agent(skill_id: str, agent_id: str = Query(..., description="目标 Agent ID")):
    """绑定技能到指定 Agent（更新 agent_id 字段）。"""
    pool = get_pool()
    existing = pool.fetchone("SELECT * FROM experience_bank WHERE id = ?", (skill_id,))
    if not existing:
        return ApiResponse.error(404, f"Skill not found: {skill_id}")

    pool.execute(
        "UPDATE experience_bank SET agent_id = ?, outcome = 'bound' WHERE id = ?",
        (agent_id, skill_id),
    )
    logger.info(f"Skill {skill_id} bound to agent {agent_id}")
    return ApiResponse.ok({
        "status": "bound",
        "id": skill_id,
        "agent_id": agent_id,
        "skill_name": dict(existing).get("skill_name", ""),
    })


# ── 技能统计 ──


@router.get("/skills/stats/summary")
async def skill_market_stats():
    """技能市场统计概览。"""
    pool = get_pool()
    total = pool.fetchone("SELECT COUNT(*) as cnt FROM experience_bank")["cnt"]
    by_status = pool.fetchall(
        "SELECT review_status, COUNT(*) as cnt FROM experience_bank GROUP BY review_status"
    )
    by_agent = pool.fetchall(
        "SELECT agent_id, COUNT(*) as cnt FROM experience_bank WHERE agent_id != '' GROUP BY agent_id ORDER BY cnt DESC LIMIT 10"
    )
    top_quality = pool.fetchall(
        "SELECT skill_name, quality_score FROM experience_bank WHERE review_status = 'approved' ORDER BY quality_score DESC LIMIT 5"
    )

    return ApiResponse.ok({
        "total_skills": total,
        "by_review_status": {r["review_status"]: r["cnt"] for r in by_status},
        "by_agent": [{"agent_id": r["agent_id"], "count": r["cnt"]} for r in by_agent],
        "top_skills": [
            {"skill_name": r["skill_name"], "quality_score": r["quality_score"]}
            for r in top_quality
        ],
    })

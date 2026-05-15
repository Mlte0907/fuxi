"""Skill 发现 — 根据任务类型和关键词自动匹配技能"""

import json
import logging
from typing import Optional

from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.skill_market.discovery")


def discover_skills(
    task_type: str = "",
    keywords: Optional[list[str]] = None,
    agent_id: Optional[str] = None,
    min_quality: float = 0.5,
    limit: int = 5,
) -> list[dict]:
    """根据任务类型和关键词发现匹配的已审核技能。

    Args:
        task_type: 任务类型（如 debug、maintenance）
        keywords: 关键词列表（匹配 trigger_keywords）
        agent_id: 如果指定，优先返回该 agent 绑定的技能
        min_quality: 最低质量分
        limit: 返回上限

    Returns:
        技能字典列表
    """
    pool = get_pool()
    conditions = ["review_status = 'approved'", "quality_score >= ?"]
    params: list = [min_quality]

    # 任务类型精确匹配或模糊匹配
    if task_type:
        conditions.append("(task_type = ? OR task_type LIKE ?)")
        params.append(task_type)
        params.append(f"%{task_type}%")

    # 关键词匹配 trigger_keywords
    keyword_conditions = []
    if keywords:
        for kw in keywords:
            keyword_conditions.append("trigger_keywords LIKE ?")
            params.append(f"%{kw}%")
        if keyword_conditions:
            conditions.append(f"({' OR '.join(keyword_conditions)})")

    # Agent 绑定优先
    if agent_id:
        conditions.append("(agent_id = ? OR agent_id = '' OR agent_id IS NULL)")
        params.append(agent_id)

    where = " AND ".join(conditions)
    sql = (
        f"SELECT * FROM experience_bank WHERE {where} "
        f"ORDER BY "
        f"  CASE WHEN agent_id = ? THEN 100 ELSE 0 END + quality_score * 50 DESC, "
        f"  created_at DESC "
        f"LIMIT ?"
    )
    if agent_id:
        params.append(agent_id)
    else:
        params.append("")
    params.append(limit)

    try:
        rows = pool.fetchall(sql, tuple(params))
        skills = []
        for r in rows:
            d = dict(r)
            d["trigger_keywords"] = json.loads(d.get("trigger_keywords", "[]"))
            if d.get("skill_name"):
                skills.append(d)
        return skills
    except Exception as e:
        logger.warning(f"Skill discovery query failed: {e}")
        return []


def format_skills_for_prompt(skills: list[dict]) -> str:
    """将技能列表格式化为注入 prompt 的文本。"""
    if not skills:
        return ""
    parts = ["\n【相关技能参考】"]
    for s in skills:
        name = s.get("skill_name", "?")
        desc = s.get("input_desc", "") or s.get("conclusion", "") or ""
        kw = ", ".join(s.get("trigger_keywords", []))
        agent = s.get("agent_id", "") or "通用"
        summary = f"  - [{name}] ({agent}) {desc[:120]}"
        if kw:
            summary += f" 触发词: {kw}"
        parts.append(summary)
    return "\n".join(parts)

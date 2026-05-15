"""Skill 市场自动集成 — 引擎 + 快捷集成函数"""

import json
import logging

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.skill_market.discovery import discover_skills, format_skills_for_prompt
from fuxi.skill_market.submission import submit_skill
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.skill_market.integration")


def inject_skill_context(task_type: str, keywords: list[str], agent_id: str) -> str:
    """快捷函数：在任务执行前注入技能上下文。

    在 DialogueEngine 或 DecisionEngine 中调用。
    返回格式化文本，可直接拼接到 prompt 中。
    """
    skills = discover_skills(
        task_type=task_type,
        keywords=keywords,
        agent_id=agent_id,
        min_quality=0.4,
        limit=5,
    )
    return format_skills_for_prompt(skills)


def auto_submit_after_task(
    task_type: str,
    description: str,
    reasoning: str,
    outcome: str,
    result: dict,
    agent_id: str,
    auto_approve: bool = False,
) -> str:
    """快捷函数：任务完成后自动提交技能。

    在 DecisionExecutor 或 DialogueEngine 中调用。
    返回技能 ID 或空字符串。
    """
    return submit_skill(
        task_type=task_type,
        description=description,
        reasoning=reasoning,
        outcome=outcome,
        result=result,
        agent_id=agent_id,
        auto_approve=auto_approve,
    )


@register_engine("skill_market", experimental=False)
class SkillMarketEngine(CognitiveEngine):
    """技能市场自动引擎 — 定期进行自动匹配和绑定。

    功能:
    1. 将未绑定的已审核技能自动绑定到匹配的 agent
    2. 将高质量 pending 技能自动审核通过
    """
    name = "skill_market"
    priority = 3
    interval = 600  # 10 分钟
    experimental = False

    def run(self) -> dict:
        pool = get_pool()
        actions = []

        # 1. 审核高质量 pending 技能
        rows = pool.fetchall(
            "SELECT * FROM experience_bank WHERE review_status = 'pending' "
            "AND quality_score >= 0.75 ORDER BY quality_score DESC LIMIT 10"
        )
        auto_approved = 0
        for r in rows:
            d = dict(r)
            pool.execute(
                "UPDATE experience_bank SET review_status = 'approved', "
                "reviewed_by = 'system:auto', review_note = 'auto-approved (quality >= 0.75)' "
                "WHERE id = ?",
                (d["id"],),
            )
            auto_approved += 1
            logger.info(f"Skill auto-approved: {d['id'][:8]} — {d.get('skill_name', '?')}")
        if auto_approved:
            actions.append(f"auto-approved {auto_approved} skills")

        # 2. 将未绑定的已审核技能自动绑定到匹配的 agent
        rows = pool.fetchall(
            "SELECT * FROM experience_bank WHERE review_status = 'approved' "
            "AND (agent_id IS NULL OR agent_id = '') "
            "AND task_type != '' ORDER BY quality_score DESC LIMIT 10"
        )
        bound = 0
        for r in rows:
            d = dict(r)
            task_type = d.get("task_type", "")
            match = pool.fetchone(
                "SELECT agent_id, COUNT(*) as cnt FROM experience_bank "
                "WHERE task_type = ? AND agent_id != '' "
                "GROUP BY agent_id ORDER BY cnt DESC LIMIT 1",
                (task_type,),
            )
            if match and match.get("agent_id"):
                pool.execute(
                    "UPDATE experience_bank SET agent_id = ?, outcome = 'auto_bound' WHERE id = ?",
                    (match["agent_id"], d["id"]),
                )
                bound += 1
                logger.info(f"Skill auto-bound: {d['id'][:8]} → {match['agent_id']}")
        if bound:
            actions.append(f"auto-bound {bound} skills")

        # 3. 清理超低质量待审核 skills
        deleted = pool.execute(
            "DELETE FROM experience_bank WHERE review_status = 'pending' "
            "AND quality_score < 0.3 AND created_at < datetime('now', '-7 days')"
        )
        if deleted:
            actions.append(f"cleaned {deleted} low-quality skills")

        return {"status": "ok", "actions": actions} if actions else {"status": "idle"}

"""Skill 自动提交 — 任务完成后自动生成为技能"""

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Optional

from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.skill_market.submission")

# 任务类型 → 触发关键词的映射
TASK_KEYWORDS = {
    "debug": ["bug", "fix", "error", "修复", "调试", "crash", "异常"],
    "refactor": ["重构", "优化", "清理", "clean", "refactor", "简化"],
    "feature": ["新增", "实现", "添加", "功能", "feature", "开发"],
    "memory": ["记忆", "memory", "ingestion", "召回"],
    "deploy": ["部署", "发布", "deploy", "上线", "配置"],
    "security": ["安全", "权限", "注入", "加密"],
    "monitor": ["监控", "告警", "日志", "异常检测"],
    "test": ["测试", "单元测试", "集成测试", "回归"],
}


def extract_skill_name(task_type: str, input_desc: str, outcome: str) -> str:
    """从任务上下文提取技能名称。"""
    clean = outcome or input_desc or ""
    match = re.search(r"[:：]\s*(\S.{2,40}?)(?:。|；|$)", clean)
    if match:
        return match.group(1).strip()[:50]
    words = re.findall(r"[一-鿿\w]+", clean[:60])
    if words:
        return "".join(words[:6])[:50]
    return f"{task_type}_skill"


def extract_keywords(task_type: str, input_text: str) -> list[str]:
    """从上下文提取触发关键词。"""
    keywords = set()
    task_kws = TASK_KEYWORDS.get(task_type, [])
    keywords.update(task_kws)
    keywords.add(task_type)
    return sorted(keywords)[:10]


def estimate_quality(result: dict) -> float:
    """估算任务质量分数。"""
    base = 0.5
    if result.get("status") in ("ok", "success", "completed", "bound"):
        base += 0.2
    if result.get("data"):
        base += 0.1
    error = result.get("error", "")
    if not error:
        base += 0.1
    return min(base, 0.95)


def submit_skill(
    task_type: str,
    description: str = "",
    reasoning: str = "",
    outcome: str = "",
    result: Optional[dict] = None,
    agent_id: str = "",
    quality_score: Optional[float] = None,
    auto_approve: bool = False,
) -> str:
    """自动提交一个技能到市场。

    检查是否已有相似的技能存在（相同 task_type + agent_id），
    避免重复提交。

    Returns:
        技能 ID 或空字符串（已存在时）
    """
    pool = get_pool()
    result = result or {}

    # 检查是否已存在
    existing = pool.fetchone(
        "SELECT id FROM experience_bank WHERE task_type = ? AND agent_id = ? "
        "AND skill_name != '' AND skill_name IS NOT NULL "
        "ORDER BY created_at DESC LIMIT 1",
        (task_type, agent_id),
    )
    if existing:
        logger.debug(f"Skill already exists for {task_type}/{agent_id}, skipping")
        return ""

    if quality_score is None:
        quality_score = estimate_quality(result)

    skill_name = extract_skill_name(task_type, description, outcome)
    keywords = extract_keywords(task_type, description + " " + outcome)
    review = "approved" if auto_approve else "pending"

    skill_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    pool.execute(
        """INSERT INTO experience_bank
           (id, skill_name, task_type, input_desc, trigger_keywords,
            agent_id, quality_score, reasoning_summary, outcome,
            review_status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            skill_id, skill_name, task_type,
            description[:500],
            json.dumps(keywords),
            agent_id, quality_score,
            reasoning[:500],
            outcome[:200],
            review, now,
        ),
    )
    logger.info(f"Skill auto-submitted: {skill_id} — {skill_name} ({agent_id}) [{review}]")
    return skill_id

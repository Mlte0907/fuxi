"""伏羲 v1.0 — 自主决策框架

评估、选择、执行、追踪的完整决策闭环。"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class DecisionType(Enum):
    MEMORY_MANAGEMENT = "memory_management"
    ATTENTION_ALLOCATION = "attention_allocation"
    ENGINE_SCHEDULING = "engine_scheduling"
    PROACTIVE_ACTION = "proactive_action"
    COLLABORATION = "collaboration"


class DecisionStatus(Enum):
    PENDING = "pending"
    EVALUATING = "evaluating"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"


@dataclass
class DecisionOption:
    """决策选项"""
    id: str
    description: str
    action_type: str
    action_params: dict = field(default_factory=dict)
    expected_outcome: str = ""
    risk_level: float = 0.0
    cost_estimate: float = 0.0
    confidence: float = 0.0


@dataclass
class Decision:
    """决策实例"""
    id: str = ""
    decision_type: DecisionType = DecisionType.MEMORY_MANAGEMENT
    trigger_reason: str = ""
    context: dict = field(default_factory=dict)
    options: List[DecisionOption] = field(default_factory=list)
    selected_option: Optional[str] = None
    status: DecisionStatus = DecisionStatus.PENDING
    evaluation_result: Optional[dict] = None
    execution_result: Optional[dict] = None
    created_at: str = ""
    decided_at: str = ""
    completed_at: str = ""


class DecisionFramework:
    """自主决策框架 — 评估、选择、执行、追踪"""

    RISK_THRESHOLD_AUTO = 0.3
    RISK_THRESHOLD_NOTIFY = 0.6
    RISK_THRESHOLD_BLOCK = 0.8

    def evaluate_options(self, decision: Decision) -> Decision:
        """评估所有候选方案，选择最优"""
        scored_options = []
        for option in decision.options:
            score = self._score_option(option, decision.context)
            scored_options.append((option, score))

        scored_options.sort(key=lambda x: x[1], reverse=True)

        decision.evaluation_result = {
            "scores": {o.id: s for o, s in scored_options},
            "best_option": scored_options[0][0].id if scored_options else None,
            "best_score": scored_options[0][1] if scored_options else 0,
        }

        best_option = scored_options[0][0] if scored_options else None
        if best_option:
            if best_option.risk_level <= self.RISK_THRESHOLD_AUTO:
                decision.selected_option = best_option.id
                decision.status = DecisionStatus.APPROVED
            elif best_option.risk_level <= self.RISK_THRESHOLD_NOTIFY:
                decision.selected_option = best_option.id
                decision.status = DecisionStatus.PENDING
            else:
                decision.status = DecisionStatus.REJECTED

        return decision

    def _score_option(self, option: DecisionOption, context: dict) -> float:
        """综合评分 = 信心度 x 收益 - 风险 x 代价"""
        experience_bonus = self._query_experience(option.action_type)
        benefit = (
            option.confidence * 0.5
            + experience_bonus * 0.3
            + (1 - option.cost_estimate) * 0.2
        )
        risk_penalty = option.risk_level * 0.6
        context_relevance = context.get("relevance_score", 0.5) * 0.1
        return benefit - risk_penalty + context_relevance

    def _query_experience(self, action_type: str) -> float:
        """查询经验库中类似行动的历史成功率"""
        from fuxi.store.connection import get_pool

        pool = get_pool()
        try:
            row = pool.fetchone(
                "SELECT outcome, COUNT(*) AS cnt FROM experience_bank "
                "WHERE task_type LIKE ? GROUP BY outcome ORDER BY cnt DESC LIMIT 1",
                (f"%{action_type}%",)
            )
            if row and row["outcome"] == "success":
                return min(1.0, row["cnt"] / 10.0)
            return 0.2
        except Exception:
            return 0.2

"""伏羲 v1.0 — DecisionEngine 自主决策引擎

基于记忆和推理自主选择行动方案。检测需决策的情境，生成候选方案，评估并执行。"""
import json
import uuid
from datetime import datetime

from fuxi.decision.executor import DecisionExecutor
from fuxi.decision.framework import (
    Decision,
    DecisionFramework,
    DecisionOption,
    DecisionStatus,
    DecisionType,
)
from fuxi.engines.base import CognitiveEngine, register_engine


@register_engine("decision", experimental=False)
class DecisionEngine(CognitiveEngine):
    """自主决策引擎 — 基于记忆和推理自主选择行动方案"""

    name = "decision"
    priority = 8
    interval = 600  # 10分钟评估一次

    def run(self) -> dict:
        from fuxi.store.connection import get_pool

        pool = get_pool()
        decisions_made = []

        situations = self._detect_situations(pool)
        for situation in situations:
            context = self._build_context(pool, situation)
            options = self._generate_options(situation, context)
            decision = Decision(
                id=str(uuid.uuid4()),
                decision_type=situation["type"],
                trigger_reason=situation["reason"],
                context=context,
                options=options,
                created_at=datetime.now().isoformat(),
            )

            framework = DecisionFramework()
            decision = framework.evaluate_options(decision)

            if decision.status == DecisionStatus.APPROVED:
                executor = DecisionExecutor()
                result = executor.execute(decision)
                decisions_made.append({
                    "type": decision.decision_type.value,
                    "action": decision.selected_option,
                    "result": result.get("status"),
                })

            self._persist_decision(decision)

        return {
            "situations_detected": len(situations),
            "decisions_made": len(decisions_made),
            "details": decisions_made,
            "timestamp": datetime.now().isoformat(),
        }

    def _detect_situations(self, pool) -> list:
        situations = []

        # 情境1: 记忆膨胀
        count_row = pool.fetchone(
            "SELECT COUNT(*) AS cnt FROM items WHERE archived=0"
        )
        if count_row and count_row["cnt"] > 500:
            situations.append({
                "type": DecisionType.MEMORY_MANAGEMENT,
                "reason": f"记忆膨胀: {count_row['cnt']} 条活跃记忆",
                "severity": "medium",
            })

        # 情境2: 高重要性记忆过期
        stale = pool.fetchone(
            "SELECT COUNT(*) AS cnt FROM items WHERE archived=0 "
            "AND importance > 0.7 AND updated_at < datetime('now','-14 days')"
        )
        if stale and stale["cnt"] > 5:
            situations.append({
                "type": DecisionType.PROACTIVE_ACTION,
                "reason": f"{stale['cnt']} 条高重要性记忆超过14天未更新",
                "severity": "high",
            })

        # 情境3: 图谱稀疏
        density_row = pool.fetchone(
            "SELECT (SELECT COUNT(*) FROM edges) * 1.0 / "
            "(SELECT MAX(1, COUNT(*)) FROM items WHERE archived=0) AS density"
        )
        if density_row and density_row["density"] < 0.5:
            situations.append({
                "type": DecisionType.ENGINE_SCHEDULING,
                "reason": f"图谱连接密度过低: {density_row['density']:.2f}",
                "severity": "low",
            })

        # 情境4: 工作记忆溢出
        try:
            from fuxi.kernel.working_memory import get_working_memory
            wm = get_working_memory()
            if wm.stats.get("evictions", 0) > 20:
                situations.append({
                    "type": DecisionType.ATTENTION_ALLOCATION,
                    "reason": f"工作记忆频繁淘汰: {wm.stats['evictions']} 次",
                    "severity": "medium",
                })
        except Exception:
            pass

        return situations

    def _build_context(self, pool, situation: dict) -> dict:
        from fuxi.memory.retrieval import recall
        related = recall(query=situation["reason"], limit=5)

        experiences = pool.fetchall(
            "SELECT task_type, conclusion, outcome FROM experience_bank "
            "ORDER BY created_at DESC LIMIT 10"
        )

        try:
            from fuxi.kernel.attention import get_attention_system
            attention = get_attention_system()
            attn_strategy = attention.active_strategy.value
            attn_budget = attention.budget
        except Exception:
            attn_strategy = "bottom_up"
            attn_budget = 0.5

        return {
            "situation": situation,
            "related_memories": len(related),
            "relevant_experiences": len(experiences),
            "attention_strategy": attn_strategy,
            "attention_budget": attn_budget,
            "relevance_score": 0.7,
        }

    def _generate_options(self, situation: dict, context: dict) -> list:
        options = []

        if situation["type"] == DecisionType.MEMORY_MANAGEMENT:
            options.extend([
                DecisionOption(
                    id="cleanup_low_value",
                    description="清理低衰减分记忆",
                    action_type="memory_cleanup",
                    risk_level=0.2,
                    cost_estimate=0.3,
                    confidence=0.8,
                ),
                DecisionOption(
                    id="distill_compress",
                    description="蒸馏压缩高频记忆",
                    action_type="engine_priority_adjust",
                    action_params={"engine": "distill", "priority": 8},
                    risk_level=0.1,
                    cost_estimate=0.2,
                    confidence=0.7,
                ),
            ])

        elif situation["type"] == DecisionType.PROACTIVE_ACTION:
            options.extend([
                DecisionOption(
                    id="notify_user",
                    description="通知用户关注过期记忆",
                    action_type="proactive_notify",
                    action_params={"message": situation["reason"], "importance": 0.7},
                    risk_level=0.05,
                    cost_estimate=0.1,
                    confidence=0.9,
                ),
                DecisionOption(
                    id="delegate_to_agent",
                    description="委派Agent复查",
                    action_type="agent_delegate",
                    action_params={
                        "agent_id": "qinglong",
                        "message": situation["reason"],
                    },
                    risk_level=0.3,
                    cost_estimate=0.5,
                    confidence=0.6,
                ),
            ])

        elif situation["type"] == DecisionType.ATTENTION_ALLOCATION:
            options.extend([
                DecisionOption(
                    id="expand_wm",
                    description="扩大工作记忆容量",
                    action_type="attention_reallocate",
                    action_params={"strategy": "explore"},
                    risk_level=0.1,
                    cost_estimate=0.2,
                    confidence=0.7,
                ),
            ])

        elif situation["type"] == DecisionType.ENGINE_SCHEDULING:
            options.extend([
                DecisionOption(
                    id="boost_dream",
                    description="提升梦境引擎优先级",
                    action_type="engine_priority_adjust",
                    action_params={"engine": "dream", "priority": 9},
                    risk_level=0.1,
                    cost_estimate=0.3,
                    confidence=0.8,
                ),
                DecisionOption(
                    id="boost_resonance",
                    description="提升共鸣引擎优先级",
                    action_type="engine_priority_adjust",
                    action_params={"engine": "resonance", "priority": 8},
                    risk_level=0.1,
                    cost_estimate=0.2,
                    confidence=0.7,
                ),
            ])

        return options

    def _persist_decision(self, decision: Decision):
        from fuxi.store.write_queue import get_write_queue
        get_write_queue().enqueue(
            "INSERT INTO event_log (event_type, source, event_data, created_at) "
            "VALUES (?,?,?,?)",
            ("decision", "engine:decision",
             json.dumps({
                 "id": decision.id,
                 "type": decision.decision_type.value,
                 "reason": decision.trigger_reason,
                 "selected": decision.selected_option,
                 "status": decision.status.value,
             }, ensure_ascii=False),
             datetime.now().isoformat())
        )

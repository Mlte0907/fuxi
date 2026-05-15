"""伏羲 v1.5 — PredictiveWorldModel 预测性世界模型

纯大脑能力：基于因果图和记忆库，从当前系统状态推演可能的未来情景。
不执行任何实际行动，只输出预测和预案。
"""
import hashlib
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np

from fuxi.engines.base import CognitiveEngine, get_engine_registry, register_engine
from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.world_model")

FORECAST_HORIZON = 3
MIN_PROBABILITY = 0.05
TOP_SCENARIOS = 10


@dataclass
class Scenario:
    id: str
    trigger: str
    description: str
    probability: float
    causal_path: List[str] = field(default_factory=list)
    severity: float = 0.5
    estimated_impact: str = ""
    suggested_actions: List[dict] = field(default_factory=list)
    matched: bool = False

    def hash_key(self) -> str:
        return hashlib.md5(self.trigger.encode()).hexdigest()[:12]


@dataclass
class Plan:
    scenario_id: str
    description: str
    suggested_actions: List[dict] = field(default_factory=list)
    estimated_effect: str = ""


@register_engine("world_model", experimental=False)
class PredictiveWorldModel(CognitiveEngine):
    """预测性世界模型 v1.5 — 纯大脑的预测推理

    基于因果图 DAG、情感状态、记忆趋势、引擎健康状况，
    从当前状态出发，推演未来 N 步的可能情景。
    生成预案后通过事件总线发布，由手脚自行决定是否采用。
    """
    name = "world_model"
    priority = 7
    interval = 300

    def __init__(self):
        super().__init__()
        self._scenario_cache: Dict[str, List[Scenario]] = {}
        self._prediction_history: List[dict] = []
        self._bayesian_weights: Dict[str, float] = {}
        self._plan_cache: Dict[str, Plan] = {}

    def _get_subscriptions(self):
        return {
            "emotion.quadrant_changed": self._on_event,
            "emotion.frustration": self._on_event,
            "soul.health_changed": self._on_event,
            "engine.executed": self._on_event,
        }

    def run(self) -> dict:
        pool = get_pool()

        current_state = self._snapshot_current_state(pool)
        scenarios = self._forecast(current_state)

        plans = []
        for s in scenarios:
            if s.probability * s.severity > 0.3:
                plan = self._generate_plan(s)
                plans.append(plan)
                self._plan_cache[plan.scenario_id] = plan

        if scenarios:
            self._publish_forecast(scenarios[:TOP_SCENARIOS], plans)

        pending = self._pop_pending_events()
        for evt in pending:
            self._match_event(pool, evt)

        state = {
            "scenarios_generated": len(scenarios),
            "top_scenarios": [
                {
                    "trigger": s.trigger[:80],
                    "probability": round(s.probability, 3),
                    "severity": round(s.severity, 3),
                    "causal_depth": len(s.causal_path),
                }
                for s in scenarios[:TOP_SCENARIOS]
            ],
            "plans_generated": len(plans),
            "prediction_history_size": len(self._prediction_history),
            "cached_scenarios": sum(len(v) for v in self._scenario_cache.values()),
            "v": "1.5",
            "timestamp": datetime.now().isoformat(),
        }

        try:
            with pool.connection() as c:
                c.execute(
                    "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
                    "VALUES (?,?,?)",
                    ("world_model", json.dumps(state, ensure_ascii=False),
                     datetime.now().isoformat())
                )
        except Exception:
            pass

        self._state.metadata["world_model_state"] = state
        return state

    def _snapshot_current_state(self, pool) -> dict:
        state = {
            "timestamp": datetime.now().isoformat(),
            "engine_health": {},
            "emotion": {},
            "recent_failures": [],
            "recent_events": [],
            "memory_trends": [],
        }

        try:
            registry = get_engine_registry()
            for name, eng in registry.engines.items():
                h = eng.health_check()
                state["engine_health"][name] = {
                    "error_count": h["error_count"],
                    "run_count": h["run_count"],
                    "running": h["running"],
                }
        except Exception:
            pass

        try:
            row = pool.fetchone(
                "SELECT state_json FROM engine_states WHERE engine_name='emotion' "
                "ORDER BY updated_at DESC LIMIT 1"
            )
            if row:
                es = json.loads(row["state_json"])
                state["emotion"] = {
                    "valence": es.get("valence", 0.0),
                    "arousal": es.get("arousal", 0.0),
                    "frustration": es.get("frustration", 0.0),
                    "trend_label": es.get("trend_label", "stable"),
                }
        except Exception:
            pass

        try:
            failures = pool.fetchall(
                "SELECT event_type, event_data, created_at FROM event_log "
                "WHERE event_type IN ('error', 'warning', 'failure') "
                "AND created_at > datetime('now', '-6 hours') "
                "ORDER BY created_at DESC LIMIT 20"
            )
            state["recent_failures"] = [
                {"type": f["event_type"], "ts": f["created_at"]}
                for f in failures
            ]
        except Exception:
            pass

        try:
            trends = pool.fetchall(
                "SELECT drawer_id, COUNT(*) as cnt, AVG(importance) as avg_imp "
                "FROM items WHERE archived=0 AND created_at > datetime('now', '-1 day') "
                "GROUP BY drawer_id ORDER BY cnt DESC"
            )
            state["memory_trends"] = [
                {"drawer": t["drawer_id"], "count": t["cnt"],
                 "avg_importance": round(t["avg_imp"], 3) if t["avg_imp"] else 0}
                for t in trends
            ]
        except Exception:
            pass

        return state

    def _forecast(self, current_state: dict) -> List[Scenario]:
        state_hash = self._hash_state(current_state)
        if state_hash in self._scenario_cache:
            return self._scenario_cache[state_hash]

        scenarios = []

        try:
            registry = get_engine_registry()
            causal_eng = registry.get("causal")
            if causal_eng:
                causal_result = causal_eng._state.metadata.get("last_run", {})
                graph_nodes = causal_result.get("graph_nodes", 0)
            else:
                graph_nodes = 0
        except Exception:
            graph_nodes = 0

        scenarios.extend(self._forecast_failure_cascade(current_state, graph_nodes))
        scenarios.extend(self._forecast_emotional_spiral(current_state))
        scenarios.extend(self._forecast_resource_pressure(current_state))
        scenarios.extend(self._forecast_pattern_repeat(current_state))

        scenarios.sort(key=lambda s: s.probability * s.severity, reverse=True)

        self._scenario_cache[state_hash] = scenarios
        if len(self._scenario_cache) > 50:
            oldest = next(iter(self._scenario_cache))
            del self._scenario_cache[oldest]

        return scenarios[:TOP_SCENARIOS * 2]

    def _forecast_failure_cascade(self, state: dict, graph_nodes: int) -> List[Scenario]:
        scenarios = []
        engine_health = state.get("engine_health", {})
        failing = {n: h for n, h in engine_health.items()
                   if h.get("error_count", 0) > 3}

        for eng_name in failing:
            prob = min(0.85, failing[eng_name].get("error_count", 0) * 0.1)

            dependent_engines = []
            try:
                causal_eng = get_engine_registry().get("causal")
                if causal_eng:
                    graph = causal_eng._build_causal_graph(get_pool()) if hasattr(causal_eng, '_build_causal_graph') else None
                    if graph:
                        dependent_engines = graph.get_children(eng_name)
            except Exception:
                pass

            if dependent_engines:
                prob *= min(1.0, len(dependent_engines) * 0.3)

            scenarios.append(Scenario(
                id=f"fc_{eng_name}",
                trigger=f"引擎 {eng_name} 持续高错误率",
                description=f"引擎 {eng_name} 错误数{failing[eng_name]['error_count']}，"
                           f"可能级联影响到 {', '.join(dependent_engines[:3]) or '其他引擎'}",
                probability=round(prob, 3),
                causal_path=[f"{eng_name}_failure", "dependent_engines_degraded",
                            "system_performance_drop"],
                severity=min(0.9, 0.3 + len(dependent_engines) * 0.15),
                estimated_impact=f"预计影响 {len(dependent_engines) or '多个'} 依赖引擎",
                suggested_actions=[
                    {"target": "openclaw", "type": "check_engine_health",
                     "engine": eng_name},
                ],
            ))

        return scenarios

    def _forecast_emotional_spiral(self, state: dict) -> List[Scenario]:
        scenarios = []
        emotion = state.get("emotion", {})
        valence = emotion.get("valence", 0.0)
        frustration = emotion.get("frustration", 0.0)
        trend = emotion.get("trend_label", "stable")

        if trend == "declining" and valence < -0.3:
            prob = 0.55 + abs(valence) * 0.3
            scenarios.append(Scenario(
                id="es_decline",
                trigger="情感持续走低",
                description=f"效价{valence:.2f}已连续下行，"
                           f"焦虑模式可能激活保守决策",
                probability=round(min(0.85, prob), 3),
                causal_path=["negative_memory_accumulation", "valence_decline",
                            "conservative_decision_mode"],
                severity=0.6,
                estimated_impact="决策趋于保守，主动探索减少",
                suggested_actions=[
                    {"target": "openclaw", "type": "raise_self_reflection"},
                ],
            ))

        if frustration > 0.5:
            prob = 0.4 + frustration * 0.4
            scenarios.append(Scenario(
                id="es_frustration",
                trigger="高受挫信号",
                description=f"frustration={frustration:.2f}，"
                           f"可能出现目标放弃或重复尝试",
                probability=round(min(0.85, prob), 3),
                causal_path=["goal_blocked", "frustration_rise",
                            "potential_abandonment"],
                severity=0.55,
                estimated_impact="目标达成受阻，需手脚介入调整策略",
                suggested_actions=[
                    {"target": "openclaw", "type": "review_goals"},
                ],
            ))

        return scenarios

    def _forecast_resource_pressure(self, state: dict) -> List[Scenario]:
        scenarios = []
        failures = state.get("recent_failures", [])

        if len(failures) > 10:
            prob = min(0.85, 0.3 + len(failures) * 0.03)
            scenarios.append(Scenario(
                id="rp_high_failures",
                trigger=f"近6小时 {len(failures)} 次错误/警告",
                description="系统错误频率显著升高，可能出现资源压力",
                probability=round(prob, 3),
                causal_path=["high_error_rate", "resource_pressure",
                            "potential_crash"],
                severity=0.7,
                estimated_impact="系统稳定性下降",
                suggested_actions=[
                    {"target": "openclaw", "type": "system_health_check"},
                ],
            ))

        return scenarios

    def _forecast_pattern_repeat(self, state: dict) -> List[Scenario]:
        scenarios = []
        try:
            pool = get_pool()
            row = pool.fetchone(
                "SELECT COUNT(*) as cnt FROM event_log "
                "WHERE event_type = 'error' "
                "AND created_at > datetime('now', '-2 days')"
            )
            if row and row["cnt"] > 20:
                prob = min(0.8, 0.3 + row["cnt"] * 0.015)
                scenarios.append(Scenario(
                    id="pr_repeat",
                    trigger="错误模式复现",
                    description=f"过去2天 {row['cnt']} 次错误，存在重复模式",
                    probability=round(prob, 3),
                    causal_path=["recurring_error", "pattern_repeat",
                                "unresolved_root_cause"],
                    severity=0.5,
                    estimated_impact="未解决根源持续产生错误",
                    suggested_actions=[
                        {"target": "openclaw", "type": "root_cause_analysis"},
                    ],
                ))
        except Exception:
            pass

        return scenarios

    def _generate_plan(self, scenario: Scenario) -> Plan:
        return Plan(
            scenario_id=scenario.id,
            description=f"如果检测到 [{scenario.trigger}]，建议:",
            suggested_actions=scenario.suggested_actions,
            estimated_effect=scenario.estimated_impact,
        )

    def _publish_forecast(self, scenarios: List[Scenario], plans: List[Plan]):
        get_event_bus().publish(Event(
            type="brain.forecast",
            data={
                "scenarios": [
                    {
                        "id": s.id,
                        "trigger": s.trigger,
                        "probability": s.probability,
                        "severity": s.severity,
                        "causal_path": s.causal_path,
                    }
                    for s in scenarios
                ],
                "plans": [
                    {
                        "scenario_id": p.scenario_id,
                        "description": p.description,
                        "actions": p.suggested_actions,
                    }
                    for p in plans
                ],
                "timestamp": datetime.now().isoformat(),
            },
            priority=EventPriority.NORMAL,
            source="engine:world_model",
        ))

    def _match_event(self, pool, evt: dict) -> Optional[Scenario]:
        evt_type = evt.get("type", "")
        evt_data = evt.get("data", {})

        for scenarios in list(self._scenario_cache.values()):
            for s in scenarios:
                if s.matched:
                    continue
                trigger_match = False

                if "failure" in evt_type.lower() or "error" in evt_type.lower():
                    engine_name = evt_data.get("engine", "")
                    if engine_name and engine_name in s.trigger:
                        trigger_match = True

                if "emotion" in evt_type and ("declining" in str(evt_data) or
                                              "frustration" in str(evt_data)):
                    trigger_match = True

                if trigger_match:
                    s.matched = True
                    logger.info(f"预判命中: {s.trigger} → 预案已就绪 (prob={s.probability:.2f})")

                    get_event_bus().publish(Event(
                        type="brain.forecast_matched",
                        data={
                            "scenario_id": s.id,
                            "trigger": s.trigger,
                            "probability": s.probability,
                            "suggested_actions": s.suggested_actions,
                        },
                        priority=EventPriority.HIGH,
                        source="engine:world_model",
                    ))

                    self._learn_from_match(s)
                    return s

        return None

    def _learn_from_match(self, matched: Scenario):
        path_key = "→".join(matched.causal_path)
        current = self._bayesian_weights.get(path_key, 0.5)
        self._bayesian_weights[path_key] = min(1.0, current + 0.1)

        self._prediction_history.append({
            "ts": datetime.now().isoformat(),
            "predicted": matched.trigger,
            "probability": matched.probability,
            "outcome": "matched",
        })

    def _hash_state(self, state: dict) -> str:
        key_parts = [
            str(len(state.get("recent_failures", []))),
            str(state.get("emotion", {}).get("valence", 0)),
            str(state.get("emotion", {}).get("frustration", 0)),
        ]
        for eng, h in sorted(state.get("engine_health", {}).items()):
            if h.get("error_count", 0) > 2:
                key_parts.append(f"{eng}:{h['error_count']}")
        return hashlib.md5("|".join(key_parts).encode()).hexdigest()[:16]
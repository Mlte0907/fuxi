"""伏羲 v1.5 — ArchAuditor 认知架构自审视

纯大脑能力：审计自身认知架构的效率，发现瓶颈和覆盖缺口。
输出分析报告，不做自动变更。最终决策和部署由人类负责。
"""
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from fuxi.engines.base import CognitiveEngine, get_engine_registry, register_engine
from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.arch_auditor")


@dataclass
class EngineRank:
    name: str
    efficiency: float
    run_count: int
    useful_outputs: int
    failure_rate: float


@dataclass
class ContextGap:
    context_type: str
    frequency: int
    description: str


@dataclass
class RedundancyAlert:
    engine_a: str
    engine_b: str
    overlap_score: float
    description: str


@register_engine("arch_auditor", experimental=False)
class ArchAuditor(CognitiveEngine):
    """认知架构自审视 v1.5

    分析大脑自身的工作效率：哪些引擎低效？哪些情境无引擎覆盖？
    哪些引擎在重复劳动？生成审计报告，不自动修改配置。
    """
    name = "arch_auditor"
    priority = 3
    interval = 1800

    def _get_subscriptions(self):
        return {"engine.executed": self._on_event}

    def run(self) -> dict:
        pool = get_pool()

        rankings = self._rank_engines_by_efficiency(pool)
        context_gaps = self._find_uncovered_contexts(pool)
        redundancy_alerts = self._detect_redundancy()
        recommendations = self._generate_recommendations(
            rankings, context_gaps, redundancy_alerts
        )

        state = {
            "engine_rankings": [
                {
                    "name": r.name,
                    "efficiency": round(r.efficiency, 3),
                    "run_count": r.run_count,
                    "failure_rate": round(r.failure_rate, 3),
                }
                for r in rankings[:10]
            ],
            "context_gaps": [
                {"context_type": g.context_type, "frequency": g.frequency}
                for g in context_gaps[:5]
            ],
            "redundancy_alerts": [
                {"a": ra.engine_a, "b": ra.engine_b,
                 "overlap": round(ra.overlap_score, 3)}
                for ra in redundancy_alerts[:5]
            ],
            "recommendations": recommendations[:10],
            "overall_health": self._assess_overall(rankings, len(context_gaps)),
            "v": "1.5",
            "timestamp": datetime.now().isoformat(),
        }

        try:
            with pool.connection() as c:
                c.execute(
                    "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
                    "VALUES (?,?,?)",
                    ("arch_auditor", json.dumps(state, ensure_ascii=False),
                     datetime.now().isoformat())
                )
        except Exception:
            pass

        if recommendations:
            get_event_bus().publish(Event(
                type="brain.audit_report",
                data={
                    "recommendations": recommendations[:5],
                    "overall_health": state["overall_health"],
                },
                priority=EventPriority.LOW,
                source="engine:arch_auditor",
            ))

            try:
                from fuxi.memory.ingestion import remember
                remember(
                    raw_text=f"[架构审计] {state['overall_health']} — "
                             f"{len(recommendations)}项建议",
                    drawer_id="longterm",
                    importance=0.3,
                    source="self",
                    confidence=0.7,
                    created_by="arch_auditor",
                    tags=["架构审计", "architecture_audit"],
                )
            except Exception as e:
                logger.debug(f"Auditor memory write failed: {e}")

        self._state.metadata["audit_state"] = state
        return state

    def _rank_engines_by_efficiency(self, pool) -> List[EngineRank]:
        rankings = []
        registry = get_engine_registry()

        for name, eng in registry.engines.items():
            health = eng.health_check()
            run_count = health.get("run_count", 0)
            error_count = health.get("error_count", 0)

            if run_count < 5:
                continue

            failure_rate = error_count / max(run_count, 1)

            useful_outputs = 0
            try:
                row = pool.fetchone(
                    "SELECT COUNT(*) as cnt FROM event_log "
                    "WHERE event_type = 'engine.executed' "
                    "AND json_extract(event_data, '$.engine') = ? "
                    "AND json_extract(event_data, '$.status') = 'ok'",
                    (name,)
                )
                useful_outputs = row["cnt"] if row else 0
            except Exception:
                useful_outputs = run_count - error_count

            efficiency = useful_outputs / (run_count + 1) if run_count > 0 else 0

            rankings.append(EngineRank(
                name=name,
                efficiency=efficiency,
                run_count=run_count,
                useful_outputs=useful_outputs,
                failure_rate=failure_rate,
            ))

        return sorted(rankings, key=lambda r: r.efficiency)

    def _find_uncovered_contexts(self, pool) -> List[ContextGap]:
        gaps = []
        try:
            rows = pool.fetchall(
                "SELECT drawer_id, COUNT(*) as cnt FROM items "
                "WHERE archived=0 GROUP BY drawer_id ORDER BY cnt DESC"
            )
            all_drawers = set(r["drawer_id"] for r in rows)

            engine_subscriptions = set()
            registry = get_engine_registry()
            for name, eng in registry.engines.items():
                try:
                    subs = eng._get_subscriptions()
                    engine_subscriptions.update(subs.keys())
                except Exception:
                    pass

            for drawer in all_drawers:
                if drawer not in engine_subscriptions and drawer != "default":
                    cnt = next((r["cnt"] for r in rows if r["drawer_id"] == drawer), 0)
                    if cnt > 10:
                        gaps.append(ContextGap(
                            context_type=drawer,
                            frequency=cnt,
                            description=f"抽屉 [{drawer}] 有 {cnt} 条记忆但无引擎订阅",
                        ))
        except Exception:
            pass
        return sorted(gaps, key=lambda g: g.frequency, reverse=True)

    def _detect_redundancy(self) -> List[RedundancyAlert]:
        alerts = []
        registry = get_engine_registry()

        pairs_checked = set()
        for name_a in registry.engines:
            for name_b in registry.engines:
                if name_a >= name_b:
                    continue
                pair_key = tuple(sorted([name_a, name_b]))
                if pair_key in pairs_checked:
                    continue
                pairs_checked.add(pair_key)

                interval_a = registry.engines[name_a].interval
                interval_b = registry.engines[name_b].interval

                if abs(interval_a - interval_b) < 10:
                    try:
                        subs_a = set(registry.engines[name_a]._get_subscriptions().keys())
                        subs_b = set(registry.engines[name_b]._get_subscriptions().keys())
                        common = subs_a & subs_b
                        if common:
                            overlap = len(common) / max(len(subs_a | subs_b), 1)
                            if overlap > 0.5:
                                alerts.append(RedundancyAlert(
                                    engine_a=name_a,
                                    engine_b=name_b,
                                    overlap_score=overlap,
                                    description=f"[{name_a}]和[{name_b}]订阅重叠{overlap:.0%}",
                                ))
                    except Exception:
                        pass

        return sorted(alerts, key=lambda ra: ra.overlap_score, reverse=True)

    def _generate_recommendations(self, rankings: List[EngineRank],
                                   gaps: List[ContextGap],
                                   redundancies: List[RedundancyAlert]) -> List[str]:
        recs = []

        for r in rankings:
            if r.efficiency < 0.1 and r.run_count > 50:
                recs.append(
                    f"[效率] 引擎 [{r.name}] 效率={r.efficiency:.3f}，"
                    f"运行{r.run_count}次，失败率{r.failure_rate:.1%}，建议降低优先级或审查"
                )
            elif r.failure_rate > 0.3 and r.run_count > 10:
                recs.append(
                    f"[可靠性] 引擎 [{r.name}] 失败率{r.failure_rate:.1%}，"
                    f"需关注稳定性"
                )

        for g in gaps[:3]:
            recs.append(
                f"[覆盖缺口] 情境 [{g.context_type}] 出现{g.frequency}次但无引擎覆盖，"
                f"建议增加对应引擎或扩展已有引擎范围"
            )

        for ra in redundancies[:3]:
            recs.append(
                f"[冗余] [{ra.engine_a}]和[{ra.engine_b}]订阅重叠"
                f"{ra.overlap_score:.0%}，建议审查是否可合并"
            )

        if not recs:
            recs.append("[健康] 当前认知架构运行正常，无显著问题")

        return recs

    def _assess_overall(self, rankings: List[EngineRank], gap_count: int) -> str:
        if not rankings:
            return "unknown"

        low_eff = sum(1 for r in rankings if r.efficiency < 0.1)
        high_fail = sum(1 for r in rankings if r.failure_rate > 0.3)

        if low_eff > len(rankings) * 0.3:
            return "needs_attention"
        if high_fail > 3:
            return "degraded"
        if gap_count > 5:
            return "gaps_present"
        return "healthy"
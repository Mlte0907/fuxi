"""伏羲 v2.0 — PredictionEngine 预测预取 + 趋势分析"""
import json
import logging
from datetime import datetime
from typing import List, Optional

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.prediction")


@register_engine("prediction", experimental=False)
class PredictionEngine(CognitiveEngine):
    """预测预取 v2.0 — 基于历史模式预判下一步需要什么记忆，结合世界模型情景"""
    name = "prediction"
    priority = 7
    interval = 300

    def _get_subscriptions(self):
        return {"brain.forecast": self._on_forecast}

    def _on_forecast(self, event: Event):
        pending = self._state.metadata.setdefault("_pending_forecasts", [])
        pending.append(event.data)
        if len(pending) > 10:
            pending.pop(0)

    def run(self) -> dict:
        pool = get_pool()

        recent_views = pool.fetchall(
            "SELECT item_id, COUNT(*) as view_count FROM agent_views "
            "GROUP BY item_id ORDER BY view_count DESC LIMIT 10"
        )

        predictions = []
        for r in recent_views:
            related = pool.fetchall(
                "SELECT i.id, SUBSTR(i.raw_text,1,80) AS preview, i.importance FROM items i "
                "JOIN agent_views av ON av.item_id = i.id "
                "WHERE i.id != ? AND i.archived = 0 AND i.importance > 0.6 "
                "ORDER BY i.importance DESC LIMIT 5",
                (r["item_id"],)
            )
            if related:
                predictions.append({
                    "trigger_id": r["item_id"],
                    "view_count": r["view_count"],
                    "predicted": [
                        {"id": x["id"][:8], "preview": x["preview"]}
                        for x in related
                    ]
                })

        hot_topics = pool.fetchall(
            "SELECT SUBSTR(raw_text, 1, 30) AS topic, COUNT(*) AS cnt "
            "FROM items WHERE archived=0 AND created_at > datetime('now','-1 day') "
            "GROUP BY topic ORDER BY cnt DESC LIMIT 5"
        )

        # v2.0: 趋势分析
        trends = self._analyze_trends(pool)

        # v2.0: 结合世界模型预测进行记忆预取
        pending_forecasts = self._state.metadata.pop("_pending_forecasts", [])
        scenario_prefetch = []
        for fc in pending_forecasts:
            for s in fc.get("scenarios", [])[:3]:
                if s.get("probability", 0) > 0.5:
                    related_mem = self._prefetch_for_scenario(pool, s)
                    scenario_prefetch.extend(related_mem)

        state = {
            "predictions": predictions[:5],
            "hot_topics": [{"topic": t["topic"], "count": t["cnt"]} for t in hot_topics],
            "trends": trends,
            "scenario_prefetch": scenario_prefetch[:10],
            "v": "2.0",
            "timestamp": datetime.now().isoformat(),
        }

        with pool.connection() as c:
            c.execute(
                "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
                "VALUES (?,?,?)",
                ("prediction", json.dumps(state, ensure_ascii=False), datetime.now().isoformat())
            )

        self._state.metadata["last_prediction"] = state
        return state

    def _analyze_trends(self, pool) -> dict:
        trends = {}

        try:
            row = pool.fetchone(
                "SELECT COUNT(*) as cnt FROM items "
                "WHERE archived=0 AND created_at > datetime('now', '-1 hour')"
            )
            hourly = row["cnt"] if row else 0

            row = pool.fetchone(
                "SELECT COUNT(*) as cnt FROM items "
                "WHERE archived=0 AND created_at > datetime('now', '-2 hours') "
                "AND created_at <= datetime('now', '-1 hour')"
            )
            prev_hourly = row["cnt"] if row else 0

            if prev_hourly > 0:
                trends["ingestion_rate"] = round(hourly / prev_hourly, 3)
            else:
                trends["ingestion_rate"] = 1.0
        except Exception:
            trends["ingestion_rate"] = 1.0

        try:
            row = pool.fetchone(
                "SELECT AVG(importance) as avg_imp FROM items "
                "WHERE archived=0 AND created_at > datetime('now', '-1 day')"
            )
            trends["avg_importance_24h"] = round(row["avg_imp"], 3) if row and row["avg_imp"] else 0.5
        except Exception:
            trends["avg_importance_24h"] = 0.5

        try:
            rows = pool.fetchall(
                "SELECT drawer_id, COUNT(*) as cnt FROM items "
                "WHERE archived=0 AND created_at > datetime('now', '-1 day') "
                "GROUP BY drawer_id ORDER BY cnt DESC LIMIT 3"
            )
            trends["top_drawers"] = [
                {"drawer": r["drawer_id"], "count": r["cnt"]} for r in rows
            ]
        except Exception:
            trends["top_drawers"] = []

        return trends

    def _prefetch_for_scenario(self, pool, scenario: dict) -> List[dict]:
        trigger = scenario.get("trigger", "")
        if not trigger:
            return []

        try:
            keywords = trigger.split()
            clauses = []
            params = []
            for kw in keywords[:3]:
                if len(kw) > 2:
                    clauses.append("raw_text LIKE ?")
                    params.append(f"%{kw}%")

            if not clauses:
                return []

            rows = pool.fetchall(
                f"SELECT id, SUBSTR(raw_text,1,60) AS preview, importance "
                f"FROM items WHERE archived=0 AND ({' OR '.join(clauses)}) "
                f"ORDER BY importance DESC LIMIT 3",
                params,
            )
            return [
                {"id": r["id"][:8], "preview": r["preview"],
                 "importance": r["importance"]}
                for r in rows
            ]
        except Exception:
            return []
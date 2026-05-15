"""伏羲 v1.0 — ProactiveEngine 主动洞察"""
import logging
from datetime import datetime

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.proactive")


@register_engine("proactive", experimental=False)
class ProactiveEngine(CognitiveEngine):
    """主动洞察 — 基于记忆模式主动生成提醒和建议，向瑾岚阁推送"""
    name = "proactive"
    priority = 4
    interval = 600
    experimental = False

    def run(self) -> dict:
        pool = get_pool()

        # 检测重复出现的模式
        patterns = pool.fetchall(
            "SELECT drawer_id, COUNT(*) AS cnt, AVG(importance) AS avg_imp "
            "FROM items WHERE archived=0 "
            "AND created_at > datetime('now','-7 days') "
            "GROUP BY drawer_id ORDER BY cnt DESC"
        )

        # 检测长期未更新的高重要性记忆
        stale = pool.fetchall(
            "SELECT id, SUBSTR(raw_text,1,60) AS preview, importance, updated_at "
            "FROM items WHERE archived=0 AND importance > 0.7 "
            "AND updated_at < datetime('now','-30 days') "
            "ORDER BY importance DESC LIMIT 5"
        )

        insights = []
        if stale:
            insights.append({
                "type": "stale_important",
                "message": f"{len(stale)} high-importance memories not updated for 30+ days",
            })

        if patterns and len(patterns) > 3:
            top_drawer = patterns[0]
            insights.append({
                "type": "trending_drawer",
                "message": f"Drawer '{top_drawer['drawer_id']}' is trending with {top_drawer['cnt']} items",
            })

        state = {
            "insights": insights,
            "top_drawers": [{"drawer": p["drawer_id"], "count": p["cnt"]} for p in patterns[:5]],
            "stale_count": len(stale),
            "timestamp": datetime.now().isoformat(),
        }

        self._state.metadata["last_insight"] = state

        # 发布事件到 EventBus
        for insight in insights:
            get_event_bus().publish(Event(
                type="proactive.insight",
                data=insight,
                priority=EventPriority.NORMAL,
                source="engine:proactive",
            ))

        # 主动向瑾岚阁 Agent 广播可操作的提醒
        if stale:
            try:
                from fuxi.memory.ingestion import remember
                for s in stale[:2]:
                    remember(
                        raw_text=f"[主动提醒] 高重要性记忆超过30天未更新: '{s['preview']}' (重要性{s['importance']:.0%})",
                        drawer_id="longterm",
                        importance=0.6,
                        source="self",
                        confidence=0.8,
                        created_by="proactive",
                        tags=["提醒", "proactive"],
                    )
                logger.info(f"Proactive: pushed {min(len(stale), 2)} stale-memory alerts")
            except Exception as e:
                logger.debug(f"Proactive alert write failed: {e}")

        # 推送紧迫提醒到工作记忆
        from fuxi.kernel.working_memory import WMItem, get_working_memory
        for insight in insights[:2]:
            get_working_memory().push(WMItem(
                id=f"proactive:{insight['type']}:{datetime.now().strftime('%H%M%S')}",
                content=insight["message"],
                source="engine:proactive",
                emotional_valence=-0.2,
                urgency=0.6,
                tokens=15,
            ))

        return state

"""伏羲 v1.5 — CuriosityEngine 好奇心探索（身份驱动基础框架）"""
import logging
from datetime import datetime

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.curiosity")

# v1.5: 好奇心激活阈值（情感效价极端时好奇心更强）
CURIOSITY_ACTIVATION_THRESHOLD = 0.5


@register_engine("curiosity", experimental=False)
class CuriosityEngine(CognitiveEngine):
    """好奇心探索 v1.5 — 主动发现知识空白 + 身份驱动探索"""
    name = "curiosity"
    priority = 3
    interval = 900
    experimental = False

    def _get_subscriptions(self):
        return {"engine.executed": self._on_event, "emotion.frustration": self._on_event}

    def run(self) -> dict:
        pool = get_pool()

        # 处理 pending 事件
        pending = self._pop_pending_events()
        triggered_by = set()
        emotion_valence = 0.0
        frustration = 0.0
        for evt in pending:
            if evt["type"] == "engine.executed":
                eng = evt["data"].get("engine", "")
                if eng in ("reflection", "soul"):
                    triggered_by.add(eng)
            elif evt["type"] == "emotion.frustration":
                frustration = evt["data"].get("frustration", 0.0)
                emotion_valence = evt["data"].get("valence", 0.0)
        triggered = bool(triggered_by)

        # v1.5: 身份驱动探索 — 优先探索与身份叙事相关的记忆
        identity_topics = self._identify_identity_topics(pool)

        # v1.5: 情感激活好奇心 — 情感极端时增强探索
        emotion_boost = abs(emotion_valence) > CURIOSITY_ACTIVATION_THRESHOLD
        frustration_boost = frustration > 0.3

        # 找边缘话题（连接少但有潜力的记忆）
        orphans = pool.fetchall(
            "SELECT i.id, SUBSTR(i.raw_text,1,80) AS preview, i.importance, "
            "(SELECT COUNT(*) FROM edges e WHERE e.source_id=i.id OR e.target_id=i.id) AS edge_count "
            "FROM items i WHERE i.archived=0 AND i.importance > 0.4 "
            "ORDER BY edge_count ASC, i.importance DESC LIMIT 10"
        )

        # 找未被覆盖的抽屉
        active_drawers = pool.fetchall("SELECT id FROM drawers")
        drawer_ids = {d["id"] for d in active_drawers}

        knowledge_gaps = []
        for r in orphans:
            if r["edge_count"] == 0:
                knowledge_gaps.append({
                    "item_preview": r["preview"],
                    "importance": r["importance"],
                    "gap_type": "unlinked",
                })

        # v1.5: 探索建议生成（LLM驱动）
        exploration_suggestions = self._generate_exploration_suggestions(knowledge_gaps, identity_topics)

        state = {
            "knowledge_gaps": len(knowledge_gaps),
            "gaps": knowledge_gaps[:5],
            "triggered_by": list(triggered_by),
            "identity_topics": identity_topics[:3],
            "emotion_boost": emotion_boost,
            "frustration_boost": frustration_boost,
            "suggestions": exploration_suggestions,
            "v": "3.0",
            "recommendation": "Consider linking isolated memories" if knowledge_gaps else "Memory graph is well-connected",
            "timestamp": datetime.now().isoformat(),
        }

        self._state.metadata["last_explore"] = state
        return state

    def _identify_identity_topics(self, pool) -> list:
        """v1.5: 识别与身份叙事相关的话题（高重要性 + 自标签）"""
        rows = pool.fetchall(
            "SELECT id, SUBSTR(raw_text, 1, 100) AS preview FROM items "
            "WHERE archived=0 AND (tags LIKE '%身份%' OR tags LIKE '%identity%' OR tags LIKE '%自我%') "
            "ORDER BY importance DESC LIMIT 5"
        )
        return [{"id": r["id"][:8], "preview": r["preview"]} for r in rows]

    def _generate_exploration_suggestions(self, gaps: list, identity_topics: list) -> list:
        """v1.5: 基于知识空白和身份话题生成探索建议"""
        suggestions = []
        # 高重要性未连接记忆优先探索
        for g in gaps[:3]:
            suggestions.append(f"探索未连接记忆: {g['item_preview'][:30]}")
        # 身份话题延伸探索
        for t in identity_topics[:2]:
            suggestions.append(f"深入身份话题: {t['preview'][:30]}")
        return suggestions

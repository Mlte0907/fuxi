"""伏羲 v1.0 — ReconsolidationEngine 再巩固"""
import logging
from datetime import datetime

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.reconsolidation")


@register_engine("reconsolidation", experimental=False)
class ReconsolidationEngine(CognitiveEngine):
    """再巩固 — 定期刷新重要记忆的衰减分数，模拟睡眠记忆巩固"""
    name = "reconsolidation"
    priority = 5
    interval = 3600
    experimental = False

    def run(self) -> dict:
        pool = get_pool()

        # 选中等重要性且衰减中的记忆
        candidates = pool.fetchall(
            "SELECT id, importance, decay_score, updated_at FROM items "
            "WHERE archived=0 AND importance BETWEEN 0.3 AND 0.7 "
            "AND decay_score BETWEEN 0.2 AND 0.8 "
            "AND updated_at < datetime('now','-1 day') "
            "ORDER BY decay_score ASC LIMIT 20"
        )

        boosted = 0
        with pool.connection() as c:
            for r in candidates:
                # 基于重要性再巩固
                boost = (r["importance"] * 0.2) + 0.05
                new_score = min(1.0, r["decay_score"] + boost)
                c.execute(
                    "UPDATE items SET decay_score = ?, updated_at = ? WHERE id = ?",
                    (round(new_score, 6), datetime.now().isoformat(), r["id"])
                )
                boosted += 1

        state = {
            "candidates": len(candidates),
            "boosted": boosted,
            "avg_boost": round((0.1 + 0.05), 3),
            "timestamp": datetime.now().isoformat(),
        }

        self._state.metadata["last_reconsolidation"] = state
        return state

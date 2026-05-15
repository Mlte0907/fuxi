"""伏羲 v1.0 — CreativeEngine 创意重组"""
import logging
import random
from datetime import datetime

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.creative")


@register_engine("creative", experimental=False)
class CreativeEngine(CognitiveEngine):
    """创意重组 — 跨领域随机连接，产生新联想"""
    name = "creative"
    priority = 3
    interval = 1200
    experimental = False

    def run(self) -> dict:
        pool = get_pool()

        # 随机选取来自不同抽屉的记忆对
        drawers = pool.fetchall("SELECT DISTINCT drawer_id FROM items WHERE archived=0")
        if len(drawers) < 2:
            return {"recombinations": 0, "message": "Not enough diverse drawers"}

        drawer_ids = [d["drawer_id"] for d in drawers]
        # 随机选两个不同抽屉
        a_drawer, b_drawer = random.sample(drawer_ids, min(2, len(drawer_ids)))

        items_a = pool.fetchall(
            "SELECT id, SUBSTR(raw_text,1,60) AS preview FROM items WHERE drawer_id=? AND archived=0 ORDER BY RANDOM() LIMIT 3",
            (a_drawer,)
        )
        items_b = pool.fetchall(
            "SELECT id, SUBSTR(raw_text,1,60) AS preview FROM items WHERE drawer_id=? AND archived=0 ORDER BY RANDOM() LIMIT 3",
            (b_drawer,)
        )

        recombinations = []
        for a in items_a:
            for b in items_b:
                recombinations.append({
                    "from": a["preview"],
                    "to": b["preview"],
                    "cross_domain": f"{a_drawer} ↔ {b_drawer}",
                })

        # 创建跨域连接（直接使用 item ID，避免 preview 截断冲突）
        id_map = {}
        for row in items_a:
            id_map[row["preview"]] = row["id"]
        for row in items_b:
            id_map[row["preview"]] = row["id"]
        for idx, _rec in enumerate(recombinations[:3]):
            try:
                import uuid
                # 直接用 items_a/b 的索引对应 ID，避免 preview 匹配
                a_idx = idx // len(items_b) if items_b else 0
                b_idx = idx % len(items_b) if items_b else 0
                item_a_id = items_a[min(a_idx, len(items_a) - 1)]["id"] if items_a else None
                item_b_id = items_b[min(b_idx, len(items_b) - 1)]["id"] if items_b else None
                if item_a_id and item_b_id:
                    with pool.connection() as c:
                        c.execute(
                            "INSERT OR IGNORE INTO edges (id, source_id, target_id, edge_type, weight, created_at) "
                            "VALUES (?,?,?,?,?,?)",
                            (str(uuid.uuid4()), item_a_id, item_b_id,
                             "related_to", 0.3, datetime.now().isoformat())
                        )
            except Exception:
                continue

        state = {
            "recombinations": len(recombinations),
            "samples": recombinations[:3],
            "drawers_crossed": f"{a_drawer} ↔ {b_drawer}",
            "timestamp": datetime.now().isoformat(),
        }

        self._state.metadata["last_creative"] = state
        return state

"""伏羲 v1.0 — ResonanceEngine 共鸣匹配"""
import json
import logging
from datetime import datetime

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.memory.embedding import get_embedding_service
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.resonance")


@register_engine("resonance", experimental=False)
class ResonanceEngine(CognitiveEngine):
    """共鸣匹配 — 发现情感/语义共鸣的记忆对"""
    name = "resonance"
    priority = 6
    interval = 600

    def run(self) -> dict:
        pool = get_pool()
        es = get_embedding_service()

        # 找高情感值的记忆
        emotional = pool.fetchall(
            "SELECT id, raw_text, emotion_valence, embedding FROM items "
            "WHERE archived=0 AND emotion_valence != 0 AND embedding IS NOT NULL "
            "ORDER BY ABS(emotion_valence) DESC LIMIT 30"
        )

        matches = []
        if len(emotional) >= 2:
            from fuxi.memory.search import cosine_similarity

            for i in range(len(emotional)):
                for j in range(i + 1, len(emotional)):
                    try:
                        vec_i = json.loads(emotional[i]["embedding"])
                        vec_j = json.loads(emotional[j]["embedding"])
                        sim = cosine_similarity(vec_i, vec_j)

                        # 情感共鸣：向量相似 且 情感值同向
                        same_sign = emotional[i]["emotion_valence"] * emotional[j]["emotion_valence"] > 0
                        if sim > 0.7 and same_sign:
                            matches.append({
                                "source": emotional[i]["id"][:8],
                                "target": emotional[j]["id"][:8],
                                "similarity": round(sim, 3),
                                "valence": emotional[i]["emotion_valence"],
                            })
                    except Exception:
                        continue

        # 取Top-10匹配
        matches.sort(key=lambda x: x["similarity"], reverse=True)
        top_matches = matches[:10]

        # 对高共鸣匹配建立图边（使用完整ID精确匹配）
        id_map = {row["id"][:8]: row["id"] for row in emotional}
        for m in top_matches[:5]:
            try:
                import uuid
                full_source = id_map.get(m["source"])
                full_target = id_map.get(m["target"])
                if not full_source or not full_target:
                    continue
                with pool.connection() as c:
                    c.execute(
                        "INSERT OR IGNORE INTO edges (id, source_id, target_id, edge_type, weight, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), full_source, full_target,
                         "related_to", m["similarity"], datetime.now().isoformat())
                    )
            except Exception:
                pass

        state = {
            "scanned": len(emotional),
            "matches_found": len(top_matches),
            "top_matches": top_matches,
            "timestamp": datetime.now().isoformat(),
        }

        self._state.metadata["last_resonance"] = state
        return state

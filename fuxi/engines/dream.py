"""伏羲 v1.0 — DreamConsolidation 15步梦境整理"""
import contextlib
import json
import logging
from datetime import datetime

from fuxi.config import config
from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.memory.search import cosine_similarity
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.dream")


@register_engine("dream", experimental=False)
class DreamConsolidation(CognitiveEngine):
    """梦境记忆巩固 — 15步梦境整理流程"""
    name = "dream"
    priority = 8
    interval = config.dream_interval

    def run(self) -> dict:
        pool = get_pool()
        steps_log = []
        stats = {"consolidated": 0, "linked": 0, "pruned": 0, "distilled": 0}

        # Step 1: 检索近期记忆
        recent = self._step_fetch_recent(pool, 50)
        steps_log.append(f"fetch: {len(recent)} items")

        if not recent:
            return {"status": "empty", "steps": steps_log}

        # Step 2: 去重检查
        merged = self._step_dedup(pool, recent)
        steps_log.append(f"dedup: {merged} merged")
        stats["consolidated"] += merged

        # Step 3: 建立连接
        linked = self._step_link(pool, recent)
        steps_log.append(f"link: {linked} edges")
        stats["linked"] += linked

        # Step 10-12: 衰减修剪
        from fuxi.memory.decay import decay_all
        decay_stats = decay_all(dry_run=False)
        steps_log.append(f"decay: {decay_stats}")
        stats["pruned"] = decay_stats["purge_candidates"]

        # Step 13-15: 蒸馏总结
        distilled = self._step_distill(pool, recent)
        steps_log.append(f"distill: {distilled} candidates")
        stats["distilled"] = distilled

        # 持久化状态
        state = {"stats": stats, "steps": steps_log, "timestamp": datetime.now().isoformat()}
        with pool.connection() as c:
            c.execute(
                "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
                "VALUES (?,?,?)",
                ("dream", json.dumps(state, ensure_ascii=False), datetime.now().isoformat())
            )

        self._state.metadata["last_dream"] = state
        return state

    def _step_fetch_recent(self, pool, limit: int) -> list:
        rows = pool.fetchall(
            "SELECT * FROM items WHERE archived=0 ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        return [dict(r) for r in rows]

    def _step_dedup(self, pool, items: list) -> int:
        # 加载 embedding 用于语义预筛选
        item_ids = [it["id"] for it in items]
        placeholders = ",".join("?" * len(item_ids))
        emb_rows = pool.fetchall(
            f"SELECT id, embedding FROM items WHERE id IN ({placeholders}) AND embedding IS NOT NULL",
            item_ids
        )
        emb_map = {}
        for r in emb_rows:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                emb_map[r["id"]] = json.loads(r["embedding"])

        merged = 0
        merged_ids = set()
        for i in range(len(items)):
            if items[i]["id"] in merged_ids:
                continue
            # 用 embedding 找 top-5 最相似候选项，替代盲窗
            candidates = []
            for j in range(len(items)):
                if i == j or items[j]["id"] in merged_ids:
                    continue
                pre_score = 0.0
                if items[i]["id"] in emb_map and items[j]["id"] in emb_map:
                    pre_score = cosine_similarity(emb_map[items[i]["id"]], emb_map[items[j]["id"]])
                if pre_score > 0.5:
                    candidates.append((j, pre_score))
            candidates.sort(key=lambda x: x[1], reverse=True)
            for j, _ in candidates[:5]:
                if self._similarity(items[i]["raw_text"], items[j]["raw_text"]) > 0.85:
                    newer, older = (items[i], items[j]) if items[i]["updated_at"] > items[j]["updated_at"] else (items[j], items[i])
                    merged_ids.add(older["id"])
                    with pool.connection() as c:
                        c.execute(
                            "UPDATE items SET archived=1, updated_at=? WHERE id=?",
                            (datetime.now().isoformat(), older["id"])
                        )
                    merged += 1
        return merged

    def _step_link(self, pool, items: list) -> int:
        # 加载 embedding 用于预筛选，避免 O(n²) 全量 Jaccard 比较
        item_ids = [it["id"] for it in items]
        placeholders = ",".join("?" * len(item_ids))
        emb_rows = pool.fetchall(
            f"SELECT id, embedding FROM items WHERE id IN ({placeholders}) AND embedding IS NOT NULL",
            item_ids
        )
        emb_map = {}
        for r in emb_rows:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                emb_map[r["id"]] = json.loads(r["embedding"])

        # 预计算候选项对：只用 embedding 相似度 > 0.3 的对做 Jaccard
        # 无 embedding 的对跳过（无法做语义预筛选，避免 O(n²) 盲比较）
        candidate_pairs = []
        has_embed = [items[i]["id"] in emb_map for i in range(len(items))]
        # 对有 embedding 的索引做分组：按向量第一维符号分桶，桶内才做两两比较
        buckets: dict = {}
        for i in range(len(items)):
            if not has_embed[i]:
                continue
            vec = emb_map[items[i]["id"]]
            key = tuple(1 if v >= 0 else -1 for v in vec[:8])  # 用前8维做超平面哈希
            buckets.setdefault(key, []).append(i)
            # 也加入相邻桶（汉明距离1）避免边界遗漏
            for flip in range(min(8, len(vec))):
                neighbor = list(key)
                neighbor[flip] *= -1
                buckets.setdefault(tuple(neighbor), []).append(i)
        seen = set()
        for bucket in buckets.values():
            for idx_a in range(len(bucket)):
                for idx_b in range(idx_a + 1, len(bucket)):
                    pair = (min(bucket[idx_a], bucket[idx_b]), max(bucket[idx_a], bucket[idx_b]))
                    if pair in seen:
                        continue
                    seen.add(pair)
                    i, j = pair
                    cos_sim = cosine_similarity(emb_map[items[i]["id"]], emb_map[items[j]["id"]])
                    if cos_sim >= 0.3:
                        candidate_pairs.append(pair)

        linked = 0
        for i, j in candidate_pairs:
            sim = self._similarity(items[i]["raw_text"], items[j]["raw_text"])
            if 0.3 < sim < 0.85:
                import uuid
                with pool.connection() as c:
                    c.execute(
                        "INSERT OR IGNORE INTO edges (id, source_id, target_id, edge_type, weight, created_at) "
                        "VALUES (?,?,?,?,?,?)",
                        (str(uuid.uuid4()), items[i]["id"], items[j]["id"],
                         "related_to", round(sim, 3), datetime.now().isoformat())
                    )
                linked += 1
        return linked

    def _step_distill(self, pool, items: list) -> int:
        # 标记高重要性低衰减的记忆作为蒸馏候选
        candidates = 0
        for item in items:
            if item.get("importance", 0) > 0.7 and item.get("decay_score", 0) > 0.8:
                candidates += 1
        return candidates

    def _similarity(self, a: str, b: str) -> float:
        """简单的 Jaccard 相似度（基于3-gram）"""
        if not a or not b:
            return 0.0
        a_grams = {a[i:i+3] for i in range(max(0, len(a)-2))}
        b_grams = {b[i:i+3] for i in range(max(0, len(b)-2))}
        if not a_grams or not b_grams:
            return 0.0
        intersection = len(a_grams & b_grams)
        union = len(a_grams | b_grams)
        return intersection / union if union > 0 else 0.0



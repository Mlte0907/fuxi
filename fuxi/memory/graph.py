"""伏羲 v1.0 — 记忆图谱（9种边 + BFS + 因果链）"""
import json
import logging
import uuid
from collections import deque
from datetime import datetime
from typing import List, Optional, Set

from fuxi.config import config
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.memory.graph")


class MemoryGraph:
    """记忆图谱管理器"""

    def add_edge(self, source_id: str, target_id: str, edge_type: str,
                 weight: float = 0.5, metadata: Optional[dict] = None) -> str:
        if edge_type not in config.edge_types:
            raise ValueError(f"Unknown edge type: {edge_type}")

        pool = get_pool()
        edge_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        # 反向边优先（取更强的关系）
        reverse = pool.fetchone(
            "SELECT id, weight FROM edges WHERE source_id=? AND target_id=? AND edge_type=?",
            (target_id, source_id, edge_type)
        )
        if reverse and reverse["weight"] >= weight:
            # 反向边已存在且权重更强，return现有边ID
            logger.debug(f"Reverse edge exists: {reverse['id'][:8]} (w={reverse['weight']:.2f})")
            return reverse["id"]

        with pool.connection() as c:
            if reverse:
                # 反向边权重较低，更新权重并return
                c.execute("UPDATE edges SET weight = ?, metadata = ? WHERE id = ?",
                          (weight, json.dumps(metadata or {}, ensure_ascii=False), reverse["id"]))
                logger.debug(f"Edge weight upgraded: {reverse['id'][:8]} ({reverse['weight']:.2f} -> {weight:.2f})")
                return reverse["id"]
            c.execute(
                "INSERT INTO edges (id, source_id, target_id, edge_type, weight, "
                "metadata, created_at) VALUES (?,?,?,?,?,?,?)",
                (edge_id, source_id, target_id, edge_type, weight,
                 json.dumps(metadata or {}, ensure_ascii=False), now)
            )
            # 双向更新记忆的图连接计数
            c.execute("UPDATE items SET updated_at=? WHERE id IN (?,?)",
                      (now, source_id, target_id))

        logger.debug(f"Edge: {source_id[:8]} --[{edge_type}]--> {target_id[:8]}")
        return edge_id

    def get_neighbors(self, item_id: str, edge_type: Optional[str] = None,
                      direction: str = "both", max_depth: int = 1,
                      min_weight: float = 0.0) -> List[dict]:
        """获取邻居节点，支持方向过滤"""
        pool = get_pool()
        results = []

        if direction in ("outgoing", "both"):
            type_clause = "AND e.edge_type = ?" if edge_type else ""
            params = (item_id, min_weight) if not edge_type else (item_id, edge_type, min_weight)
            rows = pool.fetchall(
                f"SELECT i.*, e.edge_type, e.weight, 'outgoing' AS direction "
                f"FROM items i JOIN edges e ON e.target_id = i.id "
                f"WHERE e.source_id = ? {type_clause} AND e.weight >= ? "
                f"AND i.archived = 0",
                params
            )
            results.extend([dict(r) for r in rows])

        if direction in ("incoming", "both"):
            type_clause = "AND e.edge_type = ?" if edge_type else ""
            params = (item_id, min_weight) if not edge_type else (item_id, edge_type, min_weight)
            rows = pool.fetchall(
                f"SELECT i.*, e.edge_type, e.weight, 'incoming' AS direction "
                f"FROM items i JOIN edges e ON e.source_id = i.id "
                f"WHERE e.target_id = ? {type_clause} AND e.weight >= ? "
                f"AND i.archived = 0",
                params
            )
            results.extend([dict(r) for r in rows])

        return results

    def bfs(self, start_id: str, max_depth: int = 3,
            edge_types: Optional[List[str]] = None, min_weight: float = 0.3) -> List[dict]:
        """BFS遍历图谱"""
        pool = get_pool()
        visited: Set[str] = set()
        queue = deque([(start_id, 0)])
        visited.add(start_id)
        result = []

        while queue:
            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            # 分离 outgoing 和 incoming 查询，避免 OR JOIN 问题
            if edge_types:
                placeholders = ",".join("?" * len(edge_types))
                # Outgoing edges (current -> others)
                out_rows = pool.fetchall(
                    f"SELECT DISTINCT i.*, e.edge_type, e.weight, e.source_id as from_id "
                    f"FROM items i JOIN edges e ON e.target_id = i.id "
                    f"WHERE e.source_id = ? AND e.edge_type IN ({placeholders}) "
                    f"AND e.weight >= ? AND i.id != ? AND i.archived = 0",
                    [current_id] + edge_types + [min_weight, start_id]
                )
                # Incoming edges (others -> current)
                in_rows = pool.fetchall(
                    f"SELECT DISTINCT i.*, e.edge_type, e.weight, e.target_id as from_id "
                    f"FROM items i JOIN edges e ON e.source_id = i.id "
                    f"WHERE e.target_id = ? AND e.edge_type IN ({placeholders}) "
                    f"AND e.weight >= ? AND i.id != ? AND i.archived = 0",
                    [current_id] + edge_types + [min_weight, start_id]
                )
                rows = list(out_rows) + list(in_rows)
            else:
                out_rows = pool.fetchall(
                    f"SELECT DISTINCT i.*, e.edge_type, e.weight, e.source_id as from_id "
                    f"FROM items i JOIN edges e ON e.target_id = i.id "
                    f"WHERE e.source_id = ? AND e.weight >= ? AND i.id != ? AND i.archived = 0",
                    [current_id, min_weight, start_id]
                )
                in_rows = pool.fetchall(
                    f"SELECT DISTINCT i.*, e.edge_type, e.weight, e.target_id as from_id "
                    f"FROM items i JOIN edges e ON e.source_id = i.id "
                    f"WHERE e.target_id = ? AND e.weight >= ? AND i.id != ? AND i.archived = 0",
                    [current_id, min_weight, start_id]
                )
                rows = list(out_rows) + list(in_rows)

            for r in rows:
                d = dict(r)
                nid = d["id"]
                if nid not in visited:
                    visited.add(nid)
                    d["depth"] = depth + 1
                    result.append(d)
                    queue.append((nid, depth + 1))

        result.sort(key=lambda x: (x.get("depth", 0), -x.get("weight", 0)))
        return result


    def causal_chain(self, item_id: str, max_length: int = 5) -> List[dict]:
        """追溯因果链（沿着 causes→enables→depends_on 边）"""
        pool = get_pool()
        chain = []
        current = item_id
        visited = set()

        for _ in range(max_length):
            if current in visited:
                break
            visited.add(current)

            item = pool.fetchone("SELECT * FROM items WHERE id = ? AND archived = 0", (current,))
            if not item:
                break
            chain.append(dict(item))

            # 找下一个因果节点
            edge = pool.fetchone(
                "SELECT source_id FROM edges WHERE target_id = ? "
                "AND edge_type IN ('causes','enables','depends_on') "
                "ORDER BY weight DESC LIMIT 1",
                (current,)
            )
            if not edge:
                break
            current = edge["source_id"]

        return chain

    def get_graph_stats(self) -> dict:
        pool = get_pool()
        total_edges = pool.fetchone("SELECT COUNT(*) AS cnt FROM edges")
        by_type = pool.fetchall(
            "SELECT edge_type, COUNT(*) AS cnt FROM edges GROUP BY edge_type ORDER BY cnt DESC"
        )
        return {
            "total_edges": total_edges["cnt"] if total_edges else 0,
            "by_type": {r["edge_type"]: r["cnt"] for r in by_type},
            "edge_types": config.edge_types
        }

    def get_edges(self, limit: int = 500, drawer_id: Optional[str] = None) -> List[dict]:
        """获取所有边，可选按 drawer 过滤（通过 source/target 所在 drawer）"""
        pool = get_pool()
        if drawer_id:
            rows = pool.fetchall(
                "SELECT DISTINCT e.* FROM edges e "
                "JOIN items si ON e.source_id = si.id "
                "JOIN items ti ON e.target_id = ti.id "
                "WHERE si.archived = 0 AND ti.archived = 0 "
                "AND (si.drawer_id = ? OR ti.drawer_id = ?) "
                "ORDER BY e.weight DESC LIMIT ?",
                (drawer_id, drawer_id, limit)
            )
        else:
            rows = pool.fetchall(
                "SELECT e.* FROM edges e "
                "JOIN items si ON e.source_id = si.id "
                "JOIN items ti ON e.target_id = ti.id "
                "WHERE si.archived = 0 AND ti.archived = 0 "
                "ORDER BY e.weight DESC LIMIT ?",
                (limit,)
            )
        return [dict(r) for r in rows]

    def remove_edge(self, edge_id: str) -> bool:
        pool = get_pool()
        with pool.connection() as c:
            c.execute("DELETE FROM edges WHERE id = ?", (edge_id,))
        return True

    def discover_auto_relations(self, top_k: int = 20, similarity_threshold: float = 0.85) -> dict:
        """v2.0: 基于嵌入向量聚类自动发现新关系

        流程: 取样 → 向量聚类 → 同簇高相似对 → LLM命名关系类型 → 自动创建边
        返回: 新发现的关系数和建议列表
        """
        pool = get_pool()

        # 取有嵌入向量的活跃记忆
        rows = pool.fetchall(
            "SELECT id, raw_text, embedding, drawer_id FROM items "
            "WHERE archived = 0 AND embedding IS NOT NULL "
            "ORDER BY updated_at DESC LIMIT 200"
        )
        if len(rows) < 5:
            return {"status": "skip", "reason": "not enough items with embeddings", "found": 0}

        items = [dict(r) for r in rows]
        embeddings = []
        for item in items:
            try:
                embeddings.append(json.loads(item["embedding"]))
            except Exception:
                pass

        if len(embeddings) < 5:
            return {"status": "skip", "reason": "not enough valid embeddings", "found": 0}

        # 简单聚类: 按 drawer 分组 + 向量余弦相似度
        from fuxi.memory.search import _cosine_sim
        candidates = []

        # 对每对检查相似度（同drawer优先）
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                if items[i]["drawer_id"] == items[j]["drawer_id"]:
                    continue  # 同一抽屉可能有 explicit relation，跳过
                try:
                    sim = _cosine_sim(embeddings[i], embeddings[j])
                    if sim >= similarity_threshold:
                        candidates.append({
                            "source_id": items[i]["id"],
                            "target_id": items[j]["id"],
                            "similarity": sim,
                        })
                except Exception:
                    continue

        # 去重（已存在的边）
        existing_edges = self.get_edges(limit=10000)
        existing_pairs = set()
        for e in existing_edges:
            existing_pairs.add((e["source_id"], e["target_id"]))

        new_candidates = [
            c for c in candidates
            if (c["source_id"], c["target_id"]) not in existing_pairs
            and (c["target_id"], c["source_id"]) not in existing_pairs
        ]

        discovered = 0
        suggestions = []
        for cand in new_candidates[:top_k]:
            # 自动创建相似关系边
            edge_id = self.add_edge(
                source_id=cand["source_id"],
                target_id=cand["target_id"],
                edge_type="related_to",
                weight=cand["similarity"],
                metadata={"discovered": "auto_cluster", "similarity": round(cand["similarity"], 3)},
            )
            discovered += 1
            suggestions.append({
                "source": cand["source_id"][:8],
                "target": cand["target_id"][:8],
                "similarity": round(cand["similarity"], 3),
                "edge_id": edge_id[:8],
            })

        logger.info(f"Auto-discovery: found {discovered} new relations")
        return {"status": "ok", "found": discovered, "suggestions": suggestions}

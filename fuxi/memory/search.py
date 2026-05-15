"""伏羲 v1.0 — 混合搜索（FTS5+向量+RRF+自适应权重）"""
import json
import logging
from typing import List, Optional

from fuxi.config import config
from fuxi.memory.embedding import get_embedding_service
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.memory.search")


def search(query: str, drawer_id: Optional[str] = None, limit: int = 20, offset: int = 0,
           vector_weight: Optional[float] = None, fts_weight: Optional[float] = None,
           min_score: float = 0.0, agent_id: Optional[str] = None,
           tags: Optional[List[str]] = None) -> dict:
    """Hybrid search combining FTS5 full-text + semantic vector + RRF fusion.

    Falls back gracefully when vector embedding is unavailable.
    Returns results with search_score, method, and weights metadata.
    """
    if not query or not query.strip():
        return {"results": [], "total": 0, "query": query, "method": "empty"}

    if vector_weight is None:
        vector_weight = config.vector_weight_default
    if fts_weight is None:
        fts_weight = config.fts_weight_default

    pool = get_pool()

    # FTS5全文搜索
    fts_results = {}
    try:
        fts_rows = pool.fetchall(
            "SELECT rowid, rank FROM items_fts WHERE items_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (query, limit * 3)
        )
        for i, r in enumerate(fts_rows):
            fts_results[r["rowid"]] = 1.0 / (fts_weight + i + 1)  # RRF for FTS
    except Exception as e:
        logger.warning(f"FTS search failed: {e}")

    # 向量语义搜索（优先使用向量索引加速）
    vec_results = {}
    embed_svc = get_embedding_service()
    query_vec = embed_svc.embed(query)
    if query_vec:
        try:
            # 尝试使用向量索引加速
            from fuxi.memory.vector_index import get_vector_index
            vix = get_vector_index()
            if vix.is_built and vix.size > 100:
                # 使用加速索引搜索
                indexed = vix.search(query_vec, top_k=limit * 3)
                # 需要将 item_id 映射回 rowid
                if indexed:
                    id_list = [item_id for item_id, _ in indexed]
                    id_placeholders = ",".join("?" * len(id_list))
                    id_rows = pool.fetchall(
                        f"SELECT id, rowid FROM items WHERE id IN ({id_placeholders}) AND archived=0",
                        id_list,
                    )
                    id_to_rowid = {r["id"]: r["rowid"] for r in id_rows}
                    for item_id, sim in indexed:
                        rowid = id_to_rowid.get(item_id)
                        if rowid and sim > config.similarity_threshold:
                            vec_results[rowid] = sim
            else:
                # 降级为分批扫描
                _brute_force_vec_search(pool, query_vec, limit, vec_results)
        except Exception as e:
            logger.warning(f"Vector index search failed, falling back: {e}")
            _brute_force_vec_search(pool, query_vec, limit, vec_results)

    # 如果只有向量结果没有FTS结果，要求更高阈值
    if not fts_results and vec_results:
        vec_results = {k: v for k, v in vec_results.items() if v > 0.3}

    # RRF融合
    fused = _rrf_fuse(fts_results, vec_results, fts_weight, vector_weight)

    if not fts_results and not vec_results:
        return {"results": [], "total": 0, "query": query, "method": "empty"}

    # 从DB获取完整记录
    if fused:
        fused_ids = list(fused.keys())
        placeholders = ",".join("?" * len(fused_ids))
        clauses = ["i.id IN (SELECT id FROM items WHERE rowid IN ({})".format(placeholders) + ")"]
        params = fused_ids.copy()
    else:
        clauses = ["i.archived = 0"]
        params = []

    if drawer_id:
        clauses.append("i.drawer_id = ?")
        params.append(drawer_id)

    if agent_id:
        clauses.append("EXISTS (SELECT 1 FROM agent_views av WHERE av.item_id = i.id AND av.agent_id = ?)")
        params.append(agent_id)

    if tags:
        tag_clauses = " OR ".join(["EXISTS (SELECT 1 FROM json_each(i.tags) WHERE value = ?)" for _ in tags])
        clauses.append(f"({tag_clauses})")
        for t in tags:
            params.append(t)

    where = " AND ".join(clauses)
    rows = pool.fetchall(
        f"SELECT i.* FROM items i WHERE {where} ORDER BY i.updated_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset]
    )

    results = []
    for r in rows:
        d = dict(r)
        rowid = d.get("rowid", 0)
        d["search_score"] = round(fused.get(rowid, 0.0), 4)
        if d["search_score"] < min_score:
            continue
        for f in ("tags", "collaborators"):
            if d.get(f) and isinstance(d[f], str):
                try:
                    d[f] = json.loads(d[f])
                except json.JSONDecodeError:
                    d[f] = []
        results.append(d)

    return {
        "results": results,
        "total": len(results),
        "query": query,
        "method": _compute_method(fts_results, vec_results, fused),
        "fts_used": len(fts_results) > 0,
        "vector_used": len(vec_results) > 0,
        "weights": {"vector": vector_weight, "fts": fts_weight}
    }


def _brute_force_vec_search(pool, query_vec, limit, vec_results):
    """暴力向量搜索 — 分批扫描数据库中的嵌入向量"""
    batch_size = min(limit * 2, 50)
    target_high_quality = limit * 2
    max_scan = limit * 5
    scores = []
    high_quality_count = 0

    for batch_offset in range(0, max_scan, batch_size):
        vec_rows = pool.fetchall(
            "SELECT id, rowid, embedding FROM items WHERE embedding IS NOT NULL "
            "AND archived = 0 LIMIT ? OFFSET ?",
            (batch_size, batch_offset)
        )
        if not vec_rows:
            break
        for r in vec_rows:
            try:
                vec = json.loads(r["embedding"])
                sim = _cosine_sim(query_vec, vec)
                if sim > 0.25:
                    scores.append((r["rowid"], sim))
                    if sim > 0.6:
                        high_quality_count += 1
            except (json.JSONDecodeError, Exception):
                continue
        if high_quality_count >= target_high_quality:
            break

    scores.sort(key=lambda x: x[1], reverse=True)
    for _i, (rowid, sim) in enumerate(scores[:limit * 3]):
        vec_results[rowid] = sim


def _rrf_fuse(fts: dict, vec: dict, fts_weight: float, vec_weight: float) -> dict:
    """倒数排名融合（Reciprocal Rank Fusion）"""
    merged: dict[int, float] = {}

    for rowid, score in fts.items():
        merged[rowid] = merged.get(rowid, 0) + score * fts_weight

    for rowid, score in vec.items():
        merged[rowid] = merged.get(rowid, 0) + score * vec_weight

    # 按融合分降序
    return dict(sorted(merged.items(), key=lambda x: x[1], reverse=True))


def _compute_method(fts: dict, vec: dict, fused: dict) -> str:
    """P1 BUG 4 FIX: 明确标记搜索降级状态"""
    fts_ok = len(fts) > 0
    vec_ok = len(vec) > 0
    if fts_ok and vec_ok:
        return "hybrid"  # 完整混合搜索
    if fts_ok:
        return "fts"  # 仅有FTS结果
    if vec_ok:
        return "vector_only"  # 仅有向量结果（无FTS，降级状态）
    return "empty"


def _cosine_sim(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def get_search_stats() -> dict:
    """Return search engine stats including embedding service health."""
    from fuxi.memory.embedding import get_embedding_service
    es = get_embedding_service()
    return {
        **es.stats,
        "vector_weight_default": config.vector_weight_default,
        "fts_weight_default": config.fts_weight_default,
    }


def holographic_search(query: str, weights: dict = None,
                       top_k: int = 10) -> List[dict]:
    """全息搜索 — 将查询编码为多维度投影，跨维度加权融合检索。

    纯大脑能力：不直接执行任务，只做记忆检索。
    支持 "昨天下午让我焦虑的那件事" 这样的跨维度自然语言查询。
    """
    from fuxi.memory.hologram import (DEFAULT_FUSION_WEIGHTS, FUSION_ORDER,
                                       get_holographic_encoder)
    from fuxi.memory.vector_index import get_holographic_index
    from fuxi.store.connection import get_pool

    if weights is None:
        weights = DEFAULT_FUSION_WEIGHTS

    encoder = get_holographic_encoder()
    h_index = get_holographic_index()

    if not h_index.is_built:
        return []

    now_str = datetime.now().isoformat()
    query_projections = {}

    for dim in FUSION_ORDER:
        if weights.get(dim, 0) <= 0:
            continue
        if dim == "semantic":
            es = get_embedding_service()
            vec = es.embed(query)
            if vec:
                query_projections["semantic"] = vec
        elif dim == "temporal":
            query_projections["temporal"] = encoder.temporal.encode(
                created_at=now_str
            ).tolist()
        elif dim == "emotional":
            query_projections["emotional"] = encoder.emotional.encode(
                valence=0.0, arousal=0.0, dominance=0.5
            ).tolist()
        elif dim == "causal":
            query_projections["causal"] = encoder.causal.encode(
                causal_summary=query
            ).tolist()
        elif dim == "source":
            query_projections["source"] = encoder.source.encode(
                source=query
            ).tolist()

    if not query_projections:
        return []

    fused = h_index.fused_search(query_projections, weights=weights, top_k=top_k)

    if not fused:
        return []

    pool = get_pool()
    item_ids = [item_id for item_id, _ in fused]
    placeholders = ",".join("?" * len(item_ids))
    rows = pool.fetchall(
        f"SELECT * FROM items WHERE id IN ({placeholders}) AND archived=0",
        item_ids,
    )

    result = []
    score_map = dict(fused)
    for r in rows:
        d = dict(r)
        d["holographic_score"] = round(score_map.get(d["id"], 0.0), 4)
        for f in ("tags", "collaborators"):
            if d.get(f) and isinstance(d[f], str):
                try:
                    d[f] = json.loads(d[f])
                except json.JSONDecodeError:
                    d[f] = []
        result.append(d)

    result.sort(key=lambda x: x["holographic_score"], reverse=True)
    return result[:top_k]

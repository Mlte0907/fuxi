"""伏羲 v1.0 — 记忆召回（Agent过滤+缓存+预算裁剪）"""
import contextlib
import hashlib
import json
import logging
import threading
import time
from typing import List, Optional

from fuxi.config import config
from fuxi.memory.embedding import get_embedding_service
from fuxi.memory.search import _cosine_sim
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.memory.retrieval")

_recall_cache: dict = {}
_cache_lock = threading.Lock()
_cache_ttl = 60  # 1分钟缓存


def recall(query: Optional[str] = None, drawer_id: Optional[str] = None, limit: int = 10,
           offset: int = 0, agent_id: Optional[str] = None, min_importance: float = 0.0,
           sort_by: str = "relevance", use_cache: bool = True,
           vector_weight: Optional[float] = None) -> List[dict]:
    """召回记忆，支持多种过滤和排序策略"""
    if vector_weight is None:
        vector_weight = config.vector_weight_default

    cache_key = None
    if use_cache and query:
        # BUG-005 fix: include min_importance in cache key
        cache_key = _make_cache_key(query, drawer_id, limit, offset, agent_id, sort_by, min_importance)
        with _cache_lock:
            if cache_key in _recall_cache:
                entry = _recall_cache[cache_key]
                if time.time() - entry["ts"] < _cache_ttl:
                    return entry["data"]

    pool = get_pool()
    clauses = ["i.archived = 0"]
    params: list = []

    if drawer_id:
        clauses.append("i.drawer_id = ?")
        params.append(drawer_id)

    if min_importance > 0:
        clauses.append("i.importance >= ?")
        params.append(min_importance)

    if agent_id:
        clauses.append("EXISTS (SELECT 1 FROM agent_views av WHERE av.item_id = i.id AND av.agent_id = ?)")
        params.append(agent_id)

    where = " AND ".join(clauses)

    if query:
        query_vec = None
        embed_svc = get_embedding_service()
        with contextlib.suppress(Exception):
            query_vec = embed_svc.embed(query)

        if query_vec:
            # 先按复合索引取候选集（limit*3），再计算精确 relevance，避免全表计算
            candidate_limit = limit * 5
            rows = pool.fetchall(
                f"SELECT i.*, i.decay_score * {vector_weight} + i.importance * (1-{vector_weight}) AS relevance "
                f"FROM items i WHERE {where} AND i.embedding IS NOT NULL "
                f"ORDER BY relevance DESC LIMIT ?",
                params + [candidate_limit]
            )
            # 在 Python 端计算精确向量相似度并重新排序
            def _vec_similarity(row):
                try:
                    vec = json.loads(row["embedding"])
                    return _cosine_sim(vec, query_vec)
                except Exception:
                    return 0.0
            rows_sorted = sorted(rows, key=lambda r: _vec_similarity(r) * vector_weight + r["importance"] * (1 - vector_weight), reverse=True)
            rows = rows_sorted[offset:offset + limit]
        else:
            # 纯FTS降级
            rows = pool.fetchall(
                f"SELECT i.*, i.importance AS relevance FROM items i "
                f"JOIN items_fts fts ON fts.rowid = i.rowid "
                f"WHERE {where} AND fts MATCH ? "
                f"ORDER BY rank LIMIT ? OFFSET ?",
                params + [query, limit, offset]
            )
    else:
        order_col = "i.importance" if sort_by == "importance" else "i.updated_at"
        rows = pool.fetchall(
            f"SELECT i.*, {order_col} AS relevance FROM items i "
            f"WHERE {where} ORDER BY {order_col} DESC LIMIT ? OFFSET ?",
            params + [limit, offset]
        )

    results = [_row_to_dict(r) for r in rows]

    if cache_key:
        with _cache_lock:
            if len(_recall_cache) >= config.recall_cache_max:
                oldest = next(iter(_recall_cache))
                del _recall_cache[oldest]
            _recall_cache[cache_key] = {"ts": time.time(), "data": results}

    return results


def recall_by_ids(item_ids: List[str]) -> List[dict]:
    """按ID批量召回"""
    if not item_ids:
        return []
    pool = get_pool()
    placeholders = ",".join("?" * len(item_ids))
    rows = pool.fetchall(
        f"SELECT * FROM items WHERE id IN ({placeholders}) AND archived=0",
        item_ids
    )
    return [_row_to_dict(r) for r in rows]


def recall_context(drawer_id: Optional[str] = None, budget: Optional[int] = None) -> List[dict]:
    """召回上下文窗口内的记忆（用于LLM上下文组装）"""
    if budget is None:
        budget = config.default_context_budget
    # 优选高重要性+高衰减分+近期更新的记忆
    pool = get_pool()
    clauses = ["i.archived = 0"]
    params: list = []
    if drawer_id:
        clauses.append("i.drawer_id = ?")
        params.append(drawer_id)
    where = " AND ".join(clauses)
    rows = pool.fetchall(
        f"SELECT i.* FROM items i WHERE {where} "
        f"ORDER BY (i.importance * 0.4 + i.decay_score * 0.3 - "
        f"CAST((julianday('now') - julianday(i.updated_at)) AS REAL) * 0.3) DESC "
        f"LIMIT ?",
        params + [min(budget, 50)]
    )
    return [_row_to_dict(r) for r in rows]


def _make_cache_key(*args) -> str:
    raw = json.dumps(args, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


def _row_to_dict(row) -> dict:
    d = dict(row)
    for field in ("tags", "collaborators"):
        if d.get(field) and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except json.JSONDecodeError:
                d[field] = []
    return d


def clear_recall_cache():
    """Clear the recall cache to force fresh DB queries."""
    global _recall_cache
    with _cache_lock:
        _recall_cache.clear()
    logger.debug("Recall cache cleared")

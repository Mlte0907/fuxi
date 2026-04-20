#!/usr/bin/env python3
"""
伏羲 (Fuxi) — 混合检索引擎
Phase 1: 向量检索 × FTS全文 × 结构化过滤 × Reciprocal Rank 重排序

检索流程:
  1. 向量检索 (Chroma) — 语义相似度
  2. FTS5 全文检索 — 关键词匹配
  3. 结构化过滤 — world/room/drawer/tags 过滤
  4. RRF 重排序 — 融合多路结果
  5. 遗忘曲线加权 — decay_score * importance 影响排序
"""

import json, math, sqlite3, os, random
from pathlib import Path
from typing import Optional

# 路径配置（与 fuxi_core 保持一致）
def _get_base():
    return Path(os.environ.get("FUXI_BASE_DIR", os.path.expanduser("~/.openclaw/fuxi")))

BASE_DIR = _get_base()
DB_PATH  = BASE_DIR / "fuxi.db"
CHROMA_DIR = BASE_DIR / "chroma"

SCNET_BASE = os.environ.get("SCNET_BASE", "https://api.scnet.cn/api/llm/v1")
SCNET_KEY  = os.environ.get("SCNET_KEY", "")

_chroma_client = None

def get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        try:
            import chromadb
            _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        except ImportError:
            _chroma_client = None
    return _chroma_client


def embed_query(text: str) -> list[float]:
    """对查询文本进行向量化"""
    if not SCNET_KEY:
        return [random.random() * 2 - 1 for _ in range(1536)]
    import urllib.request

    payload = json.dumps({
        "model": "Qwen3-Embedding-8B",
        "input": text[:2000]
    }).encode()

    req = urllib.request.Request(
        f"{SCNET_BASE}/embeddings",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SCNET_KEY}"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
            return result["data"][0]["embedding"]
    except Exception as e:
        print(f"[伏羲] 查询向量化失败: {e}")
        return [random.random() * 2 - 1 for _ in range(1536)]


def search(
    query: str,
    world_id: str = None,
    room_id: str = None,
    drawer_id: str = None,
    tags: list = None,
    top_k: int = 10,
    hybrid: bool = True
) -> list[dict]:
    """
    混合检索：融合向量 + FTS + 遗忘曲线加权
    """
    results = {}  # item_id -> score

    # ── 1. 向量检索 ──────────────────────────────────────
    if hybrid:
        vec = embed_query(query)
        client = get_chroma_client()
        if client:
            try:
                coll = client.get_or_create_collection("fuxi_items")
                vect_results = coll.query(
                    query_embeddings=[vec],
                    n_results=min(top_k * 2, 50),
                    include=["metadatas", "documents", "distances"]
                )
                for i, (mid, dist, doc) in enumerate(zip(
                        vect_results["ids"][0],
                        vect_results["distances"][0],
                        vect_results["documents"][0])):
                    score = 1.0 / (dist + 0.001)
                    if mid in results:
                        results[mid] += score * 0.6
                    else:
                        results[mid] = score * 0.6
            except Exception as e:
                print(f"[伏羲] 向量检索失败: {e}")

    # ── 2. FTS5 全文检索 ────────────────────────────────
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    fts_query = query
    fts_query = fts_query.replace("'", "''")

    try:
        sql = "SELECT id, raw_text FROM items_fts WHERE items_fts MATCH ? LIMIT ?"
        cur.execute(sql, (fts_query, top_k * 3))
        fts_rows = cur.fetchall()
        for i, (mid, _) in enumerate(fts_rows):
            rank_score = 1.0 / (i + 1)
            if mid in results:
                results[mid] += rank_score * 0.4
            else:
                results[mid] = rank_score * 0.4
    except Exception as e:
        print(f"[伏羲] FTS 检索失败: {e}")

    # ── 3. 结构化过滤（Drawer/World/Room）────────────────
    if drawer_id or room_id or world_id or tags:
        filter_sql = "SELECT id FROM items WHERE 1=1"
        params = []
        if drawer_id:
            filter_sql += " AND drawer_id=?"
            params.append(drawer_id)
        if room_id:
            filter_sql = """
                SELECT i.id FROM items i
                JOIN drawers d ON i.drawer_id = d.id
                JOIN rooms r ON d.room_id = r.id
                WHERE r.id = ?
            """
            params = [room_id]
        if world_id:
            filter_sql += " AND drawer_id IN (SELECT d.id FROM drawers d JOIN rooms r ON d.room_id=r.id WHERE r.world_id=?)"
            params.append(world_id)
        if tags:
            tag_conds = " OR ".join(["tags LIKE ?"] * len(tags))
            filter_sql = f"""
                SELECT id FROM items
                WHERE ({tag_conds})
            """ + (f" AND drawer_id IN (SELECT d.id FROM drawers d JOIN rooms r ON d.room_id=r.id WHERE r.world_id='{world_id}')" if world_id else "")
            params = [f'%"{t}"%' for t in tags]
        cur.execute(filter_sql, params)
        filtered_ids = set(r[0] for r in cur.fetchall())
        results = {k: v for k, v in results.items() if k in filtered_ids}

    # ── 4. 遗忘曲线加权 ──────────────────────────────────
    scored_items = []
    for iid, score in results.items():
        cur.execute(
            "SELECT decay_score, importance, raw_text FROM items WHERE id=?", (iid,)
        )
        row = cur.fetchone()
        if row:
            decay, importance, raw_text = row
            weighted = score * (float(decay) * 0.7 + float(importance) * 0.3)
            scored_items.append({
                "id": iid,
                "score": round(weighted, 4),
                "raw_text": raw_text[:150],
                "decay_score": decay,
                "importance": importance
            })

    conn.close()

    # ── 5. 排序返回 ─────────────────────────────────────
    scored_items.sort(key=lambda x: x["score"], reverse=True)
    return scored_items[:top_k]

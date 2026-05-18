"""伏羲 v1.0 — 记忆摄入（去重+智能分类）"""
import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fuxi.config import config
from fuxi.memory.embedding import get_embedding_service
from fuxi.memory.search import cosine_similarity
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.memory.ingestion")

def remember(raw_text: str, drawer_id: str = "default", importance: float = 0.5,
             tags: Optional[list] = None, source: str = "direct", confidence: Optional[float] = None,
             created_by: str = "system", facts: str = "",
             collaborators: Optional[list] = None, emotion_valence: float = 0.0,
             conn=None) -> str:
    """Ingest a memory into FuXi.

    Deduplicates against existing memories using text similarity.
    Generates vector embedding and stores in SQLite.

    Returns the memory item ID (new or existing).
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("raw_text is required")
    if confidence is None:
        confidence = config.confidence_sources.get(source, 1.0)
    tags = tags or []
    collaborators = collaborators or []

    # 去重检查
    existing = _find_duplicate(raw_text)
    if existing:
        _boost_existing(existing["id"])
        return existing["id"]

    item_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    embed = get_embedding_service()
    vec = embed.embed(raw_text)
    # P0 BUG FIX: 确保向量有效，拒绝零向量
    if not vec or all(abs(v) < 1e-6 for v in vec):
        logger.warning(f"Zero/invalid embedding for item {item_id[:8]}, retrying with local fallback")
        vec = embed._local_embed(raw_text)
    if not vec or all(abs(v) < 1e-6 for v in vec):
        logger.error(f"Failed to generate valid embedding for item {item_id[:8]}, storing without vector")
        vec = None
    vec_json = json.dumps(vec) if vec else None

    pool = get_pool()
    if conn is not None:
        _do_insert(conn, item_id, raw_text, facts, drawer_id, importance,
                   tags, source, confidence, created_by, collaborators,
                   emotion_valence, vec_json, now)
    else:
        with pool.connection() as c:
            _do_insert(c, item_id, raw_text, facts, drawer_id, importance,
                       tags, source, confidence, created_by, collaborators,
                       emotion_valence, vec_json, now)

    logger.info(f"Remembered: {item_id[:8]} in drawer={drawer_id}, importance={importance}")

    try:
        _encode_hologram(item_id, raw_text, now, drawer_id, emotion_valence,
                         source, created_by, tags)
    except Exception as e:
        logger.debug(f"Holographic encoding skipped: {e}")

    return item_id


def _encode_hologram(item_id: str, raw_text: str, created_at: str,
                     drawer_id: str, emotion_valence: float,
                     source: str, created_by: str, tags: list):
    from fuxi.memory.hologram import get_holographic_encoder
    from fuxi.memory.vector_index import get_holographic_index

    encoder = get_holographic_encoder()
    hologram = encoder.encode_existing(
        item_id=item_id,
        raw_text=raw_text,
        created_at=created_at,
        drawer_id=drawer_id,
        valence=emotion_valence,
        source_type=source,
        created_by=created_by,
        tags=tags,
    )

    try:
        h_index = get_holographic_index()
        h_index.add_hologram(hologram)
    except Exception as e:
        logger.debug(f"Holographic index add failed: {e}")


def _do_insert(conn, item_id, raw_text, facts, drawer_id, importance,
               tags, source, confidence, created_by, collaborators,
               emotion_valence, vec_json, now):
    conn.execute(
        "INSERT INTO items (id, raw_text, facts, drawer_id, importance, "
        "tags, source, confidence, created_by, collaborators, "
        "emotion_valence, embedding, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (item_id, raw_text, facts, drawer_id, importance,
         json.dumps(tags, ensure_ascii=False), source, confidence, created_by,
         json.dumps(collaborators, ensure_ascii=False),
         emotion_valence, vec_json, now, now)
    )
    conn.execute("UPDATE drawers SET item_count = item_count + 1, updated_at = ? WHERE id = ?",
              (now, drawer_id))


def _text_based_fallback_dedup(raw_text: str) -> Optional[dict]:
    """v1.1 fix: embedding 服务不可用时的降级去重（文本相似度）"""
    if len(raw_text) < 20:
        return None
    pool = get_pool()
    rows = pool.fetchall(
        "SELECT id, raw_text FROM items WHERE archived = 0 "
        "AND LENGTH(raw_text) BETWEEN ? AND ? "
        "ORDER BY created_at DESC LIMIT 50",
        (len(raw_text) - 5, len(raw_text) + 5),
    )
    for r in rows:
        other = r["raw_text"]
        if len(other) < 10:
            continue
        # 长度相近且有 40+ 字符重叠认为是相似
        overlap = sum(1 for a, b in zip(raw_text, other) if a == b)
        len_norm = max(len(raw_text), len(other))
        if overlap / len_norm > 0.85:
            return dict(r)
    return None


def _find_duplicate(raw_text: str) -> Optional[dict]:
    pool = get_pool()
    # Exact match first
    row = pool.fetchone(
        "SELECT id, raw_text FROM items WHERE raw_text = ? AND archived = 0 LIMIT 1",
        (raw_text,)
    )
    if row:
        return dict(row)
    # Semantic similarity check using embedding
    embed = get_embedding_service()
    query_vec = embed.embed(raw_text)
    if query_vec is None:
        # v1.1 fix: embedding 服务失败时，降级到文本相似度（长度+ substring 检查）
        return _text_based_fallback_dedup(raw_text)
    # Get recent memories from same drawer for comparison
    # BUG-003 fix: Use vector index when available for faster/better candidate selection
    try:
        from fuxi.memory.vector_index import get_vector_index
        vix = get_vector_index()
        if vix.is_built and vix.size > 0:
            candidates = vix.search(query_vec, top_k=20)
            if candidates:
                id_list = [item_id for item_id, _ in candidates]
                placeholders = ",".join("?" * len(id_list))
                candidate_rows = pool.fetchall(
                    f"SELECT id, raw_text, embedding FROM items "
                    f"WHERE id IN ({placeholders}) AND archived = 0",
                    id_list
                )
                best_score = 0.0
                best_row = None
                for r in candidate_rows:
                    if not r["embedding"]:
                        continue
                    try:
                        stored_vec = json.loads(r["embedding"])
                        score = cosine_similarity(query_vec, stored_vec)
                        if score > 0.92 and score > best_score:
                            best_score = score
                            best_row = dict(r)
                    except Exception:
                        continue
                if best_row:
                    logger.info(f"Semantic duplicate found (via index): score={best_score:.3f}")
                    return best_row
    except Exception as e:
        logger.warning(f"Vector index dedup check failed, falling back: {e}")

    # v1.5.2 fix: Fallback 扫描限制为 50 条（原本 200 条），并在相同 drawer 内扫描以减少范围
    rows = pool.fetchall(
        "SELECT id, raw_text, embedding FROM items WHERE archived = 0 AND drawer_id = 'default' "
        "ORDER BY created_at DESC LIMIT 50"
    )
    best_score = 0.0
    best_row = None
    for r in rows:
        if not r["embedding"]:
            continue
        try:
            stored_vec = json.loads(r["embedding"])
            score = cosine_similarity(query_vec, stored_vec)
            if score > 0.92 and score > best_score:
                best_score = score
                best_row = dict(r)
        except Exception:
            continue
    if best_row:
        logger.info(f"Semantic duplicate found (scan): score={best_score:.3f}")
        return best_row
    return None


def _boost_existing(item_id: str):
    pool = get_pool()
    with pool.connection() as c:
        c.execute(
            "UPDATE items SET importance = MIN(1.0, importance + 0.05), "
            "decay_score = MIN(1.0, decay_score * 1.1), updated_at = ? "
            "WHERE id = ?",
            (datetime.now().isoformat(), item_id)
        )

"""伏羲 v1.0 — 向量索引加速层

支持 FAISS/hnswlib 作为可选向量索引后端，加速大规模向量搜索。
当第三方库不可用时自动降级为 brute-force。"""
import json
import logging
import threading
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger("fuxi.memory.vector_index")


class VectorIndex:
    """向量索引抽象 — 加速大规模向量相似度搜索

    优先级: FAISS > hnswlib > brute-force
    """

    def __init__(self, dim: int = 1024):
        self._dim = dim
        self._lock = threading.Lock()
        self._backend = self._detect_backend()
        self._index = None
        self._id_map: List[str] = []  # index position → item_id
        self._built = False

    @property
    def backend_name(self) -> str:
        return self._backend

    @property
    def is_built(self) -> bool:
        return self._built

    @property
    def size(self) -> int:
        return len(self._id_map)

    def _detect_backend(self) -> str:
        """检测可用的向量索引后端"""
        import importlib.util
        if importlib.util.find_spec("faiss"):
            logger.info("Vector index backend: FAISS")
            return "faiss"
        if importlib.util.find_spec("hnswlib"):
            logger.info("Vector index backend: hnswlib")
            return "hnswlib"
        logger.info("Vector index backend: brute-force (no acceleration library)")
        return "brute-force"

    def build(self, vectors: List[Tuple[str, List[float]]]):
        """从 (item_id, vector) 列表构建索引"""
        if not vectors:
            return

        with self._lock:
            self._id_map = [item_id for item_id, _ in vectors]
            vecs = np.array([v for _, v in vectors], dtype=np.float32)

            if self._backend == "faiss":
                self._build_faiss(vecs)
            elif self._backend == "hnswlib":
                self._build_hnswlib(vecs)
            # brute-force: no index needed, compare directly

            self._built = True
            logger.info(f"Vector index built: {len(vectors)} vectors, backend={self._backend}")

    def _build_faiss(self, vecs: np.ndarray):
        import faiss
        self._dim = vecs.shape[1]
        index = faiss.IndexFlatIP(self._dim)  # inner product (cosine on normalized vecs)
        faiss.normalize_L2(vecs)
        index.add(vecs)
        self._index = index

    def _build_hnswlib(self, vecs: np.ndarray):
        import hnswlib
        self._dim = vecs.shape[1]
        index = hnswlib.Index(space="cosine", dim=self._dim)
        index.init_index(max_elements=len(vecs), ef_construction=200, M=16)
        index.add_items(vecs, np.arange(len(vecs)))
        index.set_ef(50)
        self._index = index

    def search(self, query_vec: List[float], top_k: int = 10) -> List[Tuple[str, float]]:
        """搜索与查询向量最相似的 top_k 条记录

        Returns:
            [(item_id, similarity_score), ...] 按相似度降序
        """
        query = np.array([query_vec], dtype=np.float32)

        with self._lock:
            if not self._built:
                return []

            if self._backend == "faiss":
                return self._search_faiss(query, top_k)
            elif self._backend == "hnswlib":
                return self._search_hnswlib(query, top_k)
            else:
                return self._search_brute(query, top_k)

    def _search_faiss(self, query: np.ndarray, top_k: int) -> List[Tuple[str, float]]:
        import faiss
        faiss.normalize_L2(query)
        scores, indices = self._index.search(query, min(top_k, self.size))
        results = []
        for idx, score in zip(indices[0], scores[0], strict=True):
            if idx >= 0 and idx < len(self._id_map):
                results.append((self._id_map[idx], float(score)))
        return results

    def _search_hnswlib(self, query: np.ndarray, top_k: int) -> List[Tuple[str, float]]:
        indices, distances = self._index.knn_query(
            query, k=min(top_k, self.size)
        )
        results = []
        for idx, dist in zip(indices[0], distances[0], strict=True):
            if 0 <= idx < len(self._id_map):
                results.append((self._id_map[idx], float(1.0 - dist)))
        return results

    def _search_brute(self, query: np.ndarray, top_k: int) -> List[Tuple[str, float]]:
        """暴力搜索 — 对非索引后端，每次搜索都需加载所有向量"""
        from fuxi.store.connection import get_pool

        pool = get_pool()
        rows = pool.fetchall(
            "SELECT id, embedding FROM items WHERE embedding IS NOT NULL AND archived=0"
        )
        if not rows:
            return []

        scores = []
        query_norm = query[0] / (np.linalg.norm(query[0]) + 1e-8)
        for row in rows:
            try:
                vec = np.array(json.loads(row["embedding"]), dtype=np.float32)
                vec_norm = vec / (np.linalg.norm(vec) + 1e-8)
                sim = float(np.dot(query_norm, vec_norm))
                scores.append((row["id"], sim))
            except Exception:
                continue

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def add(self, item_id: str, vector: List[float]):
        """向已构建的索引添加单个向量（仅 FAISS/hnswlib 支持）"""
        with self._lock:
            if self._backend == "brute-force" or not self._built:
                return
            vec = np.array([vector], dtype=np.float32)
            if self._backend == "faiss":
                import faiss
                faiss.normalize_L2(vec)
                self._index.add(vec)
            elif self._backend == "hnswlib":
                idx = len(self._id_map)
                self._index.add_items(vec, np.array([idx]))
            self._id_map.append(item_id)

    def remove(self, item_id: str):
        """从索引中移除向量（标记为空，不重建）"""
        with self._lock:
            if item_id in self._id_map:
                idx = self._id_map.index(item_id)
                self._id_map[idx] = ""  # 标记为空槽位
            # FAISS/hnswlib 不支持单条删除，需要重建

    def rebuild_if_needed(self):
        """当移除条目过多时重建索引"""
        empty_count = sum(1 for i in self._id_map if i == "")
        if empty_count > len(self._id_map) * 0.3:
            logger.info(f"Rebuilding vector index ({empty_count} empty slots)")
            self._built = False
            self._index = None
            valid = [(i, self._get_vec(i)) for i in self._id_map if i]
            filtered = [(i, v) for i, v in valid if v is not None]
            self.build(filtered)

    def _get_vec(self, item_id: str) -> Optional[List[float]]:
        from fuxi.store.connection import get_pool

        pool = get_pool()
        row = pool.fetchone(
            "SELECT embedding FROM items WHERE id=? AND embedding IS NOT NULL",
            (item_id,)
        )
        if row:
            try:
                return json.loads(row["embedding"])
            except Exception:
                pass
        return None


class HolographicVectorIndex:
    """全息向量索引 — 多维投影的多索引向量库

    每个维度维护独立的 FAISS/brute-force 索引，支持：
    - 单维度检索
    - 跨维度加权融合检索
    """

    INDEX_DIMS = {
        "semantic": 1024,
        "temporal": 256,
        "emotional": 128,
        "causal": 256,
        "source": 128,
    }

    def __init__(self):
        self._indices: dict = {}
        self._id_maps: dict = {}
        self._local_vecs: dict = {}
        self._lock = threading.Lock()
        self._built = False

    @property
    def is_built(self) -> bool:
        return self._built

    @property
    def sizes(self) -> dict:
        return {name: len(m) for name, m in self._id_maps.items()}

    def add(self, item_id: str, projection: np.ndarray, index_name: str):
        with self._lock:
            if index_name not in self._indices:
                self._indices[index_name] = VectorIndex(
                    dim=self.INDEX_DIMS.get(index_name, 256)
                )
                self._id_maps[index_name] = []

            vec_list = projection.tolist() if isinstance(projection, np.ndarray) else projection
            self._id_maps[index_name].append(item_id)

            idx = self._indices[index_name]
            idx._built = True
            idx._id_map = self._id_maps[index_name]

            if index_name not in self._local_vecs:
                self._local_vecs[index_name] = {}
            self._local_vecs[index_name][item_id] = vec_list

            if idx._backend != "brute-force":
                if idx._index is not None:
                    idx.add(item_id, vec_list)
            self._built = True

    def add_hologram(self, hologram):
        from fuxi.memory.hologram import Hologram
        for dim_name in hologram.all_dims():
            proj = hologram.get(dim_name)
            if proj is not None:
                self.add(hologram.item_id, proj, dim_name)

    def search(self, query_vec: List[float], index_name: str, top_k: int = 10
               ) -> List[Tuple[str, float]]:
        with self._lock:
            if index_name not in self._indices:
                return []
            idx = self._indices[index_name]
            if (idx._backend == "brute-force" or idx._index is None):
                local = self._local_vecs.get(index_name, {})
                if local:
                    scores = []
                    query_np = np.array(query_vec, dtype=np.float32)
                    q_norm = query_np / (np.linalg.norm(query_np) + 1e-8)
                    for item_id, vec_list in local.items():
                        v_np = np.array(vec_list, dtype=np.float32)
                        v_norm = v_np / (np.linalg.norm(v_np) + 1e-8)
                        sim = float(np.dot(q_norm, v_norm))
                        scores.append((item_id, sim))
                    scores.sort(key=lambda x: x[1], reverse=True)
                    return scores[:top_k]
            return idx.search(query_vec, top_k)

    def fused_search(self, query_projections: dict, weights: dict = None,
                     top_k: int = 10) -> List[Tuple[str, float]]:
        if weights is None:
            from fuxi.memory.hologram import DEFAULT_FUSION_WEIGHTS
            weights = DEFAULT_FUSION_WEIGHTS

        all_scores: dict = {}
        for dim_name, query_vec in query_projections.items():
            weight = weights.get(dim_name, 0.0)
            if weight <= 0:
                continue
            results = self.search(query_vec, index_name=dim_name, top_k=top_k * 2)
            for item_id, score in results:
                all_scores[item_id] = all_scores.get(item_id, 0.0) + score * weight

        sorted_items = sorted(all_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_items[:top_k]

    def remove(self, item_id: str):
        with self._lock:
            for name in self._indices:
                if item_id in self._id_maps.get(name, []):
                    self._indices[name].remove(item_id)


_holographic_index: Optional[HolographicVectorIndex] = None
_holographic_index_lock = threading.Lock()


def get_holographic_index() -> HolographicVectorIndex:
    global _holographic_index
    if _holographic_index is None:
        with _holographic_index_lock:
            if _holographic_index is None:
                _holographic_index = HolographicVectorIndex()
    return _holographic_index


# ── 全局单例 ──
_vec_index: Optional[VectorIndex] = None
_vec_index_lock = threading.Lock()


def get_vector_index(dim: int = 1024) -> VectorIndex:
    global _vec_index
    if _vec_index is None:
        with _vec_index_lock:
            if _vec_index is None:
                _vec_index = VectorIndex(dim=dim)
    return _vec_index

"""伏羲 v1.5 — 全息记忆编码：多维度投影 + 跨维度检索

纯大脑能力：将记忆分解为语义/时空/情感/因果/来源五维投影，
支持任一维度独立检索，跨维度加权融合重建完整记忆。
"""
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

from fuxi.memory.embedding import get_embedding_service

logger = logging.getLogger("fuxi.memory.hologram")

PROJECTION_DIMS = {
    "semantic": 1024,
    "temporal": 256,
    "emotional": 128,
    "causal": 256,
    "source": 128,
}

FUSION_ORDER = ["semantic", "temporal", "emotional", "causal", "source"]

DEFAULT_FUSION_WEIGHTS = {
    "semantic": 0.40,
    "temporal": 0.15,
    "emotional": 0.15,
    "causal": 0.20,
    "source": 0.10,
}


@dataclass
class Hologram:
    item_id: str
    projections: Dict[str, np.ndarray] = field(default_factory=dict)

    def get(self, dim: str) -> Optional[np.ndarray]:
        return self.projections.get(dim)

    def all_dims(self) -> List[str]:
        return [d for d in FUSION_ORDER if d in self.projections]

    @property
    def byte_size(self) -> int:
        total = 0
        for vec in self.projections.values():
            total += vec.nbytes
        return total


class TemporalEncoder:
    """时空投影编码器 — 将时间+抽屉+位置编码为256维向量"""

    def __init__(self, dim: int = 256):
        self._dim = dim
        self._rng = np.random.default_rng(42)

    def encode(self, created_at: str, drawer_id: str = "",
               sequence_position: int = 0) -> np.ndarray:
        vec = np.zeros(self._dim, dtype=np.float32)

        if created_at:
            try:
                if isinstance(created_at, str):
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                else:
                    dt = created_at

                hour_sin = np.sin(2 * np.pi * dt.hour / 24.0)
                hour_cos = np.cos(2 * np.pi * dt.hour / 24.0)
                dow_sin = np.sin(2 * np.pi * dt.weekday() / 7.0)
                dow_cos = np.cos(2 * np.pi * dt.weekday() / 7.0)
                month_sin = np.sin(2 * np.pi * dt.month / 12.0)
                month_cos = np.cos(2 * np.pi * dt.month / 12.0)

                vec[0] = hour_sin
                vec[1] = hour_cos
                vec[2] = dow_sin
                vec[3] = dow_cos
                vec[4] = month_sin
                vec[5] = month_cos

                ts_hash = int(hashlib.md5(created_at.encode()).hexdigest(), 16)
                for i in range(6, min(38, self._dim)):
                    idx = (ts_hash + i * 31) % self._dim
                    vec[idx] += 0.5
            except Exception:
                pass

        if drawer_id:
            dh = int(hashlib.md5(drawer_id.encode()).hexdigest(), 16)
            for i in range(40, min(80, self._dim)):
                idx = (dh + i * 37) % self._dim
                vec[idx] += 0.3

        if sequence_position > 0:
            pos_signal = 1.0 / (1.0 + sequence_position)
            for i in range(80, min(120, self._dim)):
                vec[(sequence_position * 13 + i * 41) % self._dim] += pos_signal

        norm = np.linalg.norm(vec)
        if norm > 1e-8:
            vec /= norm
        return vec


class EmotionalEncoder:
    """情感投影编码器 — 将PAD三维情感编码为128维向量"""

    def __init__(self, dim: int = 128):
        self._dim = dim

    def encode(self, valence: float = 0.0, arousal: float = 0.0,
               dominance: float = 0.5) -> np.ndarray:
        vec = np.zeros(self._dim, dtype=np.float32)

        v = max(-1.0, min(1.0, valence))
        a = max(0.0, min(1.0, arousal))
        d = max(0.0, min(1.0, dominance))

        vec[0] = v
        vec[1] = a
        vec[2] = d

        for i in range(3, min(20, self._dim)):
            phase = (i - 3) * np.pi / 17
            vec[i] = v * np.sin(phase) + a * np.cos(phase)

        for i in range(20, min(50, self._dim)):
            idx = int(abs(v * 10 + a * 5) * (self._dim - 20))
            j = (idx + i * 7) % (self._dim - 20) + 20
            vec[j] += 0.3

        for i in range(50, min(90, self._dim)):
            if a > 0.3:
                vec[i] = a * 0.5 * (1.0 if v >= 0 else -1.0)

        for i in range(90, min(self._dim, 128)):
            vec[i] = d * 0.4

        norm = np.linalg.norm(vec)
        if norm > 1e-8:
            vec /= norm
        return vec


class CausalEncoder:
    """因果投影编码器 — 将因果链摘要编码为256维向量"""

    def __init__(self, dim: int = 256):
        self._dim = dim
        self._embed = get_embedding_service()

    def encode(self, causal_summary: str = "") -> np.ndarray:
        vec = np.zeros(self._dim, dtype=np.float32)
        if not causal_summary:
            return vec

        try:
            emb = self._embed.embed(causal_summary)
            if emb:
                for i, v in enumerate(emb[:min(len(emb), self._dim)]):
                    vec[i] = v
                norm = np.linalg.norm(vec)
                if norm > 1e-8:
                    vec /= norm
                return vec
        except Exception as e:
            logger.debug(f"Causal encoding failed: {e}")

        h = int(hashlib.md5(causal_summary.encode()).hexdigest(), 16)
        for i in range(self._dim):
            idx = (h + i * 67) % self._dim
            bit = (h >> (i % 64)) & 1
            vec[idx] += 0.3 if bit else -0.3
        norm = np.linalg.norm(vec)
        if norm > 1e-8:
            vec /= norm
        return vec


class SourceEncoder:
    """来源投影编码器 — 将agent_id+channel+session编码为128维向量"""

    def __init__(self, dim: int = 128):
        self._dim = dim

    def encode(self, source: str = "", created_by: str = "",
               session_id: str = "") -> np.ndarray:
        vec = np.zeros(self._dim, dtype=np.float32)

        parts = [source, created_by, session_id]
        for part_idx, part in enumerate(parts):
            if not part:
                continue
            h = int(hashlib.md5(part.encode()).hexdigest(), 16)
            offset = part_idx * 40
            for i in range(min(40, self._dim - offset)):
                idx = offset + (h + i * 43) % min(40, self._dim - offset)
                if 0 <= idx < self._dim:
                    bit = (h >> (i % 64)) & 1
                    vec[idx] += 0.4 if bit else -0.4

        norm = np.linalg.norm(vec)
        if norm > 1e-8:
            vec /= norm
        return vec


class HolographicEncoder:
    """全息编码器 — 统一入口，将MemoryItem编码为多维度投影Hologram"""

    def __init__(self):
        self.temporal = TemporalEncoder(dim=PROJECTION_DIMS["temporal"])
        self.emotional = EmotionalEncoder(dim=PROJECTION_DIMS["emotional"])
        self.causal = CausalEncoder(dim=PROJECTION_DIMS["causal"])
        self.source = SourceEncoder(dim=PROJECTION_DIMS["source"])
        self._embed = get_embedding_service()

    def encode(self, raw_text: str, created_at: str = "",
               drawer_id: str = "", sequence_position: int = 0,
               valence: float = 0.0, arousal: float = 0.0,
               dominance: float = 0.5,
               causal_summary: str = "",
               source_type: str = "", created_by: str = "",
               session_id: str = "", tags: list | None = None) -> Hologram:
        import uuid

        projections = {}

        semantic_vec = self._embed.embed(raw_text)
        if semantic_vec:
            projections["semantic"] = np.array(semantic_vec, dtype=np.float32)

        projections["temporal"] = self.temporal.encode(
            created_at, drawer_id, sequence_position
        )
        projections["emotional"] = self.emotional.encode(
            valence, arousal, dominance
        )
        projections["causal"] = self.causal.encode(causal_summary)
        projections["source"] = self.source.encode(
            source_type, created_by, session_id
        )

        return Hologram(
            item_id=str(uuid.uuid4()),
            projections=projections,
        )

    def encode_existing(self, item_id: str, raw_text: str, created_at: str = "",
                        drawer_id: str = "", **kwargs) -> Hologram:
        h = self.encode(
            raw_text=raw_text,
            created_at=created_at,
            drawer_id=drawer_id,
            sequence_position=kwargs.get("sequence_position", 0),
            valence=kwargs.get("valence", 0.0),
            arousal=kwargs.get("arousal", 0.0),
            dominance=kwargs.get("dominance", 0.5),
            causal_summary=kwargs.get("causal_summary", ""),
            source_type=kwargs.get("source_type", ""),
            created_by=kwargs.get("created_by", ""),
            session_id=kwargs.get("session_id", ""),
            tags=kwargs.get("tags", []),
        )
        h.item_id = item_id
        return h


_holographic_encoder: Optional[HolographicEncoder] = None


def get_holographic_encoder() -> HolographicEncoder:
    global _holographic_encoder
    if _holographic_encoder is None:
        _holographic_encoder = HolographicEncoder()
    return _holographic_encoder
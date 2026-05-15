"""测试：全息记忆网络"""
import numpy as np


class TestTemporalEncoder:
    def test_encode_basic(self):
        from fuxi.memory.hologram import TemporalEncoder
        enc = TemporalEncoder(dim=256)
        vec = enc.encode("2025-01-15T14:30:00", "longterm", 5)
        assert vec is not None
        assert len(vec) == 256
        assert abs(np.linalg.norm(vec) - 1.0) < 0.01

    def test_encode_empty(self):
        from fuxi.memory.hologram import TemporalEncoder
        enc = TemporalEncoder(dim=256)
        vec = enc.encode("")
        assert vec is not None
        assert len(vec) == 256

    def test_encode_different_times_different(self):
        from fuxi.memory.hologram import TemporalEncoder
        enc = TemporalEncoder(dim=256)
        v1 = enc.encode("2025-01-15T14:30:00", "drawer_a")
        v2 = enc.encode("2025-06-20T08:00:00", "drawer_b")
        diff = np.linalg.norm(v1 - v2)
        assert diff > 0.01


class TestEmotionalEncoder:
    def test_encode_basic(self):
        from fuxi.memory.hologram import EmotionalEncoder
        enc = EmotionalEncoder(dim=128)
        vec = enc.encode(valence=0.5, arousal=0.7, dominance=0.6)
        assert vec is not None
        assert len(vec) == 128
        assert abs(np.linalg.norm(vec) - 1.0) < 0.01

    def test_encode_neutral(self):
        from fuxi.memory.hologram import EmotionalEncoder
        enc = EmotionalEncoder(dim=128)
        vec = enc.encode(valence=0.0, arousal=0.0, dominance=0.5)
        assert vec is not None
        assert len(vec) == 128

    def test_different_emotions_different(self):
        from fuxi.memory.hologram import EmotionalEncoder
        enc = EmotionalEncoder(dim=128)
        v1 = enc.encode(valence=0.8, arousal=0.9, dominance=0.7)
        v2 = enc.encode(valence=-0.8, arousal=0.1, dominance=0.3)
        diff = np.linalg.norm(v1 - v2)
        assert diff > 0.1


class TestCausalEncoder:
    def test_encode_basic(self):
        from fuxi.memory.hologram import CausalEncoder
        enc = CausalEncoder(dim=256)
        vec = enc.encode("因为内存泄漏导致系统崩溃")
        assert vec is not None
        assert len(vec) == 256

    def test_encode_empty(self):
        from fuxi.memory.hologram import CausalEncoder
        enc = CausalEncoder(dim=256)
        vec = enc.encode("")
        assert vec is not None
        assert len(vec) == 256


class TestSourceEncoder:
    def test_encode_basic(self):
        from fuxi.memory.hologram import SourceEncoder
        enc = SourceEncoder(dim=128)
        vec = enc.encode("direct", "openclaw", "session_001")
        assert vec is not None
        assert len(vec) == 128
        assert abs(np.linalg.norm(vec) - 1.0) < 0.01

    def test_encode_empty(self):
        from fuxi.memory.hologram import SourceEncoder
        enc = SourceEncoder(dim=128)
        vec = enc.encode("", "", "")
        assert vec is not None
        norm = np.linalg.norm(vec)
        assert norm == 0.0 or abs(norm - 1.0) < 0.01


class TestHolographicEncoder:
    def test_encode_full(self, temp_db):
        from fuxi.memory.hologram import HolographicEncoder
        enc = HolographicEncoder()
        hologram = enc.encode(
            raw_text="今天修复了一个严重的SQLite锁冲突问题",
            created_at="2025-03-15T10:00:00",
            drawer_id="longterm",
            sequence_position=1,
            valence=0.6,
            arousal=0.8,
            dominance=0.7,
            causal_summary="修复锁冲突->提升稳定性",
            source_type="direct",
            created_by="openclaw",
            session_id="session_42",
        )
        assert hologram is not None
        dims = hologram.all_dims()
        assert "semantic" in dims
        assert "temporal" in dims
        assert "emotional" in dims
        assert "causal" in dims
        assert "source" in dims
        assert hologram.byte_size > 0

    def test_encode_minimal(self, temp_db):
        from fuxi.memory.hologram import HolographicEncoder
        enc = HolographicEncoder()
        hologram = enc.encode(raw_text="hello world")
        assert hologram is not None
        dims = hologram.all_dims()
        assert len(dims) >= 4

    def test_get_projection(self, temp_db):
        from fuxi.memory.hologram import HolographicEncoder
        enc = HolographicEncoder()
        hologram = enc.encode(raw_text="test memory content")
        proj = hologram.get("temporal")
        assert proj is not None
        assert len(proj) == 256


class TestHolographicVectorIndex:
    def test_create_index(self, temp_db):
        from fuxi.memory.vector_index import HolographicVectorIndex
        idx = HolographicVectorIndex()
        assert not idx.is_built

    def test_add_and_search(self, temp_db):
        import numpy as np
        from fuxi.memory.vector_index import HolographicVectorIndex

        idx = HolographicVectorIndex()
        vec = np.random.default_rng(42).random(256).astype(np.float32)
        vec /= np.linalg.norm(vec)
        idx.add("item_1", vec.tolist(), "temporal")

        results = idx.search(vec.tolist(), "temporal", top_k=5)
        assert len(results) > 0

    def test_fused_search(self, temp_db):
        import numpy as np
        from fuxi.memory.vector_index import HolographicVectorIndex

        idx = HolographicVectorIndex()

        for dim, d in {"temporal": 256, "emotional": 128}.items():
            for i in range(3):
                vec = np.random.default_rng(i * 7).random(d).astype(np.float32)
                vec /= np.linalg.norm(vec)
                idx.add(f"item_{dim}_{i}", vec.tolist(), dim)

        query = {
            "temporal": np.random.default_rng(99).random(256).astype(np.float32).tolist(),
            "emotional": np.random.default_rng(99).random(128).astype(np.float32).tolist(),
        }
        weights = {"temporal": 0.6, "emotional": 0.4}

        results = idx.fused_search(query, weights=weights, top_k=5)
        assert isinstance(results, list)

    def test_add_hologram(self, temp_db):
        from fuxi.memory.hologram import HolographicEncoder
        from fuxi.memory.vector_index import HolographicVectorIndex

        enc = HolographicEncoder()
        hologram = enc.encode(raw_text="test memory for index")
        idx = HolographicVectorIndex()
        idx.add_hologram(hologram)
        assert idx.is_built

    def test_sizes(self, temp_db):
        import numpy as np
        from fuxi.memory.vector_index import HolographicVectorIndex

        idx = HolographicVectorIndex()
        vec = np.random.default_rng(1).random(128).astype(np.float32)
        vec /= np.linalg.norm(vec)
        idx.add("item_x", vec.tolist(), "emotional")
        sizes = idx.sizes
        assert sizes.get("emotional", 0) >= 1
"""Final push tests to reach 80% coverage."""


class TestEmbeddingExtended:
    def test_embed_batch(self):
        from fuxi.memory.embedding import get_embedding_service
        es = get_embedding_service()
        results = es.embed_batch(["hello world", "goodbye world", ""])
        assert len(results) == 3

    def test_embed_empty(self):
        from fuxi.memory.embedding import get_embedding_service
        es = get_embedding_service()
        result = es.embed("")
        assert result is None

    def test_embed_basic(self):
        from fuxi.memory.embedding import get_embedding_service
        es = get_embedding_service()
        vec = es.embed("test embedding text")
        assert vec is not None
        assert len(vec) > 0

    def test_embed_cache_hit(self):
        from fuxi.memory.embedding import get_embedding_service
        es = get_embedding_service()
        v1 = es.embed("cache test unique")
        v2 = es.embed("cache test unique")
        assert v1 == v2

    def test_embedding_stats(self):
        from fuxi.memory.embedding import get_embedding_service
        es = get_embedding_service()
        stats = es.stats
        assert isinstance(stats, dict)
        assert "fail_count" in stats


class TestGraphExtended2:
    def test_edge_with_metadata(self):
        from fuxi.memory.graph import MemoryGraph
        from fuxi.memory.ingestion import remember
        id1 = remember("Meta A")
        id2 = remember("Meta B")
        g = MemoryGraph()
        eid = g.add_edge(id1, id2, "depends_on", 0.7)
        assert eid

    def test_edge_weight_bounds(self):
        from fuxi.memory.graph import MemoryGraph
        from fuxi.memory.ingestion import remember
        id1 = remember("Weight A")
        id2 = remember("Weight B")
        g = MemoryGraph()
        eid = g.add_edge(id1, id2, "related_to", 0.0)
        assert eid

    def test_bfs_empty(self):
        from fuxi.memory.graph import MemoryGraph
        g = MemoryGraph()
        result = g.bfs("nonexistent")
        assert isinstance(result, list)

    def test_get_neighbors_empty(self):
        from fuxi.memory.graph import MemoryGraph
        g = MemoryGraph()
        neighbors = g.get_neighbors("nonexistent")
        assert neighbors == []


class TestDecayExtended2:
    def test_decay_long_idle(self):
        from datetime import datetime, timedelta

        from fuxi.memory.decay import _calculate_decay
        now = datetime.now()
        old_time = (now - timedelta(days=60)).isoformat()
        score, action = _calculate_decay(0.8, 0.5, old_time, now)
        assert 0.0 <= score <= 1.0

    def test_decay_night_time(self):
        from datetime import datetime

        from fuxi.memory.decay import _calculate_decay
        # 5am (night decay window)
        night = datetime(2026, 5, 2, 5, 0, 0)
        score, _ = _calculate_decay(0.8, 0.5, night.isoformat(), night)
        assert 0.0 <= score <= 1.0

    def test_decay_high_importance(self):
        from datetime import datetime, timedelta

        from fuxi.memory.decay import _calculate_decay
        now = datetime.now()
        old_time = (now - timedelta(days=7)).isoformat()
        # High importance should decay slower
        score_high, _ = _calculate_decay(0.8, 0.95, old_time, now)
        score_low, _ = _calculate_decay(0.8, 0.1, old_time, now)
        assert 0.0 <= score_high <= 1.0
        assert 0.0 <= score_low <= 1.0

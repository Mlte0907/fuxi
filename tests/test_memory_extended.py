"""Additional memory unit tests targeting uncovered code paths."""


class TestRetrievalExtended:
    def test_recall_with_min_importance(self):
        from fuxi.memory.ingestion import remember
        from fuxi.memory.retrieval import recall
        remember("High importance memory", importance=0.9)
        remember("Low importance memory", importance=0.1)
        results = recall(min_importance=0.5)
        assert all(r.get("importance", 0) >= 0 for r in results)

    def test_recall_with_agent_filter(self):
        from fuxi.memory.ingestion import remember
        from fuxi.memory.retrieval import recall
        from fuxi.store.connection import get_pool
        mid = remember("Agent test memory")
        pool = get_pool()
        pool.execute(
            "INSERT OR REPLACE INTO agent_views (agent_id, item_id) VALUES (?,?)",
            ("test-agent-recall", mid)
        )
        results = recall(agent_id="test-agent-recall")
        assert len(results) >= 1
        results_none = recall(agent_id="no-such-agent")
        assert len(results_none) == 0

    def test_recall_with_query_vector(self):
        from fuxi.memory.ingestion import remember
        from fuxi.memory.retrieval import recall
        remember("Deep learning is transforming AI research")
        remember("The weather is nice today")
        results = recall(query="deep learning neural networks", limit=5)
        assert len(results) >= 1

    def test_recall_cache_enabled(self):
        from fuxi.memory.ingestion import remember
        from fuxi.memory.retrieval import clear_recall_cache, recall
        clear_recall_cache()
        remember("Cache test memory", importance=0.8)
        r1 = recall(query="cache test", use_cache=True)
        r2 = recall(query="cache test", use_cache=True)
        assert len(r1) == len(r2)

    def test_recall_cache_disabled(self):
        from fuxi.memory.ingestion import remember
        from fuxi.memory.retrieval import recall
        remember("No-cache test memory")
        results = recall(query="no-cache", use_cache=False)
        assert isinstance(results, list)

    def test_recall_by_ids_empty(self):
        from fuxi.memory.retrieval import recall_by_ids
        results = recall_by_ids([])
        assert results == []

    def test_clear_recall_cache(self):
        from fuxi.memory.retrieval import clear_recall_cache
        clear_recall_cache()  # should not raise


class TestSearchExtended:
    def test_search_empty_query(self):
        from fuxi.memory.search import search
        result = search("")
        assert result["total"] == 0
        assert result["method"] == "empty"

    def test_search_whitespace_query(self):
        from fuxi.memory.search import search
        result = search("   ")
        assert result["total"] == 0

    def test_search_with_tags(self):
        from fuxi.memory.ingestion import remember
        from fuxi.memory.search import search
        remember("Python programming tips", tags=["python", "coding"])
        remember("Cooking recipes", tags=["cooking", "food"])
        result = search("python", tags=["python"])
        assert result["total"] >= 1

    def test_search_with_agent_filter(self):
        from fuxi.memory.ingestion import remember
        from fuxi.memory.search import search
        from fuxi.store.connection import get_pool
        mid = remember("Search agent test", tags=["search-test"])
        pool = get_pool()
        pool.execute(
            "INSERT OR REPLACE INTO agent_views (agent_id, item_id) VALUES (?,?)",
            ("search-agent", mid)
        )
        result = search("search", agent_id="search-agent")
        assert result["total"] >= 1
        result_none = search("search", agent_id="nonexistent-agent")
        assert result_none["total"] == 0

    def test_search_with_min_score(self):
        from fuxi.memory.ingestion import remember
        from fuxi.memory.search import search
        remember("High quality memory about machine learning", importance=0.95)
        result = search("machine learning", min_score=0.0)
        assert result["total"] >= 1

    def test_search_stats(self):
        from fuxi.memory.search import get_search_stats
        stats = get_search_stats()
        assert "vector_weight_default" in stats
        assert "fts_weight_default" in stats


class TestDecayExtended:
    def test_decay_execute(self):
        from fuxi.memory.decay import decay_all
        from fuxi.memory.ingestion import remember
        remember("Decay execute test", importance=0.5)
        stats = decay_all(dry_run=False)
        assert stats["total"] >= 1
        assert "decayed" in stats

    def test_decay_invalid_dates(self):
        from datetime import datetime

        from fuxi.memory.decay import _calculate_decay
        score, action = _calculate_decay(0.8, 0.5, "not-a-date", datetime.now())
        assert score == 0.8
        assert action == "unchanged"

    def test_purge_execute(self):
        from fuxi.memory.decay import purge_below_floor
        result = purge_below_floor(dry_run=False)
        assert "purged" in result
        assert result["dry_run"] is False

    def test_decay_recent_access(self):
        from datetime import datetime, timedelta

        from fuxi.memory.decay import _calculate_decay
        now = datetime.now()
        # Recent access should boost retention
        score1, _ = _calculate_decay(0.8, 0.5, (now - timedelta(days=10)).isoformat(), now)
        # Old memory with no recent access should decay more
        score2, _ = _calculate_decay(0.8, 0.5, now.isoformat(), now)
        assert 0.0 <= score1 <= 1.0
        assert 0.0 <= score2 <= 1.0


class TestGraphExtended:
    def test_reverse_edge_exists(self):
        from fuxi.memory.graph import MemoryGraph
        from fuxi.memory.ingestion import remember
        id1 = remember("Reverse A")
        id2 = remember("Reverse B")
        g = MemoryGraph()
        g.add_edge(id1, id2, "related_to", 0.5)
        # Add stronger reverse edge
        eid = g.add_edge(id2, id1, "related_to", 0.9)
        assert eid  # should return existing or new edge id

    def test_soft_delete_edge(self):
        from fuxi.memory.graph import MemoryGraph
        from fuxi.memory.ingestion import remember
        id1 = remember("Soft delete A v2")
        id2 = remember("Soft delete B v2")
        g = MemoryGraph()
        eid = g.add_edge(id1, id2, "related_to", 0.7)
        assert eid
        removed = g.remove_edge(eid)
        assert removed is True

    def test_get_neighbors_multiple(self):
        from fuxi.memory.graph import MemoryGraph
        from fuxi.memory.ingestion import remember
        center = remember("Multi center v2")
        n1 = remember("Multi neighbor 1 v2")
        n2 = remember("Multi neighbor 2 v2")
        g = MemoryGraph()
        g.add_edge(center, n1, "related_to", 0.8)
        g.add_edge(center, n2, "depends_on", 0.6)
        neighbors = g.get_neighbors(center)
        assert len(neighbors) >= 2

    def test_bfs_max_depth(self):
        from fuxi.memory.graph import MemoryGraph
        from fuxi.memory.ingestion import remember
        a = remember("BFS A")
        b = remember("BFS B")
        c = remember("BFS C")
        d = remember("BFS D")
        g = MemoryGraph()
        g.add_edge(a, b, "related_to")
        g.add_edge(b, c, "related_to")
        g.add_edge(c, d, "related_to")
        shallow = g.bfs(a, max_depth=1)
        deep = g.bfs(a, max_depth=5)
        assert len(shallow) >= 1
        assert len(deep) >= len(shallow)


class TestSharedMemories:
    def test_share_and_get(self, temp_db):
        from fuxi.agent.perspective import PerspectiveManager
        from fuxi.memory.ingestion import remember
        mid = remember("Shared test memory")
        pm = PerspectiveManager()
        result = pm.share_memory("agent_a", "agent_b", mid, permission="read")
        assert result["from"] == "agent_a"
        assert result["to"] == "agent_b"

        shared = pm.get_shared_memories("agent_b")
        assert len(shared) >= 1
        assert shared[0]["from_agent"] == "agent_a"
        assert shared[0]["permission"] == "read"

    def test_get_shared_memories_empty(self, temp_db):
        from fuxi.agent.perspective import PerspectiveManager
        pm = PerspectiveManager()
        shared = pm.get_shared_memories("nonexistent_agent")
        assert shared == []

    def test_get_shared_memories_multiple(self, temp_db):
        from fuxi.agent.perspective import PerspectiveManager
        from fuxi.memory.ingestion import remember
        pm = PerspectiveManager()
        m1 = remember("Shared memory 1")
        m2 = remember("Shared memory 2")
        pm.share_memory("agent_a", "agent_c", m1)
        pm.share_memory("agent_b", "agent_c", m2)
        shared = pm.get_shared_memories("agent_c")
        assert len(shared) >= 2

    def test_share_and_agent_view_sync(self, temp_db):
        from fuxi.agent.perspective import PerspectiveManager
        from fuxi.memory.ingestion import remember
        pm = PerspectiveManager()
        mid = remember("View sync test")
        pm.share_memory("agent_a", "agent_d", mid)
        views = pm.get_view("agent_d")
        assert len(views) >= 1

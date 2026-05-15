"""测试：记忆核心（摄入/召回/搜索/衰减/图谱）"""
import pytest


@pytest.mark.usefixtures("temp_db")
class TestIngestion:
    def test_remember_basic(self):
        from fuxi.memory.ingestion import remember
        item_id = remember("Hello World", drawer_id="default")
        assert item_id
        assert len(item_id) == 36  # UUID

    def test_remember_with_tags(self):
        from fuxi.memory.ingestion import remember
        item_id = remember("Tagged memory", tags=["test", "pytest"])
        assert item_id

    def test_dedup(self):
        from fuxi.memory.ingestion import remember
        id1 = remember("Unique memory for dedup test")
        id2 = remember("Unique memory for dedup test")
        assert id1 == id2  # 应该返回相同ID

    def test_empty_text_raises(self):
        from fuxi.memory.ingestion import remember
        with pytest.raises(ValueError):
            remember("")

    def test_emotion_valence(self):
        from fuxi.memory.ingestion import remember
        item_id = remember("Sad memory", emotion_valence=-0.5)
        from fuxi.memory.retrieval import recall_by_ids
        results = recall_by_ids([item_id])
        assert results[0]["emotion_valence"] == -0.5


@pytest.mark.usefixtures("temp_db")
class TestRetrieval:
    def test_recall_empty(self):
        from fuxi.memory.retrieval import recall
        results = recall(limit=10)
        assert isinstance(results, list)

    def test_recall_with_data(self):
        from fuxi.memory.ingestion import remember
        from fuxi.memory.retrieval import recall
        remember("Memory A for recall", importance=0.9)
        remember("Memory B for recall", importance=0.3)
        results = recall(limit=5)
        assert len(results) >= 2

    def test_recall_by_ids(self):
        from fuxi.memory.ingestion import remember
        from fuxi.memory.retrieval import recall_by_ids
        id1 = remember("Test recall by id")
        results = recall_by_ids([id1])
        assert len(results) == 1
        assert results[0]["id"] == id1

    def test_recall_context(self):
        from fuxi.memory.ingestion import remember
        from fuxi.memory.retrieval import recall_context
        for i in range(5):
            remember(f"Context memory {i}", importance=0.5 + i * 0.1)
        ctx = recall_context(budget=3)
        assert len(ctx) <= 3


@pytest.mark.usefixtures("temp_db")
class TestSearch:
    def test_search_basic(self):
        from fuxi.memory.ingestion import remember
        from fuxi.memory.search import search
        remember("Python is a great programming language")
        remember("JavaScript runs in browsers")
        result = search("Python")
        assert result["total"] >= 1

    def test_search_no_results(self):
        from fuxi.memory.search import search
        result = search("xyz_nonexistent_term_12345")
        # 无意义查询可能仍有低分向量匹配，但分数应很低
        for r in result["results"]:
            assert r["search_score"] < 0.4

    def test_search_with_drawer_filter(self):
        from fuxi.memory.ingestion import remember
        from fuxi.memory.search import search
        remember("Drawer A memory", drawer_id="default")
        remember("Drawer B memory", drawer_id="longterm")
        result = search("Drawer", drawer_id="longterm")
        assert result["total"] >= 1


@pytest.mark.usefixtures("temp_db")
class TestDecay:
    def test_decay_dry_run(self):
        from fuxi.memory.decay import decay_all
        from fuxi.memory.ingestion import remember
        remember("Memory for decay test", importance=0.5)
        stats = decay_all(dry_run=True)
        assert stats["total"] >= 1
        assert "decayed" in stats

    def test_purge_candidates(self):
        from fuxi.memory.decay import purge_below_floor
        result = purge_below_floor(dry_run=True)
        assert "purged" in result
        assert result["dry_run"] is True


@pytest.mark.usefixtures("temp_db")
class TestGraph:
    def test_add_edge(self):
        from fuxi.memory.graph import MemoryGraph
        from fuxi.memory.ingestion import remember
        id1 = remember("Node A")
        id2 = remember("Node B")
        g = MemoryGraph()
        edge_id = g.add_edge(id1, id2, "related_to", 0.8)
        assert edge_id

    def test_invalid_edge_type(self):
        from fuxi.memory.graph import MemoryGraph
        from fuxi.memory.ingestion import remember
        id1 = remember("Node X")
        id2 = remember("Node Y")
        g = MemoryGraph()
        with pytest.raises(ValueError):
            g.add_edge(id1, id2, "invalid_type")

    def test_get_neighbors(self):
        from fuxi.memory.graph import MemoryGraph
        from fuxi.memory.ingestion import remember
        id1 = remember("Center node")
        id2 = remember("Neighbor node")
        g = MemoryGraph()
        g.add_edge(id1, id2, "related_to", 0.9)
        neighbors = g.get_neighbors(id1)
        assert len(neighbors) >= 1

    def test_bfs(self):
        from fuxi.memory.graph import MemoryGraph
        from fuxi.memory.ingestion import remember
        id1 = remember("BFS start")
        id2 = remember("BFS level 1")
        id3 = remember("BFS level 2")
        g = MemoryGraph()
        g.add_edge(id1, id2, "related_to")
        g.add_edge(id2, id3, "depends_on")
        result = g.bfs(id1, max_depth=2)
        assert len(result) >= 1

    def test_graph_stats(self):
        from fuxi.memory.graph import MemoryGraph
        g = MemoryGraph()
        stats = g.get_graph_stats()
        assert "total_edges" in stats
        assert "by_type" in stats

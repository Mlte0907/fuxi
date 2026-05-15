"""Final graph tests to push coverage past 80%."""


class TestGraphFinal:
    def test_causal_chain(self, temp_db):
        from fuxi.memory.graph import MemoryGraph
        from fuxi.memory.ingestion import remember
        a = remember("Cause symptom")
        b = remember("Intermediate effect")
        c = remember("Final outcome")
        g = MemoryGraph()
        g.add_edge(a, b, "causes", 0.9)
        g.add_edge(b, c, "enables", 0.8)
        chain = g.causal_chain(a, max_length=3)
        assert len(chain) >= 1
        assert chain[0]["id"] == a

    def test_causal_chain_max_length(self, temp_db):
        from fuxi.memory.graph import MemoryGraph
        from fuxi.memory.ingestion import remember
        a = remember("Chain start")
        b = remember("Chain mid")
        g = MemoryGraph()
        g.add_edge(a, b, "depends_on", 0.7)
        g.add_edge(b, remember("Chain end"), "causes", 0.6)
        chain = g.causal_chain(a, max_length=1)
        assert len(chain) == 1

    def test_get_neighbors_with_edge_type(self, temp_db):
        from fuxi.memory.graph import MemoryGraph
        from fuxi.memory.ingestion import remember
        src = remember("Type Src")
        tgt = remember("Type Tgt")
        g = MemoryGraph()
        g.add_edge(src, tgt, "depends_on", 0.8)
        neighbors = g.get_neighbors(src, edge_type="depends_on")
        assert len(neighbors) >= 1
        # Wrong type should return empty
        neighbors_wrong = g.get_neighbors(src, edge_type="related_to")
        assert len(neighbors_wrong) == 0

    def test_get_neighbors_incoming(self, temp_db):
        from fuxi.memory.graph import MemoryGraph
        from fuxi.memory.ingestion import remember
        src = remember("Incoming Src")
        tgt = remember("Incoming Tgt")
        g = MemoryGraph()
        g.add_edge(src, tgt, "related_to", 0.9)
        # Get incoming from target's perspective
        incoming = g.get_neighbors(tgt, direction="incoming")
        assert len(incoming) >= 1

    def test_bfs_with_edge_types(self, temp_db):
        from fuxi.memory.graph import MemoryGraph
        from fuxi.memory.ingestion import remember
        a = remember("BFS unique start node abc123")
        b = remember("BFS distinct target xyz789")
        g = MemoryGraph()
        g.add_edge(a, b, "related_to", 0.8)
        result = g.bfs(a, edge_types=["related_to"], max_depth=2)
        assert len(result) >= 1

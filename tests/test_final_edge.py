"""Edge case tests to push coverage past 80%."""


class TestDecayWrite:
    def test_decay_force_write(self):
        """Force decay to actually write — covers lines 34, 40."""
        from fuxi.memory.decay import decay_all
        from fuxi.memory.ingestion import remember
        from fuxi.store.connection import get_pool

        mid = remember("Decay force test", importance=0.5)
        # Set a decay_score that will change significantly
        pool = get_pool()
        pool.execute("UPDATE items SET decay_score = 0.1 WHERE id = ?", (mid,))
        pool.execute("UPDATE items SET updated_at = '2020-01-01T00:00:00' WHERE id = ?", (mid,))

        stats = decay_all(dry_run=False)
        assert stats["total"] >= 1

    def test_decay_purge_write(self):
        """Force purge to actually archive — covers lines 121-124."""
        from fuxi.config import config
        from fuxi.memory.decay import purge_below_floor
        from fuxi.memory.ingestion import remember
        from fuxi.store.connection import get_pool

        mid = remember("Purge force test", importance=0.1)
        # Set decay_score below floor to trigger purge
        pool = get_pool()
        pool.execute("UPDATE items SET decay_score = ? WHERE id = ?",
                     (config.decay_floor - 0.01, mid))

        result = purge_below_floor(dry_run=False)
        assert result["purged"] >= 1
        assert result["dry_run"] is False


class TestSearchEdge:
    def test_search_empty_results(self):
        """Cover line 117: no results path."""
        from fuxi.memory.search import search
        result = search("xyznonexistent_12345_nomatch")
        assert isinstance(result, dict)
        # Must have results key even when empty
        assert "results" in result


class TestCausalChainEdge:
    def test_causal_chain_multihop(self):
        """Cover line 153: second iteration of causal_chain (traces backwards)."""
        from fuxi.memory.graph import MemoryGraph
        from fuxi.memory.ingestion import remember
        c = remember("Cause root v2")
        b = remember("Middle effect v2")
        a = remember("Final outcome v2")
        g = MemoryGraph()
        # Chain: C causes B causes A. causal_chain(A) traces back to C
        g.add_edge(c, b, "causes", 0.9)
        g.add_edge(b, a, "causes", 0.8)
        chain = g.causal_chain(a, max_length=5)
        assert len(chain) >= 2

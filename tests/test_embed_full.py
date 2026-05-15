"""Complete coverage for embedding module — both API and local paths."""


class TestEmbeddingFull:
    def test_local_embed_direct(self):
        """Cover _local_embed path directly."""
        from fuxi.memory.embedding import get_embedding_service
        es = get_embedding_service()
        vec = es._local_embed("test local embedding")
        assert vec is not None
        assert len(vec) > 0

    def test_call_api_no_key(self):
        """Cover no-key early return path."""
        from fuxi.config import config
        from fuxi.memory.embedding import get_embedding_service
        es = get_embedding_service()
        old_key = config.siliconflow_key
        config.siliconflow_key = ""
        try:
            result = es._call_api("no key test")
            assert result is None
        finally:
            config.siliconflow_key = old_key

    def test_call_api_with_key(self):
        """Cover full API call success path."""
        import pytest
        from fuxi.config import config
        from fuxi.memory.embedding import get_embedding_service
        if not config.siliconflow_key:
            pytest.skip("siliconflow_key not configured")
        es = get_embedding_service()
        vec = es._call_api("api success test")
        assert vec is not None
        assert len(vec) == 1024

    def test_embed_circuit_open_path(self):
        """Cover local embed path when circuit is open."""
        from fuxi.memory.embedding import get_embedding_service
        es = get_embedding_service()
        es._circuit_open = True
        try:
            vec = es.embed("circuit open test")
            assert vec is not None
        finally:
            es._circuit_open = False

    def test_embed_api_fallback(self):
        """Cover line 33: fallback when _call_api returns None."""
        from fuxi.config import config
        from fuxi.memory.embedding import get_embedding_service
        es = get_embedding_service()
        old_key = config.siliconflow_key
        config.siliconflow_key = ""
        try:
            vec = es.embed("fallback via api none")
            assert vec is not None  # local embed still works
        finally:
            config.siliconflow_key = old_key

    def test_cache_eviction(self):
        """Cover cache eviction when cache exceeds max."""
        from fuxi.config import config
        from fuxi.memory.embedding import get_embedding_service
        es = get_embedding_service()
        # Clear any existing cache entries
        es._cache.clear()
        max_cache = config.embed_cache_max
        # Fill cache to exactly max to trigger eviction on next embed
        for i in range(max_cache):
            es._cache[f"evict_key_{i}"] = [float(i)] * 10
        assert len(es._cache) == max_cache
        # Next embed should trigger eviction
        es._circuit_open = True
        try:
            vec = es.embed("cache eviction trigger")
            assert vec is not None
            assert len(es._cache) <= max_cache
        finally:
            es._circuit_open = False
            es._cache.clear()

    def test_embed_batch(self):
        from fuxi.memory.embedding import get_embedding_service
        es = get_embedding_service()
        results = es.embed_batch(["a", "b", ""])
        assert len(results) == 3
        assert results[2] is None  # empty string

    def test_stats_property(self):
        from fuxi.memory.embedding import get_embedding_service
        es = get_embedding_service()
        s = es.stats
        assert isinstance(s, dict)
        assert "cache_size" in s
        assert "circuit_open" in s

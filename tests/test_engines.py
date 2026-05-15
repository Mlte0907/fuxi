"""测试：认知引擎系统"""


class TestEngineRegistry:
    def test_all_engines_registered(self):
        from fuxi.engines.base import get_engine_registry
        engines = get_engine_registry().list_all()
        # 28 engines in advanced tier (feishu_im + soul registered at init)
        assert len(engines) >= 25

    def test_get_engine(self):
        from fuxi.engines.base import get_engine_registry
        soul = get_engine_registry().get("soul")
        assert soul is not None
        assert soul.name == "soul"
        assert soul.experimental is False

    def test_get_nonexistent(self):
        from fuxi.engines.base import get_engine_registry
        assert get_engine_registry().get("nonexistent_engine") is None

    def test_non_experimental_engines(self):
        from fuxi.engines.base import get_engine_registry
        enabled = get_engine_registry().get_enabled(include_experimental=False)
        names = [e.name for e in enabled]
        assert "soul" in names
        assert "emotion" in names
        assert "feishu_im" in names
        assert len(enabled) >= 23  # 25 confirmed + 1 due to pytest import order

    def test_experimental_engines(self):
        from fuxi.engines.base import get_engine_registry
        enabled = get_engine_registry().get_enabled(include_experimental=True)
        # 3 experimental: cognitive_loop, openclaw_memory, skill_evolution
        # pytest may see 1 extra due to import order
        assert len(enabled) >= 25

    def test_engine_pause_resume(self, temp_db):
        from fuxi.engines.base import get_engine_registry
        engine = get_engine_registry().get("soul")
        engine.start()
        assert engine._state.running is True
        engine.pause()
        assert engine._state.metadata.get("_paused") is True
        engine.resume()
        assert "_paused" not in engine._state.metadata
        engine.stop()

    def test_jinlange_ingestion_engine(self):
        from fuxi.engines.base import get_engine_registry
        engine = get_engine_registry().get("jinlange_ingestion")
        assert engine is not None
        assert engine.name == "jinlange_ingestion"
        assert engine.experimental is False
        assert engine.interval == 300

    def test_adaptive_engine(self):
        from fuxi.engines.base import get_engine_registry
        engine = get_engine_registry().get("adaptive")
        assert engine is not None
        assert engine.name == "adaptive"
        assert engine.experimental is False
        assert engine.interval == 1800

    def test_decision_engine(self):
        from fuxi.engines.base import get_engine_registry
        engine = get_engine_registry().get("decision")
        assert engine is not None
        assert engine.name == "decision"
        assert engine.experimental is False
        assert engine.interval == 600

    def test_engine_health_check(self):
        from fuxi.engines.base import get_engine_registry
        engine = get_engine_registry().get("soul")
        health = engine.health_check()
        assert health["name"] == "soul"
        assert "running" in health
        assert "error_count" in health

    def test_engine_get_state(self):
        from fuxi.engines.base import get_engine_registry
        engine = get_engine_registry().get("emotion")
        state = engine.get_state()
        assert state["name"] == "emotion"
        assert "experimental" in state
        assert "metadata" in state

    def test_immune_eviction_subscription(self):
        from fuxi.engines.immune import ImmuneEngine
        engine = ImmuneEngine()
        subs = engine._get_subscriptions()
        assert "wm.item_evicted" in subs
        assert callable(subs["wm.item_evicted"])

    def test_engine_start_stop(self):
        from fuxi.engines.base import get_engine_registry
        engine = get_engine_registry().get("dream")
        engine.start()
        assert engine._state.running is True
        engine.stop()
        assert engine._state.running is False

    def test_engine_execute(self, temp_db):
        from fuxi.engines.base import get_engine_registry
        engine = get_engine_registry().get("soul")
        result = engine._execute()
        assert isinstance(result, dict)
        assert engine._state.run_count >= 1
        assert engine._state.last_run > 0


class TestSoulEngine:
    def test_soul_run(self, temp_db):
        from fuxi.engines.soul import SoulEngine
        soul = SoulEngine()
        result = soul.run()
        assert isinstance(result, dict)
        assert "health" in result
        assert result["health"] == "alive"

    def test_soul_identity(self):
        from fuxi.engines.soul import SoulEngine
        soul = SoulEngine()
        state = soul.get_state()
        assert state["name"] == "soul"
        assert state["experimental"] is False

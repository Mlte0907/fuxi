"""测试：预测性世界模型"""
import json


class TestWorldModel:
    def test_engine_registered(self):
        from fuxi.engines.base import get_engine_registry
        eng = get_engine_registry().get("world_model")
        assert eng is not None
        assert eng.name == "world_model"
        assert eng.priority == 7
        assert eng.interval == 300

    def test_snapshot_current_state(self, temp_db):
        from fuxi.engines.world_model import PredictiveWorldModel
        from fuxi.store.connection import get_pool
        wm = PredictiveWorldModel()
        snapshot = wm._snapshot_current_state(get_pool())
        assert "engine_health" in snapshot
        assert "emotion" in snapshot
        assert "recent_failures" in snapshot
        assert "memory_trends" in snapshot

    def test_forecast_returns_list(self, temp_db):
        from fuxi.engines.world_model import PredictiveWorldModel
        from fuxi.store.connection import get_pool
        wm = PredictiveWorldModel()
        state = wm._snapshot_current_state(get_pool())
        scenarios = wm._forecast(state)
        assert isinstance(scenarios, list)

    def test_scenario_has_fields(self, temp_db):
        from fuxi.engines.world_model import Scenario
        s = Scenario(
            id="test_1",
            trigger="test trigger",
            description="test description",
            probability=0.7,
            severity=0.5,
        )
        assert s.id == "test_1"
        assert s.trigger == "test trigger"
        assert s.probability == 0.7
        assert s.severity == 0.5
        assert s.hash_key() is not None

    def test_generate_plan(self, temp_db):
        from fuxi.engines.world_model import PredictiveWorldModel, Scenario
        wm = PredictiveWorldModel()
        s = Scenario(
            id="test_1",
            trigger="test trigger",
            description="test",
            probability=0.8,
            severity=0.7,
            suggested_actions=[{"target": "openclaw", "type": "check"}],
        )
        plan = wm._generate_plan(s)
        assert plan.scenario_id == "test_1"
        assert len(plan.suggested_actions) > 0

    def test_run_produces_state(self, temp_db):
        from fuxi.engines.world_model import PredictiveWorldModel
        wm = PredictiveWorldModel()
        wm.start()
        state = wm.run()
        assert "scenarios_generated" in state
        assert "plans_generated" in state
        assert state["v"] == "1.5"

    def test_state_hash_deterministic(self, temp_db):
        from fuxi.engines.world_model import PredictiveWorldModel
        wm = PredictiveWorldModel()
        state = {"recent_failures": [], "emotion": {"valence": 0.0, "frustration": 0.0},
                 "engine_health": {}}
        h1 = wm._hash_state(state)
        h2 = wm._hash_state(state)
        assert h1 == h2

    def test_state_hash_different(self, temp_db):
        from fuxi.engines.world_model import PredictiveWorldModel
        wm = PredictiveWorldModel()
        h1 = wm._hash_state({"recent_failures": [], "engine_health": {}})
        h2 = wm._hash_state({"recent_failures": ["a", "b", "c"], "engine_health": {}})
        assert h1 != h2


class TestPredictionV2:
    def test_engine_registered(self):
        from fuxi.engines.base import get_engine_registry
        eng = get_engine_registry().get("prediction")
        assert eng is not None
        assert eng.name == "prediction"

    def test_run_produces_state_v2(self, temp_db):
        from fuxi.engines.prediction import PredictionEngine
        pe = PredictionEngine()
        pe.start()
        state = pe.run()
        assert "predictions" in state
        assert "trends" in state
        assert "scenario_prefetch" in state
        assert state["v"] == "2.0"

    def test_analyze_trends(self, temp_db):
        from fuxi.engines.prediction import PredictionEngine
        from fuxi.store.connection import get_pool
        pe = PredictionEngine()
        trends = pe._analyze_trends(get_pool())
        assert "ingestion_rate" in trends
        assert "avg_importance_24h" in trends

    def test_prefetch_for_scenario(self, temp_db):
        from fuxi.engines.prediction import PredictionEngine
        from fuxi.store.connection import get_pool
        pe = PredictionEngine()
        results = pe._prefetch_for_scenario(
            get_pool(),
            {"trigger": "test trigger pattern", "probability": 0.8}
        )
        assert isinstance(results, list)
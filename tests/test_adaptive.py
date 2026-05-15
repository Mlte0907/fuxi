"""测试：自适应学习模块"""
import time


class TestAdaptiveParams:
    def test_default_params(self):
        from fuxi.adaptive.params import AdaptiveParams
        params = AdaptiveParams()
        assert params.decay_base == 0.95
        assert params.touch_boost_short == 1.35
        assert params.wm_capacity == 7
        assert params.confidence == 0.5

    def test_clamp_params_lower_bound(self):
        from fuxi.adaptive.params import AdaptiveParams, clamp_params
        params = AdaptiveParams(decay_base=0.5)
        clamped = clamp_params(params)
        assert clamped.decay_base == 0.9  # 被钳制到下界

    def test_clamp_params_upper_bound(self):
        from fuxi.adaptive.params import AdaptiveParams, clamp_params
        params = AdaptiveParams(touch_boost_short=2.0)
        clamped = clamp_params(params)
        assert clamped.touch_boost_short == 1.5  # 被钳制到上界

    def test_clamp_params_multiple(self):
        from fuxi.adaptive.params import AdaptiveParams, clamp_params
        params = AdaptiveParams(
            decay_base=0.5,
            wm_capacity=15,
            attention_replenish_rate=1,
        )
        clamped = clamp_params(params)
        assert clamped.decay_base == 0.9
        assert clamped.wm_capacity == 10
        assert clamped.attention_replenish_rate == 3

    def test_wm_capacity_is_int(self):
        from fuxi.adaptive.params import AdaptiveParams
        params = AdaptiveParams(wm_capacity=5)
        assert isinstance(params.wm_capacity, int)


class TestAdaptiveFeedbackLoop:
    def test_initial_no_evaluation(self):
        from fuxi.adaptive.feedback import AdaptiveFeedbackLoop
        loop = AdaptiveFeedbackLoop()
        result = loop.evaluate({"search_satisfaction": 0.5})
        assert result is None

    def test_evaluate_too_early(self):
        from fuxi.adaptive.feedback import AdaptiveFeedbackLoop
        loop = AdaptiveFeedbackLoop()
        loop.record_adjustment(
            {"decay_base": 0.95}, {"decay_base": 0.96},
            {"search_satisfaction": 0.5}, "test"
        )
        result = loop.evaluate({"search_satisfaction": 0.6})
        assert result is None  # 还未到评估时间窗口

    def test_evaluate_rollback(self):
        from fuxi.adaptive.feedback import AdaptiveFeedbackLoop
        loop = AdaptiveFeedbackLoop()
        loop.record_adjustment(
            {"decay_base": 0.95}, {"decay_base": 0.96},
            {"search_satisfaction": 0.5}, "test adjustment"
        )
        # 手动回退时间戳来模拟超出评估窗口
        loop._adjustment_history[-1]["timestamp"] = time.time() - 7200
        result = loop.evaluate({"search_satisfaction": 0.3})
        assert result is not None
        assert result["action"] == "rollback"

    def test_evaluate_reinforce(self):
        from fuxi.adaptive.feedback import AdaptiveFeedbackLoop
        loop = AdaptiveFeedbackLoop()
        loop.record_adjustment(
            {"decay_base": 0.95}, {"decay_base": 0.96},
            {"search_satisfaction": 0.3}, "test"
        )
        loop._adjustment_history[-1]["timestamp"] = time.time() - 7200
        result = loop.evaluate({"search_satisfaction": 0.7})
        assert result is not None
        assert result["action"] == "reinforce"

    def test_evaluate_maintain(self):
        from fuxi.adaptive.feedback import AdaptiveFeedbackLoop
        loop = AdaptiveFeedbackLoop()
        loop.record_adjustment(
            {"decay_base": 0.95}, {"decay_base": 0.96},
            {"search_satisfaction": 0.5}, "test"
        )
        loop._adjustment_history[-1]["timestamp"] = time.time() - 7200
        result = loop.evaluate({"search_satisfaction": 0.5})
        assert result is not None
        assert result["action"] == "maintain"


class TestAdaptiveEngine:
    def test_engine_registered(self):
        from fuxi.engines.base import get_engine_registry
        engine = get_engine_registry().get("adaptive")
        assert engine is not None
        assert engine.name == "adaptive"
        assert engine.priority == 9
        assert engine.interval == 1800

    def test_run_returns_dict(self, temp_db):
        from fuxi.engines.adaptive import AdaptiveEngine
        engine = AdaptiveEngine()
        result = engine.run()
        assert isinstance(result, dict)
        assert "signals" in result
        assert "adjustments" in result
        assert "current_params" in result

    def test_load_params_default(self):
        from fuxi.engines.adaptive import AdaptiveEngine
        engine = AdaptiveEngine()
        params = engine._load_params()
        assert params.decay_base == 0.95

    def test_save_and_load_params(self, temp_db):
        from fuxi.adaptive.params import AdaptiveParams
        from fuxi.engines.adaptive import AdaptiveEngine
        engine = AdaptiveEngine()
        p = AdaptiveParams(decay_base=0.93, wm_capacity=8)
        engine._save_params(p)
        loaded = engine._load_params()
        assert loaded.decay_base == 0.93
        assert loaded.wm_capacity == 8


class TestBehaviorCollector:
    def test_singleton(self):
        from fuxi.adaptive.signals import get_behavior_collector
        c1 = get_behavior_collector()
        c2 = get_behavior_collector()
        assert c1 is c2

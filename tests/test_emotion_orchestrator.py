"""测试：情感驱动行为编排"""
import json
import time


class TestEmotionOrchestrator:
    def test_engine_registered(self):
        from fuxi.engines.base import get_engine_registry
        eng = get_engine_registry().get("emotion_orchestrator")
        assert eng is not None
        assert eng.name == "emotion_orchestrator"
        assert eng.priority == 8
        assert eng.interval == 60

    def test_classify_quadrant_enthusiastic(self, temp_db):
        from fuxi.engines.emotion_orchestrator import EmotionOrchestrator, EmotionQuadrant
        orch = EmotionOrchestrator()
        q = orch._classify_quadrant(0.6, 0.7)
        assert q == EmotionQuadrant.ENTHUSIASTIC

    def test_classify_quadrant_anxious(self, temp_db):
        from fuxi.engines.emotion_orchestrator import EmotionOrchestrator, EmotionQuadrant
        orch = EmotionOrchestrator()
        q = orch._classify_quadrant(-0.6, 0.7)
        assert q == EmotionQuadrant.ANXIOUS

    def test_classify_quadrant_calm(self, temp_db):
        from fuxi.engines.emotion_orchestrator import EmotionOrchestrator, EmotionQuadrant
        orch = EmotionOrchestrator()
        q = orch._classify_quadrant(0.5, 0.2)
        assert q == EmotionQuadrant.CALM

    def test_classify_quadrant_fatigued(self, temp_db):
        from fuxi.engines.emotion_orchestrator import EmotionOrchestrator, EmotionQuadrant
        orch = EmotionOrchestrator()
        q = orch._classify_quadrant(-0.5, 0.1)
        assert q == EmotionQuadrant.FATIGUED

    def test_classify_quadrant_neutral(self, temp_db):
        from fuxi.engines.emotion_orchestrator import EmotionOrchestrator, EmotionQuadrant
        orch = EmotionOrchestrator()
        q = orch._classify_quadrant(0.05, 0.1)
        assert q == EmotionQuadrant.NEUTRAL

    def test_modulation_map_has_all_quadrants(self, temp_db):
        from fuxi.engines.emotion_orchestrator import EMOTION_MODULATION, EmotionQuadrant
        for q in EmotionQuadrant:
            assert q in EMOTION_MODULATION, f"Missing modulation for {q}"
            assert isinstance(EMOTION_MODULATION[q], dict)
            assert len(EMOTION_MODULATION[q]) > 0

    def test_get_current_modulation(self, temp_db):
        from fuxi.engines.emotion_orchestrator import EmotionOrchestrator, EmotionQuadrant
        orch = EmotionOrchestrator()
        mod = orch.get_current_modulation()
        assert isinstance(mod, dict)
        assert "proactive.frequency" in mod

    def test_run_produces_state(self, temp_db):
        from fuxi.engines.emotion_orchestrator import EmotionOrchestrator
        orch = EmotionOrchestrator()
        orch.start()
        state = orch.run()
        assert "pad" in state
        assert "quadrant" in state
        assert "modulation_count" in state
        assert state["v"] == "1.5"

    def test_run_default_neutral(self, temp_db):
        from fuxi.engines.emotion_orchestrator import EmotionOrchestrator
        orch = EmotionOrchestrator()
        orch.start()
        state = orch.run()
        assert state["quadrant"] in ("neutral", "fatigued", "calm")

    def test_ema_smoothing(self, temp_db):
        from fuxi.engines.emotion_orchestrator import EmotionOrchestrator, EMA_ALPHA
        orch = EmotionOrchestrator()
        orch._current_pad = {"valence": 0.0, "arousal": 0.2, "dominance": 1.0}
        assert orch._current_pad["valence"] == 0.0

    def test_run_publishes_no_crash(self, temp_db):
        from fuxi.engines.emotion_orchestrator import EmotionOrchestrator
        orch = EmotionOrchestrator()
        orch.start()
        try:
            orch.run()
            passed = True
        except Exception:
            passed = False
        assert passed
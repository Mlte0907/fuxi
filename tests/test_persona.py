"""测试：PersonaEngine 人格化身引擎"""
import json

from conftest import auth_headers


class TestPersonaEngine:
    def test_engine_registered(self):
        from fuxi.engines.base import get_engine_registry
        engine = get_engine_registry().get("persona")
        assert engine is not None
        assert engine.name == "persona"
        assert engine.priority == 8
        assert engine.interval == 10800
        assert engine.experimental is False

    def test_personality_defaults(self):
        from fuxi.engines.persona import PersonaEngine
        defaults = PersonaEngine.PERSONALITY_DEFAULTS
        assert "openness" in defaults
        assert "curiosity" in defaults
        assert "warmth" in defaults
        assert "confidence" in defaults
        assert "verbosity" in defaults
        for v in defaults.values():
            assert 0 <= v <= 1

    def test_subscriptions(self):
        from fuxi.engines.persona import PersonaEngine
        engine = PersonaEngine()
        subs = engine._get_subscriptions()
        assert "soul.health_changed" in subs
        assert "memory.created" in subs
        assert "dialogue.completed" in subs
        assert "proactive.insight" in subs

    def test_template_report_no_llm(self, temp_db):
        from fuxi.engines.persona import PersonaEngine
        engine = PersonaEngine()
        report = engine._template_report()
        assert isinstance(report, str)
        assert len(report) > 10

    def test_valence_to_mood(self):
        from fuxi.engines.persona import PersonaEngine
        assert PersonaEngine._valence_to_mood(0.5, "neutral") == "轻松"
        assert PersonaEngine._valence_to_mood(-0.5, "neutral") == "沉重"
        assert PersonaEngine._valence_to_mood(0.1, "joy") == "愉快"
        assert PersonaEngine._valence_to_mood(0.0, "sad") == "低落"
        assert PersonaEngine._valence_to_mood(0.0, "neutral") == "平静"

    def test_valence_to_emotion_valence(self):
        from fuxi.engines.persona import PersonaEngine
        assert PersonaEngine._valence_to_emotion_valence(0.5) == 0.6
        assert PersonaEngine._valence_to_emotion_valence(-0.5) == -0.6
        assert PersonaEngine._valence_to_emotion_valence(1.0) == 1.0  # clamped

    def test_personality_drift(self):
        from fuxi.engines.persona import PersonaEngine
        engine = PersonaEngine()
        result = engine._drift(0.5, 0.9)
        assert 0.5 < result < 0.52  # small drift per cycle
        result2 = engine._drift(0.9, 0.5)
        assert 0.89 < result2 < 0.9  # small drift downward

    def test_classify_trigger_status(self):
        from fuxi.engines.persona import PersonaEngine
        engine = PersonaEngine()
        ctx = {"pending_events": [], "total_memories": 50}
        assert engine._classify_trigger(ctx) == "status"

    def test_classify_trigger_greeting(self):
        from fuxi.engines.persona import PersonaEngine
        engine = PersonaEngine()
        ctx = {"pending_events": [], "total_memories": 0}
        assert engine._classify_trigger(ctx) == "greeting"

    def test_classify_trigger_alert(self):
        from fuxi.engines.persona import PersonaEngine
        engine = PersonaEngine()
        ctx = {
            "pending_events": [
                {"type": "soul.health_changed", "data": {"new_label": "needs_attention"}}
            ]
        }
        assert engine._classify_trigger(ctx) == "alert"

    def test_classify_trigger_observation_memory(self):
        from fuxi.engines.persona import PersonaEngine
        engine = PersonaEngine()
        ctx = {
            "pending_events": [
                {"type": "memory.created", "data": {"importance": 0.85}}
            ]
        }
        assert engine._classify_trigger(ctx) == "observation"

    def test_classify_trigger_observation_dialogue(self):
        from fuxi.engines.persona import PersonaEngine
        engine = PersonaEngine()
        ctx = {
            "pending_events": [
                {"type": "dialogue.completed", "data": {}}
            ]
        }
        assert engine._classify_trigger(ctx) == "observation"

    def test_classify_trigger_reflection(self):
        from fuxi.engines.persona import PersonaEngine
        engine = PersonaEngine()
        ctx = {
            "pending_events": [
                {"type": "proactive.insight", "data": {}}
            ]
        }
        assert engine._classify_trigger(ctx) == "reflection"

    def test_should_report_cooldown(self):
        from fuxi.engines.persona import PersonaEngine
        engine = PersonaEngine()
        import time
        # Set last report to now (within cooldown)
        engine._state.metadata["last_report_ts"] = time.time()
        assert engine._should_report("status") is False

    def test_should_report_alert_within_cooldown(self):
        from fuxi.engines.persona import PersonaEngine
        engine = PersonaEngine()
        import time
        engine._state.metadata["last_report_ts"] = time.time()
        assert engine._should_report("alert") is False  # alert 也受冷却限制

    def test_build_prompt(self):
        from fuxi.engines.persona import PersonaEngine
        engine = PersonaEngine()
        ctx = {
            "health": {"label": "healthy", "overall": 0.85},
            "total_memories": 42,
            "total_connections": 30,
            "mood": "轻松",
            "valence": 0.3,
            "arousal": 0.4,
            "wm_items": [{"source": "engine:soul", "content": "健康检查"}],
            "recent_memories": [{"preview": "测试记忆", "created_by": "user"}],
            "recent_events": [],
            "pending_events": [],
            "decisions": [],
            "traits": dict(PersonaEngine.PERSONALITY_DEFAULTS),
        }
        prompt = engine._build_prompt(ctx, "status")
        assert "伏羲 v1.0" in prompt
        assert "42条" in prompt
        assert "30条" in prompt
        assert "轻松" in prompt

    def test_run_returns_dict(self, temp_db):
        from fuxi.engines.persona import PersonaEngine
        engine = PersonaEngine()
        result = engine.run()
        assert isinstance(result, dict)
        assert "action" in result
        assert "report_type" in result
        assert "timestamp" in result

    def test_run_skips_on_cooldown(self, temp_db):
        from fuxi.engines.persona import PersonaEngine
        engine = PersonaEngine()
        import time
        engine._state.metadata["last_report_ts"] = time.time()
        result = engine.run()
        assert result["action"] == "skip"

    def test_run_produces_report(self, temp_db):
        from fuxi.engines.persona import PersonaEngine
        engine = PersonaEngine()
        result = engine.run()
        if result["action"] == "reported":
            assert "report_preview" in result
            assert "mood" in result

    def test_state_persistence(self, temp_db):
        from fuxi.engines.persona import PersonaEngine
        from fuxi.store.connection import get_pool

        engine = PersonaEngine()
        ctx = {
            "mood": "平静",
            "total_memories": 10,
            "valence": 0.0,
            "health": {"label": "healthy", "overall": 0.7},
        }
        engine._persist_state("测试报告文本", "status", ctx)

        pool = get_pool()
        row = pool.fetchone(
            "SELECT state_json FROM engine_states WHERE engine_name='persona'"
        )
        assert row is not None
        data = json.loads(row["state_json"])
        assert "report_history" in data
        assert data["mood"] == "平静"
        assert len(data["report_history"]) == 1
        assert data["report_history"][0]["type"] == "status"

    def test_gather_context(self, temp_db):
        from fuxi.engines.persona import PersonaEngine
        engine = PersonaEngine()
        ctx = engine._gather_context()
        assert isinstance(ctx, dict)
        assert "health" in ctx
        assert "total_memories" in ctx
        assert "mood" in ctx
        assert "traits" in ctx
        assert "wm_items" in ctx

    def test_update_personality_drifts_traits(self, temp_db):
        from fuxi.engines.persona import PersonaEngine
        engine = PersonaEngine()
        traits = dict(PersonaEngine.PERSONALITY_DEFAULTS)
        ctx = {
            "traits": traits,
            "valence": -0.5,
            "total_memories": 500,
            "health": {"overall": 0.4},
        }
        engine._update_personality(ctx)
        # Warmth should drift downward with negative valence
        assert ctx["traits"]["warmth"] < PersonaEngine.PERSONALITY_DEFAULTS["warmth"]
        # Curiosity should be higher with more memories
        assert ctx["traits"]["curiosity"] > PersonaEngine.PERSONALITY_DEFAULTS["curiosity"]


class TestPersonaAPI:
    def test_get_persona_state(self, client):
        r = client.get("/api/v2/persona", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert "traits" in data
        assert "mood" in data

    def test_get_persona_reports(self, client):
        r = client.get("/api/v2/persona/reports", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert "reports" in data
        assert isinstance(data["reports"], list)

    def test_force_speak(self, client):
        r = client.post("/api/v2/persona/speak", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert "action" in data

    def test_get_traits(self, client):
        r = client.get("/api/v2/persona/traits", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert "openness" in data
        assert "curiosity" in data

    def test_update_traits(self, client):
        r = client.put(
            "/api/v2/persona/traits",
            json={"openness": 0.9, "warmth": 0.5},
            headers=auth_headers(),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["traits"]["openness"] == 0.9
        assert data["traits"]["warmth"] == 0.5
        assert "updated" in data

    def test_update_traits_invalid_key(self, client):
        r = client.put(
            "/api/v2/persona/traits",
            json={"not_a_trait": 0.9},
            headers=auth_headers(),
        )
        assert r.status_code == 400

    def test_get_mood(self, client):
        r = client.get("/api/v2/persona/mood", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert "mood" in data

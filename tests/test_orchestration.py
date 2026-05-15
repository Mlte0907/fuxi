"""测试：技能编排中枢"""
import json


class TestSkillOrchestrator:
    def test_engine_registered(self):
        from fuxi.engines.base import get_engine_registry
        eng = get_engine_registry().get("skill_orchestrator")
        assert eng is not None
        assert eng.name == "skill_orchestrator"
        assert eng.priority == 5
        assert eng.interval == 600

    def test_skill_gap_class(self):
        from fuxi.engines.skill_orchestrator import SkillGap
        gap = SkillGap(
            gap_id="gap_test_001",
            pattern="debug",
            failure_count=10,
            sample_errors=["error1", "error2"],
            severity=5.0,
        )
        assert gap.gap_id == "gap_test_001"
        assert gap.pattern == "debug"
        assert gap.failure_count == 10
        assert gap.severity == 5.0

    def test_run_produces_state(self, temp_db):
        from fuxi.engines.skill_orchestrator import SkillOrchestrator
        so = SkillOrchestrator()
        so.start()
        state = so.run()
        assert "gaps_detected" in state
        assert "requests_created" in state
        assert "tracking_summary" in state
        assert state["v"] == "1.5"

    def test_detect_gaps_returns_list(self, temp_db):
        from fuxi.engines.skill_orchestrator import SkillOrchestrator
        from fuxi.store.connection import get_pool
        so = SkillOrchestrator()
        gaps = so._detect_gaps(get_pool())
        assert isinstance(gaps, list)

    def test_track_deployed(self, temp_db):
        from fuxi.engines.skill_orchestrator import SkillOrchestrator
        from fuxi.store.connection import get_pool
        so = SkillOrchestrator()
        tracking = so._track_deployed(get_pool())
        assert "deployed" in tracking
        assert "improved" in tracking
        assert "needs_review" in tracking

    def test_validate_pending(self, temp_db):
        from fuxi.engines.skill_orchestrator import SkillOrchestrator
        from fuxi.store.connection import get_pool
        so = SkillOrchestrator()
        validations = so._validate_pending(get_pool())
        assert isinstance(validations, list)


class TestArchAuditor:
    def test_engine_registered(self):
        from fuxi.engines.base import get_engine_registry
        eng = get_engine_registry().get("arch_auditor")
        assert eng is not None
        assert eng.name == "arch_auditor"
        assert eng.priority == 3
        assert eng.interval == 1800

    def test_run_produces_state(self, temp_db):
        from fuxi.engines.arch_auditor import ArchAuditor
        aa = ArchAuditor()
        aa.start()
        state = aa.run()
        assert "engine_rankings" in state
        assert "context_gaps" in state
        assert "recommendations" in state
        assert "overall_health" in state
        assert state["v"] == "1.5"

    def test_rank_engines_by_efficiency(self, temp_db):
        from fuxi.engines.arch_auditor import ArchAuditor
        from fuxi.store.connection import get_pool
        aa = ArchAuditor()
        rankings = aa._rank_engines_by_efficiency(get_pool())
        assert isinstance(rankings, list)

    def test_find_uncovered_contexts(self, temp_db):
        from fuxi.engines.arch_auditor import ArchAuditor
        from fuxi.store.connection import get_pool
        aa = ArchAuditor()
        gaps = aa._find_uncovered_contexts(get_pool())
        assert isinstance(gaps, list)

    def test_detect_redundancy(self, temp_db):
        from fuxi.engines.arch_auditor import ArchAuditor
        aa = ArchAuditor()
        alerts = aa._detect_redundancy()
        assert isinstance(alerts, list)

    def test_generate_recommendations(self, temp_db):
        from fuxi.engines.arch_auditor import ArchAuditor
        aa = ArchAuditor()
        recs = aa._generate_recommendations([], [], [])
        assert len(recs) >= 1
        assert any("正常" in r or "健康" in r for r in recs)

    def test_assess_overall_healthy(self, temp_db):
        from fuxi.engines.arch_auditor import ArchAuditor
        aa = ArchAuditor()
        result = aa._assess_overall([], 0)
        assert result in ("healthy", "unknown")

    def test_engine_rank_dataclass(self, temp_db):
        from fuxi.engines.arch_auditor import EngineRank
        rank = EngineRank(
            name="test_engine",
            efficiency=0.8,
            run_count=100,
            useful_outputs=80,
            failure_rate=0.05,
        )
        assert rank.name == "test_engine"
        assert rank.efficiency == 0.8
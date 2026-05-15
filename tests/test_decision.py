"""测试：自主决策模块"""


class TestDecisionFramework:
    def test_decision_option_create(self):
        from fuxi.decision.framework import DecisionOption
        opt = DecisionOption(
            id="test1", description="测试选项",
            action_type="memory_cleanup", risk_level=0.2,
            confidence=0.8, cost_estimate=0.3,
        )
        assert opt.id == "test1"
        assert opt.risk_level == 0.2

    def test_decision_create(self):
        from fuxi.decision.framework import (
            Decision,
            DecisionOption,
            DecisionStatus,
            DecisionType,
        )
        opt = DecisionOption(
            id="test1", description="Test", action_type="memory_cleanup",
            risk_level=0.1, confidence=0.9,
        )
        d = Decision(
            id="d1", decision_type=DecisionType.MEMORY_MANAGEMENT,
            trigger_reason="test", options=[opt],
        )
        assert d.status == DecisionStatus.PENDING
        assert d.selected_option is None

    def test_evaluate_low_risk_auto_approved(self):
        from fuxi.decision.framework import (
            Decision,
            DecisionFramework,
            DecisionOption,
            DecisionStatus,
            DecisionType,
        )
        opt = DecisionOption(
            id="safe", description="安全操作",
            action_type="memory_cleanup", risk_level=0.1,
            confidence=0.9, cost_estimate=0.1,
        )
        d = Decision(
            id="d1", decision_type=DecisionType.MEMORY_MANAGEMENT,
            trigger_reason="test", options=[opt],
        )
        fw = DecisionFramework()
        d = fw.evaluate_options(d)
        assert d.status == DecisionStatus.APPROVED
        assert d.selected_option == "safe"

    def test_evaluate_high_risk_rejected(self):
        from fuxi.decision.framework import (
            Decision,
            DecisionFramework,
            DecisionOption,
            DecisionStatus,
            DecisionType,
        )
        opt = DecisionOption(
            id="risky", description="高风险操作",
            action_type="agent_delegate", risk_level=0.9,
            confidence=0.9, cost_estimate=0.1,
        )
        d = Decision(
            id="d2", decision_type=DecisionType.COLLABORATION,
            trigger_reason="test", options=[opt],
        )
        fw = DecisionFramework()
        d = fw.evaluate_options(d)
        assert d.status == DecisionStatus.REJECTED

    def test_evaluate_picks_best_score(self):
        from fuxi.decision.framework import (
            Decision,
            DecisionFramework,
            DecisionOption,
            DecisionType,
        )
        opts = [
            DecisionOption(
                id="low_conf", description="低信心",
                action_type="memory_cleanup", risk_level=0.1,
                confidence=0.3, cost_estimate=0.1,
            ),
            DecisionOption(
                id="high_conf", description="高信心",
                action_type="memory_cleanup", risk_level=0.1,
                confidence=0.9, cost_estimate=0.1,
            ),
        ]
        d = Decision(
            id="d3", decision_type=DecisionType.MEMORY_MANAGEMENT,
            trigger_reason="test", options=opts,
        )
        fw = DecisionFramework()
        d = fw.evaluate_options(d)
        assert d.selected_option == "high_conf"


class TestDecisionExecutor:
    def test_reject_unapproved(self):
        from fuxi.decision.executor import DecisionExecutor
        from fuxi.decision.framework import Decision, DecisionStatus, DecisionType
        d = Decision(
            id="d1", decision_type=DecisionType.MEMORY_MANAGEMENT,
            trigger_reason="test", status=DecisionStatus.PENDING,
        )
        executor = DecisionExecutor()
        result = executor.execute(d)
        assert result["status"] == "rejected"

    def test_handlers_registered(self):
        from fuxi.decision.executor import DecisionExecutor
        assert "memory_cleanup" in DecisionExecutor.ACTION_HANDLERS
        assert "attention_reallocate" in DecisionExecutor.ACTION_HANDLERS
        assert "engine_priority_adjust" in DecisionExecutor.ACTION_HANDLERS
        assert "proactive_notify" in DecisionExecutor.ACTION_HANDLERS
        assert "agent_delegate" in DecisionExecutor.ACTION_HANDLERS

    def test_execute_memory_cleanup(self, temp_db):
        from fuxi.decision.executor import DecisionExecutor
        from fuxi.decision.framework import (
            Decision,
            DecisionOption,
            DecisionStatus,
            DecisionType,
        )
        opt = DecisionOption(
            id="clean", description="清理",
            action_type="memory_cleanup", risk_level=0.1,
        )
        d = Decision(
            id="d1", decision_type=DecisionType.MEMORY_MANAGEMENT,
            trigger_reason="test", options=[opt],
            selected_option="clean", status=DecisionStatus.APPROVED,
        )
        executor = DecisionExecutor()
        result = executor.execute(d)
        assert result["status"] == "ok"


class TestDecisionEngine:
    def test_engine_registered(self):
        from fuxi.engines.base import get_engine_registry
        engine = get_engine_registry().get("decision")
        assert engine is not None
        assert engine.name == "decision"
        assert engine.priority == 8
        assert engine.interval == 600

    def test_run_returns_dict(self, temp_db):
        from fuxi.engines.decision import DecisionEngine
        engine = DecisionEngine()
        result = engine.run()
        assert isinstance(result, dict)
        assert "situations_detected" in result
        assert "decisions_made" in result
        assert "timestamp" in result

"""测试 observability 子系统的健康检查、自调试和验证功能"""
import pytest
import time

from fuxi.observability.health import quick_health_check, deep_health_check
from fuxi.observability.self_debugger import (
    SelfDebugger,
    FailureCapture,
    DiagnosisResult,
    DebugReport,
    FAILURE_PATTERNS,
)
from fuxi.observability.context_budget import ContextBudgetAnalyzer, ComponentInventory


class TestHealthCheck:
    """健康检查测试"""

    def test_quick_health_check_ok(self):
        """快速健康检查返回ok"""
        result = quick_health_check()
        assert result["status"] == "ok"
        assert "version" in result
        assert "uptime_seconds" in result
        assert result["uptime_seconds"] >= 0

    def test_quick_health_check_timestamp(self):
        """时间戳是合理的"""
        result = quick_health_check()
        now = time.time()
        assert abs(result["timestamp"] - now) < 5

    def test_deep_health_check_returns_dict(self):
        """深度健康检查返回字典"""
        result = deep_health_check()
        assert "status" in result
        assert "checks" in result
        assert "uptime_seconds" in result

    def test_deep_health_check_has_db(self):
        """深度检查包含DB状态"""
        result = deep_health_check()
        assert "database" in result["checks"]

    def test_deep_health_check_has_embedding(self):
        """深度检查包含嵌入服务状态"""
        result = deep_health_check()
        assert "embedding" in result["checks"]

    def test_deep_health_check_status_valid(self):
        """状态值合法"""
        result = deep_health_check()
        assert result["status"] in ("ok", "degraded")


class TestSelfDebugger:
    """自调试工作流测试"""

    def setup_method(self):
        self.debugger = SelfDebugger()

    def test_failure_patterns_defined(self):
        """故障模式库已定义"""
        assert len(FAILURE_PATTERNS) >= 4
        for key in ["max_tool_calls", "context_overflow", "connection_refused"]:
            assert key in FAILURE_PATTERNS
            assert "likely_cause" in FAILURE_PATTERNS[key]

    def test_capture_failure(self):
        """故障捕获"""
        error = RuntimeError("max_tool_calls exceeded")
        context = {
            "session_id": "test-001",
            "current_goal": "fix a bug",
            "last_success": "step 3",
            "failed_tool": "executor",
        }
        capture = self.debugger.capture_failure(error, context)
        assert capture.session == "test-001"
        assert capture.goal == "fix a bug"
        assert capture.error == "max_tool_calls exceeded"
        assert isinstance(capture.timestamp, str)

    def test_diagnose_known_pattern(self):
        """已知故障模式诊断"""
        capture = FailureCapture(
            session="test",
            goal="test",
            error="connection refused by remote host",
            last_successful_step="step 2",
            last_failed_tool="http_call",
        )
        diagnosis = self.debugger.diagnose(capture)
        assert diagnosis.pattern == "connection_refused"
        assert "service" in diagnosis.root_cause
        assert len(diagnosis.diagnosis_questions) == 4
        assert not diagnosis.is_deterministic

    def test_diagnose_unknown_pattern(self):
        """未知故障模式诊断"""
        capture = FailureCapture(
            session="test",
            goal="test",
            error="some completely novel error type",
            last_successful_step="",
            last_failed_tool="",
        )
        diagnosis = self.debugger.diagnose(capture)
        assert diagnosis.pattern == "unknown"

    def test_diagnose_file_missing_deterministic(self):
        """文件缺失为确定性故障"""
        capture = FailureCapture(
            session="test",
            goal="test",
            error="file missing: src/module.py not found",
            last_successful_step="",
            last_failed_tool="read_file",
        )
        diagnosis = self.debugger.diagnose(capture)
        assert diagnosis.is_deterministic

    def test_contained_recovery_returns_action(self):
        """恢复操作返回具体方案"""
        diagnosis = DiagnosisResult(
            pattern="context_overflow",
            root_cause="too much context",
            diagnosis_questions=[],
            is_deterministic=False,
            smallest_reversible_action="trim context",
        )
        capture = FailureCapture(session="test", goal="test", error="test")
        action = self.debugger.contained_recovery(diagnosis, capture)
        assert isinstance(action, str)
        assert "trim" in action.lower() or "context" in action.lower()

    def test_contained_recovery_unknown_pattern(self):
        """未知模式的恢复方案"""
        diagnosis = DiagnosisResult(
            pattern="unknown",
            root_cause="unknown",
            diagnosis_questions=[],
            is_deterministic=False,
            smallest_reversible_action="direct observation",
        )
        capture = FailureCapture(session="test", goal="test", error="test")
        action = self.debugger.contained_recovery(diagnosis, capture)
        assert isinstance(action, str)
        assert len(action) > 0

    def test_generate_report(self):
        """生成调试报告"""
        capture = FailureCapture(
            session="test",
            goal="test",
            error="test error",
        )
        diagnosis = DiagnosisResult(
            pattern="test",
            root_cause="test cause",
            diagnosis_questions=["q1"],
            is_deterministic=True,
            smallest_reversible_action="test action",
        )
        report = self.debugger.generate_report(
            capture, diagnosis, "recovery action", "resolved"
        )
        assert isinstance(report, DebugReport)
        assert report.capture == capture
        assert report.diagnosis == diagnosis
        assert report.outcome == "resolved"
        assert isinstance(report.timestamp, str)

    def test_run_debug_cycle(self):
        """完整调试周期"""
        error = RuntimeError("file_missing: src/module.py")
        context = {"session_id": "debug-001", "current_goal": "fix tests"}
        report = self.debugger.run_debug_cycle(error, context)
        assert isinstance(report, DebugReport)
        assert report.diagnosis is not None
        assert len(report.recovery_action) > 0


class TestContextBudget:
    """上下文预算分析测试"""

    def test_analyzer_init(self):
        """分析器初始化"""
        analyzer = ContextBudgetAnalyzer()
        assert analyzer.total_tokens == 0
        assert analyzer.inventoryy == []

    def test_inventory_returns_list(self):
        """扫描返回列表"""
        analyzer = ContextBudgetAnalyzer()
        components = analyzer.run_inventory()
        assert isinstance(components, list)

    def test_classify_components(self):
        """分类测试"""
        analyzer = ContextBudgetAnalyzer()
        analyzer.inventoryy = [
            ComponentInventory("memory", "test", "/fake/path", lines=10, tokens=13),
            ComponentInventory("agent", "heavy", "/fake/path", lines=300, tokens=390,
                               issues=["Heavy agent"]),
        ]
        analyzer.total_tokens = 403
        buckets = analyzer.classify_components()
        assert "always_needed" in buckets
        assert "sometimes_needed" in buckets
        assert "rarely_needed" in buckets

    def test_generate_report(self):
        """生成报告"""
        analyzer = ContextBudgetAnalyzer()
        analyzer.inventoryy = [
            ComponentInventory("memory", "test", "/fake/path", lines=10, tokens=13),
            ComponentInventory("agent", "ok", "/fake/path", lines=50, tokens=65),
        ]
        analyzer.total_tokens = 78
        report = analyzer.generate_report()
        assert "Context Budget Report" in report
        assert "agent" in report
        assert "memory" in report

    def test_component_limits(self):
        """组件限制已定义"""
        from fuxi.observability.context_budget import COMPONENT_LIMITS
        assert "agent" in COMPONENT_LIMITS
        assert "skill" in COMPONENT_LIMITS
        assert COMPONENT_LIMITS["agent"]["max_lines"] == 200
        assert COMPONENT_LIMITS["skill"]["max_lines"] == 400
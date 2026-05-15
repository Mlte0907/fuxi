"""伏羲 v1.0 — 自调试工作流

适配自 ECC agent-introspection-debugging:
- Phase 1: Failure Capture (故障捕获)
- Phase 2: Root-Cause Diagnosis (根因诊断)
- Phase 3: Contained Recovery (受限恢复)
- Phase 4: Introspection Report (自省报告)
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger("fuxi.observability.self_debugger")

FAILURE_PATTERNS = {
    "max_tool_calls": {
        "likely_cause": "loop or no-exit observer path",
        "check": "inspect last N tool calls for repetition"
    },
    "context_overflow": {
        "likely_cause": "unbounded notes, repeated plans, oversized logs",
        "check": "inspect recent context for duplication and low-signal bulk"
    },
    "connection_refused": {
        "likely_cause": "service unavailable or wrong port",
        "check": "verify service health, URL, and port assumptions"
    },
    "rate_limit": {
        "likely_cause": "retry storm or missing backoff",
        "check": "count repeated calls and inspect retry spacing"
    },
    "file_missing": {
        "likely_cause": "race, wrong cwd, or branch drift",
        "check": "re-check path, cwd, git status, and actual file existence"
    },
    "test_still_failing": {
        "likely_cause": "wrong hypothesis",
        "check": "isolate exact failing test and re-derive bug"
    },
}


@dataclass
class FailureCapture:
    """故障捕获模板"""
    session: str = ""
    goal: str = ""
    error: str = ""
    last_successful_step: str = ""
    last_failed_tool: str = ""
    repeated_pattern: str = ""
    environment_assumptions: list = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class DiagnosisResult:
    """诊断结果"""
    pattern: str
    root_cause: str
    diagnosis_questions: list
    is_deterministic: bool
    smallest_reversible_action: str


@dataclass
class DebugReport:
    """调试报告"""
    capture: FailureCapture
    diagnosis: Optional[DiagnosisResult]
    recovery_action: str
    outcome: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class SelfDebugger:
    """自调试工作流"""
    
    def capture_failure(self, error: Exception, context: dict) -> FailureCapture:
        """Phase 1: 捕获故障"""
        capture = FailureCapture(
            session=context.get("session_id", "unknown"),
            goal=context.get("current_goal", ""),
            error=str(error),
            last_successful_step=context.get("last_success", ""),
            last_failed_tool=context.get("failed_tool", ""),
            repeated_pattern=context.get("repeated_pattern", ""),
            environment_assumptions=context.get("assumptions", []),
        )
        logger.info(f"[SelfDebug] Failure captured: {error}")
        return capture
    
    def diagnose(self, capture: FailureCapture) -> DiagnosisResult:
        """Phase 2: 根因诊断"""
        # 匹配故障模式
        matched_pattern = None
        for pattern_key, pattern_info in FAILURE_PATTERNS.items():
            if pattern_key.replace("_", " ") in capture.error.lower() or \
               pattern_key in capture.repeated_pattern.lower():
                matched_pattern = pattern_key
                break
        
        if not matched_pattern:
            matched_pattern = "unknown"
        
        pattern_info = FAILURE_PATTERNS.get(matched_pattern, {
            "likely_cause": "unknown",
            "check": "direct observation required"
        })
        
        # 诊断问题
        questions = [
            f"Is this a logic failure, state failure, environment failure, or policy failure?",
            f"Did the agent lose the real objective?",
            f"Is the failure deterministic or transient?",
            f"What is the smallest reversible action?",
        ]
        
        is_deterministic = matched_pattern in ("file_missing", "test_still_failing")
        
        return DiagnosisResult(
            pattern=matched_pattern,
            root_cause=pattern_info["likely_cause"],
            diagnosis_questions=questions,
            is_deterministic=is_deterministic,
            smallest_reversible_action=pattern_info["check"]
        )
    
    def contained_recovery(self, diagnosis: DiagnosisResult, 
                          capture: FailureCapture) -> str:
        """Phase 3: 受限恢复"""
        recovery_actions = {
            "max_tool_calls": "stop repeated retries, restate the hypothesis, trim context",
            "context_overflow": "trim low-signal context, keep only active goal/blockers/evidence",
            "connection_refused": "verify service health, URL and port assumptions",
            "rate_limit": "add backoff delay, check retry spacing",
            "file_missing": "re-check path, cwd, git status, file existence",
            "test_still_failing": "isolate exact failing test, re-derive bug hypothesis",
        }
        
        action = recovery_actions.get(
            diagnosis.pattern,
            "narrow task to one failing command, one file, or one test"
        )
        
        logger.info(f"[SelfDebug] Recovery action: {action}")
        return action
    
    def generate_report(self, capture: FailureCapture,
                        diagnosis: DiagnosisResult,
                        recovery: str,
                        outcome: str = "pending") -> DebugReport:
        """Phase 4: 生成调试报告"""
        return DebugReport(
            capture=capture,
            diagnosis=diagnosis,
            recovery_action=recovery,
            outcome=outcome,
        )
    
    def run_debug_cycle(self, error: Exception, context: dict) -> DebugReport:
        """运行完整调试周期"""
        # 1. Capture
        capture = self.capture_failure(error, context)
        
        # 2. Diagnose
        diagnosis = self.diagnose(capture)
        
        # 3. Recover
        recovery = self.contained_recovery(diagnosis, capture)
        
        # 4. Report
        return self.generate_report(capture, diagnosis, recovery)

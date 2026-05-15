"""伏羲 v1.0 — SelfDebugger 技能封装

将 ECC agent-introspection-debugging 技能接入伏羲技能市场，
作为可被 Agent 调用的自调试工具。
"""


def run_debug_skill(error_msg: str, session_id: str = "unknown",
                     current_goal: str = "", last_success: str = "") -> dict:
    """运行自调试工作流 — 可作为技能调用

    Args:
        error_msg: 错误信息
        session_id: 会话 ID
        current_goal: 当前目标
        last_success: 最后成功的步骤
    """
    from fuxi.observability.self_debugger import SelfDebugger

    debugger = SelfDebugger()
    error = Exception(error_msg)
    context = {
        "session_id": session_id,
        "current_goal": current_goal,
        "last_success": last_success,
        "failed_tool": "",
        "repeated_pattern": "",
        "assumptions": [],
    }

    report = debugger.run_debug_cycle(error, context)

    return {
        "status": "ok",
        "pattern": report.diagnosis.pattern,
        "root_cause": report.diagnosis.root_cause,
        "recovery_action": report.recovery_action,
        "diagnosis_questions": report.diagnosis.diagnosis_questions,
    }


def run_quick_debug(error_msg: str) -> dict:
    """快速调试 — 只返回恢复建议"""
    from fuxi.observability.self_debugger import SelfDebugger

    debugger = SelfDebugger()
    error = Exception(error_msg)
    capture = debugger.capture_failure(error, {"session_id": "quick"})
    diagnosis = debugger.diagnose(capture)
    recovery = debugger.contained_recovery(diagnosis, capture)

    return {
        "status": "ok",
        "likely_cause": diagnosis.root_cause,
        "recovery": recovery,
    }

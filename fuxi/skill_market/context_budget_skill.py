"""伏羲 v1.0 — ContextBudget 技能封装

将 ECC context-budget 技能接入伏羲技能市场，
作为可被 Agent 调用的上下文预算分析工具。
"""


def run_context_budget_skill() -> dict:
    """运行上下文预算分析 — 可作为技能调用"""
    from fuxi.observability.context_budget import ContextBudgetAnalyzer

    analyzer = ContextBudgetAnalyzer()
    analyzer.run_inventory()
    buckets = analyzer.classify_components()
    report = analyzer.generate_report()

    # 检测到的问题
    issues = [c for c in analyzer.inventory if c.issues]

    return {
        "status": "ok",
        "report": report,
        "total_tokens": analyzer.total_tokens,
        "issues_count": len(issues),
        "buckets": {k: len(v) for k, v in buckets.items()},
    }


def run_quick_budget() -> dict:
    """快速预算检查 — 只扫描伏羲项目"""
    from fuxi.observability.context_budget import ContextBudgetAnalyzer

    analyzer = ContextBudgetAnalyzer()
    components = analyzer.run_inventory()
    issues = [c for c in components if c.issues]

    return {
        "status": "ok",
        "total_components": len(components),
        "total_tokens": analyzer.total_tokens,
        "components_with_issues": len(issues),
    }

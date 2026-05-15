"""伏羲 v1.0 — VerificationLoop 技能封装

将 ECC verification-loop 技能接入伏羲技能市场，
作为可被 Agent 调用的验证工具。
"""
from dataclasses import dataclass


@dataclass
class VerificationResult:
    phase: str
    passed: bool
    output: str
    warnings: int = 0
    errors: int = 0


def run_verification_skill(project_path: str = "/home/xiaoxin/fuxi") -> dict:
    """运行完整验证循环 — 可作为技能调用"""
    from fuxi.observability.verification import VerificationLoop

    vl = VerificationLoop(project_path=project_path)
    results = vl.run_full_verification()

    lines = ["=== Verification Report ===", ""]
    for phase, result in results.items():
        status = "PASS" if result.passed else "FAIL"
        lines.append(f"{phase}: {status}")

    passed = sum(1 for r in results.values() if r.passed)
    total = len(results)
    lines.append(f"Summary: {passed}/{total} phases passed")

    return {
        "status": "ok",
        "report": "\n".join(lines),
    }


def run_quick_check(project_path: str = "/home/xiaoxin/fuxi") -> dict:
    """快速检查 — 只运行 build + lint"""
    from fuxi.observability.verification import VerificationLoop

    vl = VerificationLoop(project_path=project_path)
    results = {
        "build": vl.run_build(),
        "lint": vl.run_lint(),
    }

    lines = ["=== Quick Check ===", ""]
    for phase, result in results.items():
        status = "PASS" if result.passed else "FAIL"
        lines.append(f"{status} {phase}")

    return {"status": "ok", "report": "\n".join(lines)}
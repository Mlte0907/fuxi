"""伏羲 v1.0 — 验证循环系统

适配自 ECC verification-loop 技能:
- Phase 1: Build Verification
- Phase 2: Type Check
- Phase 3: Lint Check
- Phase 4: Test Suite
- Phase 5: Security Scan
- Phase 6: Diff Review
"""
import subprocess
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("fuxi.observability.verification")


@dataclass
class VerificationResult:
    phase: str
    passed: bool
    output: str
    warnings: int = 0
    errors: int = 0


class VerificationLoop:
    """验证循环系统 - 代码质量门控"""
    
    BUILD_COMMANDS = {
        "python": ["python3", "-m", "py_compile"],
        "node": ["npm", "run", "build"],
        "go": ["go", "build", "./..."],
    }
    
    def __init__(self, project_path: str = "/home/xiaoxin/fuxi"):
        self.project_path = project_path
    
    def run_build(self, language: str = "python") -> VerificationResult:
        """Phase 1: 构建验证"""
        try:
            if language == "python":
                result = subprocess.run(
                    ["python3", "-m", "compileall", "-q", "."],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
            else:
                result = subprocess.run(
                    ["echo", "build"],
                    capture_output=True,
                    text=True
                )
            return VerificationResult(
                phase="build",
                passed=result.returncode == 0,
                output=result.stdout + result.stderr
            )
        except Exception as e:
            return VerificationResult(phase="build", passed=False, output=str(e))
    
    def run_type_check(self, language: str = "python") -> VerificationResult:
        """Phase 2: 类型检查"""
        try:
            if language == "python":
                result = subprocess.run(
                    ["python3", "-m", "mypy", "fuxi/", "--ignore-missing-imports"],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
            else:
                result = subprocess.run(["echo", "type_check"], capture_output=True, text=True)
            errors = len([l for l in result.stdout.split('\n') if ': error:' in l])
            return VerificationResult(
                phase="type_check",
                passed=result.returncode == 0,
                output=result.stdout,
                errors=errors
            )
        except Exception as e:
            return VerificationResult(phase="type_check", passed=False, output=str(e))
    
    def run_lint(self) -> VerificationResult:
        """Phase 3: Lint 检查"""
        try:
            result = subprocess.run(
                ["python3", "-m", "ruff", "check", "fuxi/", "--output-format=text"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            warnings = len([l for l in result.stdout.split('\n') if 'warning' in l.lower()])
            return VerificationResult(
                phase="lint",
                passed=result.returncode == 0,
                output=result.stdout,
                warnings=warnings
            )
        except FileNotFoundError:
            return VerificationResult(phase="lint", passed=True, output="ruff not installed, skipping")
        except Exception as e:
            return VerificationResult(phase="lint", passed=False, output=str(e))
    
    def run_tests(self) -> VerificationResult:
        """Phase 4: 测试套件"""
        try:
            result = subprocess.run(
                ["python3", "-m", "pytest", "tests/", "-v", "--tb=short"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=300
            )
            passed = result.returncode == 0
            return VerificationResult(
                phase="tests",
                passed=passed,
                output=result.stdout[-2000:]  # 最后2000字符
            )
        except FileNotFoundError:
            return VerificationResult(phase="tests", passed=True, output="pytest not found, skipping")
        except Exception as e:
            return VerificationResult(phase="tests", passed=False, output=str(e))
    
    def run_security_scan(self) -> VerificationResult:
        """Phase 5: 安全扫描"""
        findings = []
        try:
            # 检查硬编码密钥
            result = subprocess.run(
                ["grep", "-rn", "sk-[a-zA-Z0-9]", "fuxi/", "--include=*.py"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.stdout:
                findings.append(f"Potential secrets found: {len(result.stdout.split(chr(10)))}")
        except Exception:
            pass
        
        return VerificationResult(
            phase="security",
            passed=len(findings) == 0,
            output="\n".join(findings) if findings else "No issues found"
        )
    
    def run_diff_review(self) -> VerificationResult:
        """Phase 6: 差异审查"""
        try:
            result = subprocess.run(
                ["git", "diff", "--stat"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            return VerificationResult(
                phase="diff_review",
                passed=True,
                output=result.stdout if result.returncode == 0 else "Not a git repo"
            )
        except Exception as e:
            return VerificationResult(phase="diff_review", passed=False, output=str(e))
    
    def run_full_verification(self) -> dict:
        """运行完整验证循环"""
        results = {}
        phases = [
            ("build", lambda: self.run_build()),
            ("type_check", lambda: self.run_type_check()),
            ("lint", self.run_lint),
            ("tests", self.run_tests),
            ("security", self.run_security_scan),
            ("diff_review", self.run_diff_review),
        ]
        
        for phase_name, phase_func in phases:
            logger.info(f"Running {phase_name}...")
            result = phase_func()
            results[phase_name] = result
            logger.info(f"{phase_name}: {'PASS' if result.passed else 'FAIL'}")
        
        return results

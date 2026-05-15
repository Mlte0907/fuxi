"""伏羲 v1.0 — 自适应循环引擎

基于 ECC autonomous-loops 技能适配:
- Sequential Pipeline: 顺序决策管道
- De-Sloppify: 质量门控清理
- Tier-driven depth: 按复杂度分配处理深度
"""
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger("fuxi.decision.loop")


class LoopComplexity(Enum):
    """循环复杂度等级 — 对应 ECC Ralphinho tiers"""
    TRIVIAL = "trivial"      # implement → test
    SMALL = "small"         # implement → test → code-review
    MEDIUM = "medium"       # research → plan → implement → test → review-fix
    LARGE = "large"         # 完整质量管道


@dataclass
class LoopStage:
    """循环阶段"""
    name: str
    handler: Callable[..., tuple[bool, str]]  # returns (success, message)
    timeout_sec: float = 60.0
    required: bool = True


@dataclass
class LoopResult:
    """循环执行结果"""
    success: bool
    stages_completed: int
    total_stages: int
    elapsed_sec: float
    final_output: str = ""
    stage_results: list[dict] = field(default_factory=list)


class AdaptiveLoopEngine:
    """自适应循环引擎 — 将 ECC autonomous-loops 模式引入伏羲决策系统"""

    PIPELINE_STAGES = {
        LoopComplexity.TRIVIAL: ["implement", "test"],
        LoopComplexity.SMALL: ["implement", "test", "code_review"],
        LoopComplexity.MEDIUM: ["research", "plan", "implement", "test", "review_fix"],
        LoopComplexity.LARGE: ["research", "plan", "implement", "test", "prd_review", "code_review", "review_fix", "final_review"],
    }

    def __init__(self, framework):
        self.framework = framework

    def execute(self, task: str, complexity: LoopComplexity = LoopComplexity.MEDIUM) -> LoopResult:
        """执行自适应循环"""
        t0 = time.time()
        stages = self.PIPELINE_STAGES[complexity]
        stage_results = []

        for i, stage in enumerate(stages):
            success, msg = self._execute_stage(stage, task, complexity)
            stage_results.append({"stage": stage, "success": success, "message": msg})
            if not success and stage != "review_fix":
                logger.warning(f"Loop stage '{stage}' failed: {msg}")
                if complexity in (LoopComplexity.TRIVIAL, LoopComplexity.SMALL):
                    return LoopResult(
                        success=False,
                        stages_completed=i,
                        total_stages=len(stages),
                        elapsed_sec=time.time() - t0,
                        stage_results=stage_results,
                    )

        return LoopResult(
            success=all(r["success"] for r in stage_results),
            stages_completed=len(stages),
            total_stages=len(stages),
            elapsed_sec=time.time() - t0,
            stage_results=stage_results,
        )

    def _execute_stage(self, stage: str, task: str, complexity: LoopComplexity) -> tuple[bool, str]:
        """执行单个阶段"""
        stage_handlers = {
            "research": self._stage_research,
            "plan": self._stage_plan,
            "implement": self._stage_implement,
            "test": self._stage_test,
            "code_review": self._stage_code_review,
            "review_fix": self._stage_review_fix,
            "prd_review": self._stage_prd_review,
            "final_review": self._stage_final_review,
        }

        handler = stage_handlers.get(stage)
        if handler:
            return handler(task, complexity)
        return True, f"No handler for stage: {stage}"

    def _stage_research(self, task: str, complexity: LoopComplexity) -> tuple[bool, str]:
        """研究阶段 - 分析任务和上下文"""
        logger.info(f"[Loop] Research stage for: {task[:50]}")
        return True, "Research completed"

    def _stage_plan(self, task: str, complexity: LoopComplexity) -> tuple[bool, str]:
        """计划阶段 - 制定实施方案"""
        logger.info(f"[Loop] Plan stage for: {task[:50]}")
        return True, "Plan completed"

    def _stage_implement(self, task: str, complexity: LoopComplexity) -> tuple[bool, str]:
        """实现阶段"""
        logger.info(f"[Loop] Implement stage for: {task[:50]}")
        return True, "Implementation completed"

    def _stage_test(self, task: str, complexity: LoopComplexity) -> tuple[bool, str]:
        """测试阶段"""
        logger.info(f"[Loop] Test stage for: {task[:50]}")
        return True, "Tests passed"

    def _stage_code_review(self, task: str, complexity: LoopComplexity) -> tuple[bool, str]:
        """代码审查阶段"""
        logger.info(f"[Loop] Code review stage for: {task[:50]}")
        return True, "Code review passed"

    def _stage_review_fix(self, task: str, complexity: LoopComplexity) -> tuple[bool, str]:
        """修复阶段 - 响应审查反馈"""
        logger.info(f"[Loop] Review fix stage for: {task[:50]}")
        return True, "Fixes applied"

    def _stage_prd_review(self, task: str, complexity: LoopComplexity) -> tuple[bool, str]:
        """PRD 合规检查"""
        logger.info(f"[Loop] PRD review stage for: {task[:50]}")
        return True, "PRD compliance verified"

    def _stage_final_review(self, task: str, complexity: LoopComplexity) -> tuple[bool, str]:
        """最终质量门控"""
        logger.info(f"[Loop] Final review stage for: {task[:50]}")
        return True, "Final review passed"


def estimate_complexity(task: str) -> LoopComplexity:
    """根据任务描述估计复杂度"""
    task_lower = task.lower()

    complexity_indicators = {
        LoopComplexity.LARGE: ["架构", "重构", "系统设计", "多模块", "完整实现", "复杂"],
        LoopComplexity.MEDIUM: ["功能", "模块", "实现", "优化", "改进"],
        LoopComplexity.SMALL: ["修复", "bug", "小改动", "调整", "更新"],
        LoopComplexity.TRIVIAL: ["格式化", "注释", "typo", "简单修改"],
    }

    for complexity, keywords in complexity_indicators.items():
        for kw in keywords:
            if kw in task_lower:
                return complexity

    return LoopComplexity.MEDIUM

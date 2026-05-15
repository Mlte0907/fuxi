"""伏羲 v1.0 — 成本感知模型路由

适配自 ECC cost-aware-llm-pipeline:
- Immutable CostTracker (frozen dataclass)
- Narrow Retry Logic (指数退避)
- Model Routing by Task Complexity
"""
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable
from datetime import datetime

logger = logging.getLogger("fuxi.agent.cost_tracker")

# 模型成本常数 (USD per 1M tokens)
MODEL_COSTS = {
    "MiniMax-M2.7": {"input": 0.0, "output": 0.0},  # 套餐
    "deepseek/deepseek-v4-pro": {"input": 0.55, "output": 2.20},
    "openrouter/owl-alpha": {"input": 0.0, "output": 0.0},  # 免费
}

@dataclass(frozen=True, slots=True)
class CostRecord:
    """单次API调用成本记录"""
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass(frozen=True, slots=True)
class CostTracker:
    """不可变成本追踪器"""
    budget_limit: float = 10.0
    records: tuple[CostRecord, ...] = ()
    
    def add(self, record: CostRecord) -> "CostTracker":
        """返回新的tracker (从不修改self)"""
        return CostTracker(
            budget_limit=self.budget_limit,
            records=(*self.records, record),
        )
    
    @property
    def total_cost(self) -> float:
        return sum(r.cost_usd for r in self.records)
    
    @property
    def over_budget(self) -> bool:
        return self.total_cost > self.budget_limit
    
    @property
    def total_tokens(self) -> tuple[int, int]:
        inp = sum(r.input_tokens for r in self.records)
        out = sum(r.output_tokens for r in self.records)
        return inp, out


# 重试错误类型
_RETRYABLE_ERRORS = (
    "APIConnectionError",
    "RateLimitError", 
    "InternalServerError",
    "Timeout",
)
_MAX_RETRIES = 3


def select_model_by_complexity(task_type: str, text_length: int = 0, 
                               force_model: Optional[str] = None) -> str:
    """根据任务复杂度选择模型"""
    if force_model:
        return force_model
    
    # 简单任务 → Haiku (免费/低成本)
    if task_type in ("classification", "boilerplate", "narrow_edit"):
        return "deepseek/deepseek-v4-pro"  # 低成本
    
    # 中等任务 → Sonnet
    if task_type in ("implementation", "refactor", "search"):
        return "MiniMax-M2.7"  # 套餐内
    
    # 复杂任务 → Opus
    if task_type in ("architecture", "root_cause", "multi_file"):
        return "MiniMax-M2.7"  # 用套餐
    
    return "MiniMax-M2.7"


def call_with_retry(func: Callable, *, max_retries: int = _MAX_RETRIES) -> any:
    """指数退避重试 (仅限瞬态错误)"""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            error_name = type(e).__name__
            is_retryable = any(r in error_name for r in _RETRYABLE_ERRORS)
            
            if not is_retryable or attempt == max_retries - 1:
                logger.warning(f"Non-retryable error or max retries: {error_name}")
                raise
            
            wait_time = 2 ** attempt
            logger.info(f"Retry {attempt+1}/{max_retries} after {wait_time}s: {error_name}")
            time.sleep(wait_time)


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """计算API调用成本"""
    costs = MODEL_COSTS.get(model, {"input": 0.0, "output": 0.0})
    return (input_tokens / 1_000_000) * costs["input"] + \
           (output_tokens / 1_000_000) * costs["output"]

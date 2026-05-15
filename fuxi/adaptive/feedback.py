"""伏羲 v1.0 — 自适应反馈闭环

评估参数调整效果，自动回滚不良调整。"""
import time
from typing import Optional


class AdaptiveFeedbackLoop:
    """自适应反馈闭环 — 评估参数调整效果，自动回滚不良调整"""

    EVALUATION_WINDOW = 3600  # 1小时后评估效果

    def __init__(self):
        self._adjustment_history: list[dict] = []

    def record_adjustment(self, params_before: dict, params_after: dict,
                          signals_before: dict, reason: str):
        self._adjustment_history.append({
            "timestamp": time.time(),
            "params_before": params_before,
            "params_after": params_after,
            "signals_before": signals_before,
            "reason": reason,
        })

    def evaluate(self, current_signals: dict) -> Optional[dict]:
        """评估最近一次调整的效果"""
        if not self._adjustment_history:
            return None
        last = self._adjustment_history[-1]
        elapsed = time.time() - last["timestamp"]
        if elapsed < self.EVALUATION_WINDOW:
            return None  # 尚未到评估时间

        before = last["signals_before"]
        after = current_signals

        satisfaction_delta = (
            after.get("search_satisfaction", 0.5) -
            before.get("search_satisfaction", 0.5)
        )

        if satisfaction_delta < -0.1:
            return {
                "action": "rollback",
                "reason": f"搜索满意度下降 {satisfaction_delta:.2f}",
                "rollback_to": last["params_before"],
            }
        elif satisfaction_delta > 0.05:
            return {
                "action": "reinforce",
                "reason": f"搜索满意度提升 {satisfaction_delta:.2f}",
            }
        else:
            return {
                "action": "maintain",
                "reason": "无显著变化",
            }

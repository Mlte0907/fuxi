"""伏羲 v1.0 — 差分隐私机制

拉普拉斯机制 + 隐私预算管理 + 差分隐私统计。"""
import math
import random
import time
from typing import Dict, List, Optional


class LaplaceMechanism:
    """拉普拉斯机制 — 差分隐私的标准实现"""

    @staticmethod
    def add_noise(value: float, sensitivity: float, epsilon: float) -> float:
        """对数值添加拉普拉斯噪声"""
        scale = sensitivity / epsilon
        noise = random.gauss(0, scale * math.sqrt(2))
        return value + noise

    @staticmethod
    def add_noise_to_dict(data: Dict[str, float],
                          sensitivity: Dict[str, float],
                          epsilon: float) -> Dict[str, float]:
        """对字典中每个数值字段添加噪声"""
        result = {}
        for key, value in data.items():
            if key in sensitivity and isinstance(value, (int, float)):
                result[key] = LaplaceMechanism.add_noise(
                    value, sensitivity[key], epsilon
                )
            else:
                result[key] = value
        return result


class PrivacyBudget:
    """隐私预算管理器 — 跟踪和限制隐私预算消耗"""

    def __init__(self, total_epsilon: float = 1.0, delta: float = 1e-5):
        self._total = total_epsilon
        self._consumed = 0.0
        self._delta = delta
        self._queries = []

    @property
    def remaining(self) -> float:
        return max(0, self._total - self._consumed)

    @property
    def exhausted(self) -> bool:
        return self._consumed >= self._total

    def allocate(self, epsilon: float, query_name: str = "") -> bool:
        """分配隐私预算，返回是否成功"""
        if self._consumed + epsilon > self._total:
            return False
        self._consumed += epsilon
        self._queries.append({
            "name": query_name, "epsilon": epsilon,
            "consumed_at": time.time(),
        })
        return True

    def reset(self):
        """重置隐私预算（新的时间窗口）"""
        self._consumed = 0.0
        self._queries = []


class DPStatistics:
    """差分隐私统计 — 对记忆统计结果添加噪声"""

    COUNT_SENSITIVITY = 1.0
    AVG_SENSITIVITY = 1.0
    RATIO_SENSITIVITY = 1.0

    def __init__(self, epsilon: float = 0.5):
        self._epsilon = epsilon
        self._budget = PrivacyBudget(total_epsilon=epsilon * 10)

    def dp_count(self, true_count: int, query_name: str = "") -> int:
        """差分隐私计数"""
        eps = self._epsilon / 10
        if not self._budget.allocate(eps, query_name):
            return -1
        noisy = LaplaceMechanism.add_noise(
            true_count, self.COUNT_SENSITIVITY, eps
        )
        return max(0, int(round(noisy)))

    def dp_average(self, values: List[float], value_range: float,
                   query_name: str = "") -> Optional[float]:
        """差分隐私平均值"""
        if not values:
            return None
        eps = self._epsilon / 10
        if not self._budget.allocate(eps, query_name):
            return None
        true_avg = sum(values) / len(values)
        sensitivity = value_range / len(values)
        return LaplaceMechanism.add_noise(true_avg, sensitivity, eps)

    def dp_histogram(self, counts: Dict[str, int],
                     query_name: str = "") -> Dict[str, int]:
        """差分隐私直方图"""
        eps_per_bin = self._epsilon / (len(counts) * 10)
        result = {}
        for key, count in counts.items():
            if self._budget.allocate(eps_per_bin, f"{query_name}:{key}"):
                result[key] = max(0, int(round(
                    LaplaceMechanism.add_noise(count, 1.0, eps_per_bin)
                )))
            else:
                result[key] = -1
        return result

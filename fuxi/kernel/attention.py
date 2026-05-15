"""伏羲 v1.0 注意力系统（6策略 + 预算分配）"""
import threading
import time
from enum import Enum
from typing import Dict


class AttentionStrategy(Enum):
    BOTTOM_UP = "bottom_up"
    TOP_DOWN = "top_down"
    FOCUS = "focus"
    EXPLORE = "explore"
    EMOTION_DRIVEN = "emotion"
    URGENCY_DRIVEN = "urgency"

class AttentionSystem:
    def __init__(self):
        self._active_strategy = AttentionStrategy.BOTTOM_UP
        self._budget = 100
        self._last_switch = time.time()
        self._strategy_counts: Dict[AttentionStrategy, int] = dict.fromkeys(AttentionStrategy, 0)
        self._lock = threading.Lock()

    @property
    def active_strategy(self) -> AttentionStrategy:
        return self._active_strategy

    @property
    def budget(self) -> int:
        return self._budget

    def allocate(self, amount: int) -> bool:
        with self._lock:
            if self._budget >= amount:
                self._budget -= amount
                return True
            return False

    def replenish(self, amount: int = 10):
        with self._lock:
            self._budget = min(100, self._budget + amount)

    def switch(self, strategy: AttentionStrategy, _reason: str = ""):
        with self._lock:
            old = self._active_strategy
            self._active_strategy = strategy
            self._strategy_counts[strategy] += 1
            self._last_switch = time.time()
        return old, strategy

    def evaluate(self, emotional_valence: float, urgency: float, novelty: float) -> AttentionStrategy:
        if urgency > 0.7:
            return AttentionStrategy.URGENCY_DRIVEN
        if emotional_valence > 0.6:
            return AttentionStrategy.EMOTION_DRIVEN
        if novelty > 0.5:
            return AttentionStrategy.EXPLORE
        return AttentionStrategy.BOTTOM_UP

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "active_strategy": self._active_strategy.value,
                "budget": self._budget,
                "counts": {s.value: c for s, c in self._strategy_counts.items()},
            }


_attention_system: AttentionSystem | None = None


def get_attention_system() -> AttentionSystem:
    global _attention_system
    if _attention_system is None:
        _attention_system = AttentionSystem()
    return _attention_system

"""伏羲 v1.0 — 行为信号采集器

挂载在 EventBus 上，聚合用户行为统计。
"""
import time
from typing import Dict, List, Tuple

BEHAVIOR_SIGNALS = {
    "memory.accessed": "记忆被召回/搜索命中",
    "memory.created": "新记忆写入",
    "memory.updated": "记忆被更新",
    "memory.deleted": "记忆被删除",
    "memory.recalled_but_irrelevant": "召回但用户标记不相关",
    "search.query": "搜索查询",
    "search.click": "搜索结果被点击/采纳",
    "search.refine": "搜索后立即重新搜索（暗示结果不满意）",
    "drawer.access_frequency": "抽屉访问频率",
}


class BehaviorCollector:
    """行为信号采集器 — 挂载在 EventBus 上，聚合行为统计"""

    def __init__(self):
        self._window = 3600  # 1小时滑动窗口
        self._counters: Dict[str, List[Tuple[float, dict]]] = {}

    def on_event(self, event):
        """EventBus 订阅处理器"""
        signal_type = event.type
        if signal_type not in BEHAVIOR_SIGNALS:
            return
        now = time.time()
        self._counters.setdefault(signal_type, []).append((now, event.data))
        cutoff = now - self._window
        self._counters[signal_type] = [
            (ts, d) for ts, d in self._counters[signal_type] if ts > cutoff
        ]

    def get_signal_rates(self) -> dict:
        """获取各信号在窗口内的频率"""
        now = time.time()
        rates = {}
        for signal, events in self._counters.items():
            recent = [e for ts, e in events if now - ts < self._window]
            rates[signal] = len(recent) / max(self._window, 1)
        return rates

    def get_user_profile_signals(self) -> dict:
        """提取用户行为画像特征"""
        rates = self.get_signal_rates()
        return {
            "recall_frequency": rates.get("memory.accessed", 0),
            "creation_frequency": rates.get("memory.created", 0),
            "search_refinement_rate": self._search_refinement_rate(),
            "longterm_access_ratio": self._drawer_ratio("longterm"),
            "shortterm_access_ratio": self._drawer_ratio("default"),
            "avg_importance_of_accessed": self._avg_importance_accessed(),
            "search_satisfaction": self._search_satisfaction(),
        }

    def _search_satisfaction(self) -> float:
        clicks = len(self._counters.get("search.click", []))
        queries = len(self._counters.get("search.query", []))
        refines = len(self._counters.get("search.refine", []))
        total = queries + refines
        return clicks / total if total > 0 else 0.5

    def _search_refinement_rate(self) -> float:
        refines = len(self._counters.get("search.refine", []))
        queries = len(self._counters.get("search.query", []))
        return refines / queries if queries > 0 else 0.0

    def _drawer_ratio(self, drawer_id: str) -> float:
        accessed = [e for _, e in self._counters.get("memory.accessed", [])
                    if e.get("drawer_id") == drawer_id]
        total = len(self._counters.get("memory.accessed", []))
        return len(accessed) / total if total > 0 else 0.0

    def _avg_importance_accessed(self) -> float:
        events = self._counters.get("memory.accessed", [])
        if not events:
            return 0.5
        imps = [e.get("importance", 0.5) for _, e in events]
        return sum(imps) / len(imps)


_collector: BehaviorCollector = None


def get_behavior_collector() -> BehaviorCollector:
    global _collector
    if _collector is None:
        _collector = BehaviorCollector()
    return _collector

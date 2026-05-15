"""伏羲 v1.0 工作记忆（Miller定律7槽位 + 注意力衰减）"""
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fuxi.config import config
from fuxi.kernel.event_bus import get_event_bus


@dataclass
class WMItem:
    id: str
    content: str
    source: str = "perception"
    emotional_valence: float = 0.0
    urgency: float = 0.0
    tokens: int = 0
    activation: float = 1.0
    created_at: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)
    access_count: int = 0

    def touch(self):
        self.last_access = time.time()
        self.access_count += 1
        self.activation = min(1.0, self.activation + 0.1)


class WorkingMemory:
    def __init__(self, capacity: Optional[int] = None):
        self.capacity = capacity or config.wm_capacity
        self._buffer: OrderedDict = OrderedDict()
        self._decay_rate = 0.02
        self._emotional_boost = 0.1
        self._lock = threading.Lock()
        self._total_pushed = 0
        self._evictions = 0
        self._total_tokens = 0
        self._scratchpad: Dict[str, Any] = {}
        self._bus = get_event_bus()

    @property
    def slots(self) -> List[WMItem]:
        return list(self._buffer.values())

    @property
    def focus(self) -> Optional[WMItem]:
        return self._buffer[next(reversed(self._buffer))] if self._buffer else None

    @property
    def current_tokens(self) -> int:
        return self._total_tokens

    def usage(self) -> float:
        """返回工作记忆使用率 (0.0 ~ 1.0)"""
        if self.capacity == 0:
            return 0.0
        return len(self._buffer) / self.capacity

    def push(self, item: WMItem) -> Optional[WMItem]:
        from fuxi.kernel.event_bus import Event, EventPriority
        with self._lock:
            self._total_pushed += 1
            self._total_tokens += item.tokens
            item.touch()
            evicted = None
            if item.id in self._buffer:
                self._buffer.move_to_end(item.id)
            else:
                while len(self._buffer) >= self.capacity:
                    evicted = self._evict()
            self._buffer[item.id] = item
        self._bus.publish(Event(
            type="wm.item_pushed",
            data={"id": item.id, "source": item.source, "slots_used": len(self._buffer)},
            priority=EventPriority.LOW,
            source="working_memory",
        ))
        return evicted

    def _evict(self) -> Optional[WMItem]:
        from fuxi.kernel.event_bus import Event, EventPriority
        if not self._buffer:
            return None
        for item_id, item in list(self._buffer.items()):
            if item.emotional_valence > 0.7:
                continue
            evicted = self._buffer.pop(item_id)
            self._evictions += 1
            self._total_tokens = max(0, self._total_tokens - evicted.tokens)
            self._bus.publish(Event(
                type="wm.item_evicted",
                data={"id": evicted.id, "activation": round(evicted.activation, 4), "reason": "low_activation"},
                priority=EventPriority.LOW,
                source="working_memory",
            ))
            return evicted
        evicted = self._buffer.popitem(last=False)
        self._evictions += 1
        self._total_tokens = max(0, self._total_tokens - evicted[1].tokens)
        self._bus.publish(Event(
            type="wm.item_evicted",
            data={"id": evicted[1].id, "activation": round(evicted[1].activation, 4), "reason": "overflow"},
            priority=EventPriority.LOW,
            source="working_memory",
        ))
        return evicted[1]

    def get(self, item_id: str) -> Optional[WMItem]:
        with self._lock:
            item = self._buffer.get(item_id)
            if item:
                item.last_access = time.time()
                item.access_count += 1
                self._buffer.move_to_end(item_id)
            return item

    def decay_tick(self, dt: float = 1.0):
        with self._lock:
            to_remove = []
            for item_id, item in self._buffer.items():
                item.activation *= (1 - self._decay_rate * dt)
                if item.emotional_valence > 0.5:
                    item.activation += self._emotional_boost * item.emotional_valence * dt
                if item.activation < 0.1:
                    to_remove.append(item_id)
            for item_id in to_remove:
                evicted = self._buffer.pop(item_id, None)
                if evicted:
                    self._evictions += 1
                    self._total_tokens = max(0, self._total_tokens - evicted.tokens)

    def clear(self):
        with self._lock:
            self._buffer.clear()
            self._total_tokens = 0

    @property
    def context(self) -> str:
        parts = []
        for item in list(self._buffer.values())[-3:]:
            prefix = "[焦点]" if item is self.focus else ""
            parts.append(f"{prefix} {item.content[:50]}")
        return "\n".join(parts)

    @property
    def stats(self) -> dict:
        return {
            "capacity": self.capacity,
            "slots_used": len(self._buffer),
            "total_pushed": self._total_pushed,
            "evictions": self._evictions,
            "total_tokens": self._total_tokens,
        }

    def adapt_capacity(self):
        """v1.1: 根据驱逐率自适应调整容量（每100次推送检查一次）"""
        if not config.wm_capacity_adaptive:
            return
        if self._total_pushed < 100:
            return
        eviction_rate = self._evictions / self._total_pushed
        old_cap = self.capacity
        if eviction_rate > 0.3 and self.capacity < 15:
            self.capacity = min(15, self.capacity + 2)
            logger.info(f"WM capacity: {old_cap} → {self.capacity} (eviction_rate={eviction_rate:.2f})")
        elif eviction_rate < 0.05 and self.capacity > 5:
            self.capacity = max(5, self.capacity - 1)
            logger.info(f"WM capacity: {old_cap} → {self.capacity} (eviction_rate={eviction_rate:.2f})")


_wm_instance: WorkingMemory | None = None


def get_working_memory() -> WorkingMemory:
    global _wm_instance
    if _wm_instance is None:
        _wm_instance = WorkingMemory()
    return _wm_instance

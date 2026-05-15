"""伏羲 v1.0 统一事件总线"""
import asyncio
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List

logger = logging.getLogger("fuxi.kernel.event_bus")

class EventPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3

@dataclass
class Event:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    priority: EventPriority = EventPriority.NORMAL
    timestamp: float = field(default_factory=time.time)
    source: str = ""

class EventBus:
    """统一事件总线 — 同步和异步双模式"""
    _instance = None

    def __init__(self):
        self._sync_handlers: Dict[str, List[Callable]] = {}
        self._async_handlers: Dict[str, List[Callable]] = {}
        self._event_log: deque = deque(maxlen=1000)
        self._lock = threading.Lock()
        self._running = False
        self._async_task = None

    @classmethod
    def get(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def subscribe(self, event_type: str, handler: Callable, async_mode: bool = False):
        with self._lock:
            target = self._async_handlers if async_mode else self._sync_handlers
            target.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: Callable):
        with self._lock:
            for handlers in [self._sync_handlers, self._async_handlers]:
                if event_type in handlers:
                    handlers[event_type] = [h for h in handlers[event_type] if h is not handler]

    def publish(self, event: Event):
        self._event_log.append(event)
        handlers = self._sync_handlers.get(event.type, []) + self._sync_handlers.get("*", [])
        for h in handlers:
            try:
                h(event)
            except Exception as e:
                logger.error(f"Event handler error [{event.type}]: {e}")

    async def publish_async(self, event: Event):
        self._event_log.append(event)
        async_handlers = self._async_handlers.get(event.type, [])
        sync_handlers = self._sync_handlers.get(event.type, [])
        for h in async_handlers + sync_handlers:
            try:
                if asyncio.iscoroutinefunction(h):
                    await h(event)
                else:
                    h(event)
            except Exception as e:
                logger.error(f"Async handler error [{event.type}]: {e}")

    def clear(self):
        with self._lock:
            self._sync_handlers.clear()
            self._async_handlers.clear()
            self._event_log.clear()

    @property
    def recent_events(self) -> List[Event]:
        return list(self._event_log)

    @property
    def stats(self) -> Dict:
        return {
            "total_subscribers": sum(len(v) for v in self._sync_handlers.values()) +
                                 sum(len(v) for v in self._async_handlers.values()),
            "event_types": len(set(list(self._sync_handlers.keys()) +
                                   list(self._async_handlers.keys()))),
            "recent_events": len(self._event_log),
        }


def get_event_bus() -> EventBus:
    return EventBus.get()

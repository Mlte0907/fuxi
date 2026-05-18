"""伏羲 v1.0 — 认知引擎基类 + 注册表"""
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from fuxi.kernel.event_bus import Event, get_event_bus

logger = logging.getLogger("fuxi.engines.base")


@dataclass
class EngineState:
    running: bool = False
    last_run: float = 0.0
    run_count: int = 0
    error_count: int = 0
    metadata: dict = field(default_factory=dict)


class CognitiveEngine(ABC):
    """认知引擎基类"""

    name: str = "base"
    experimental: bool = False
    interval: int = 300  # 默认每5分钟运行一次
    priority: int = 5  # 1-10, 越高越优先

    def __init__(self):
        self._state = EngineState()
        self._state.metadata["_pending_events"] = []
        self._lock = threading.Lock()
        self._setup_subscriptions()
        # 从数据库恢复引擎状态（如果存在）
        self._restore_state()

    def _setup_subscriptions(self):
        """子类覆写以注册事件订阅。返回 {event_type: handler} 字典。"""
        subs = self._get_subscriptions()
        if subs:
            bus = get_event_bus()
            for event_type, handler in subs.items():
                bus.subscribe(event_type, handler)
                logger.debug(f"[{self.name}] subscribed to '{event_type}'")

    def _get_subscriptions(self) -> Dict[str, Callable]:
        """子类覆写：返回要订阅的 {event_type: handler}"""
        return {}

    def _on_event(self, event: Event):
        """默认事件处理：将事件暂存到 pending 队列，在下次 run() 中处理"""
        pending = self._state.metadata.setdefault("_pending_events", [])
        pending.append({"type": event.type, "data": event.data, "source": event.source, "ts": event.timestamp})
        if len(pending) > 50:  # 限制队列长度
            pending.pop(0)

    def _pop_pending_events(self) -> List[dict]:
        """取出并清空 pending 事件队列"""
        pending = self._state.metadata.get("_pending_events", [])
        self._state.metadata["_pending_events"] = []
        return pending

    @abstractmethod
    def run(self) -> dict:
        """执行认知循环，返回结果字典"""
        ...

    def health_check(self) -> dict:
        return {
            "name": self.name,
            "running": self._state.running,
            "last_run": self._state.last_run,
            "run_count": self._state.run_count,
            "error_count": self._state.error_count,
        }

    def get_state(self) -> dict:
        return {
            "name": self.name,
            "experimental": self.experimental,
            "interval": self.interval,
            "priority": self.priority,
            **self.health_check(),
            "metadata": self._state.metadata,
        }

    def start(self):
        self._state.running = True
        self._state.metadata.pop("_paused", None)
        logger.info(f"Engine [{self.name}] started")

    def stop(self):
        self._state.running = False
        logger.info(f"Engine [{self.name}] stopped")

    def pause(self):
        self._state.metadata["_paused"] = True
        logger.info(f"Engine [{self.name}] paused")

    def resume(self):
        self._state.metadata.pop("_paused", None)
        logger.info(f"Engine [{self.name}] resumed")

    def _restore_state(self):
        """从数据库恢复引擎状态，确保重启后引擎状态一致"""
        try:
            from fuxi.store.connection import get_pool
            pool = get_pool()
            row = pool.fetchone(
                "SELECT state_json FROM engine_states WHERE engine_name=?",
                (self.name,)
            )
            if row:
                state = json.loads(row["state_json"])
                self._state.running = state.get("running", False)
                self._state.last_run = state.get("last_run", 0.0)
                self._state.run_count = state.get("run_count", 0)
                self._state.error_count = state.get("error_count", 0)
                if "metadata" in state:
                    # 合并 metadata，保留 pending_events
                    for k, v in state["metadata"].items():
                        if k != "_pending_events":
                            self._state.metadata[k] = v
                logger.info(f"[{self.name}] state restored: running={self._state.running}, run_count={self._state.run_count}")
        except Exception as e:
            logger.warning(f"[{self.name}] failed to restore state: {e}")

    def _execute(self) -> dict:
        """带错误统计的执行包装"""
        import asyncio
        import inspect
        from fuxi.kernel.event_bus import EventPriority
        from fuxi.store.connection import get_pool
        from datetime import datetime
        t0 = time.time()
        try:
            if inspect.iscoroutinefunction(self.run):
                result = asyncio.run(self.run())
            else:
                result = self.run()
            elapsed_ms = round((time.time() - t0) * 1000)
            self._state.last_run = time.time()
            self._state.run_count += 1
            get_event_bus().publish(Event(
                type="engine.executed",
                data={"engine": self.name, "status": "ok", "elapsed_ms": elapsed_ms, "run_count": self._state.run_count},
                priority=EventPriority.LOW,
                source=f"engine:{self.name}",
            ))
            # 持久化 run_count 和 last_run 到 engine_states
            pool = get_pool()
            with pool.connection() as c:
                state_json = json.dumps({
                    "running": self._state.running,
                    "last_run": self._state.last_run,
                    "run_count": self._state.run_count,
                    "error_count": self._state.error_count,
                    "metadata": self._state.metadata,
                }, ensure_ascii=False)
                c.execute(
                    "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
                    "VALUES (?,?,?)",
                    (self.name, state_json, datetime.now().isoformat())
                )
            return result
        except Exception as e:
            self._state.error_count += 1
            get_event_bus().publish(Event(
                type="engine.executed",
                data={"engine": self.name, "status": "error", "error": str(e)},
                priority=EventPriority.HIGH,
                source=f"engine:{self.name}",
            ))
            logger.error(f"Engine [{self.name}] error: {e}")
            raise


class EngineRegistry:
    """引擎注册表 — 实例单例模式，每个实例独立持有引擎"""

    def __init__(self):
        self._engines: Dict[str, CognitiveEngine] = {}
        self._lock = threading.Lock()

    def register(self, name: str, experimental: bool = False):
        """注册引擎的装饰器"""
        def decorator(engine_cls):
            if name in self._engines:
                return engine_cls  # Skip re-registration
            self._engines[name] = engine_cls()
            self._engines[name].name = name
            self._engines[name].experimental = experimental
            logger.debug(f"Registered engine: {name}{' (exp)' if experimental else ''}")
            return engine_cls
        return decorator

    def get(self, name: str) -> Optional[CognitiveEngine]:
        return self._engines.get(name)

    def list_all(self, include_tier: bool = True) -> List[dict]:
        """List all engines, optionally with tier info."""
        from fuxi.engines import get_enabled_engines
        enabled_engines = get_enabled_engines()
        result = []
        for name, e in self._engines.items():
            info = {
                "name": name,
                "experimental": e.experimental,
                "running": e._state.running,
                "priority": e.priority,
                "interval": e.interval,
                "health": e.health_check(),
            }
            if include_tier:
                info["tier"] = "enabled" if enabled_engines is None or name in enabled_engines else "disabled"
            result.append(info)
        return result

    def list_by_tier(self, tier: str | None = None) -> List[dict]:
        """List engines filtered by tier. tier=None uses config.engine_tier."""
        from fuxi.config import config
        from fuxi.engines import ENGINE_TIERS, get_enabled_engines
        target_tier = tier if tier is not None else config.engine_tier
        tier_filter = ENGINE_TIERS.get(target_tier, ENGINE_TIERS["standard"])
        enabled = get_enabled_engines()
        result = []
        for name, e in self._engines.items():
            info = {
                "name": name,
                "experimental": e.experimental,
                "running": e._state.running,
                "priority": e.priority,
                "interval": e.interval,
                "tier_label": target_tier,
                "health": e.health_check(),
            }
            info["in_tier"] = name in tier_filter
            info["tier_status"] = "enabled" if enabled is None or name in enabled else "disabled"
            result.append(info)
        return result

    def get_enabled(self, include_experimental: bool = False) -> List[CognitiveEngine]:
        return [
            e for e in self._engines.values()
            if (include_experimental or not e.experimental)
        ]

    def start_all(self, include_experimental: bool = False, tier: str | None = None):
        """Start engines, optionally filtered by tier.
        tier=None uses config.engine_tier.
        """
        from fuxi.engines import get_enabled_engines
        tier_filter = get_enabled_engines() if tier is None else None
        started = 0
        for name, engine in self._engines.items():
            if tier_filter is not None and name not in tier_filter:
                continue
            if include_experimental or not engine.experimental:
                engine.start()
                started += 1
        logger.info(f"Started {started}/{len(self._engines)} engines")

    def stop_all(self):
        for engine in self._engines.values():
            engine.stop()
        logger.info(f"Stopped {len(self._engines)} engines")

    def run_all(self, include_experimental: bool = False, tier: str | None = None,
                max_workers: int = 8) -> Dict[str, dict]:
        """并行执行所有引擎（按优先级排序），使用 ThreadPoolExecutor"""
        results = {}
        from fuxi.engines import get_enabled_engines
        tier_filter = get_enabled_engines() if tier is None else None
        engines = sorted(
            self._engines.items(),
            key=lambda x: x[1].priority, reverse=True
        )
        # Filter engines to run
        runnable = []
        for name, engine in engines:
            if tier_filter is not None and name not in tier_filter:
                continue
            if include_experimental or not engine.experimental:
                runnable.append((name, engine))

        def execute_one(item):
            name, engine = item
            try:
                return name, engine._execute()
            except Exception as e:
                return name, {"error": str(e)}

        # Use ThreadPoolExecutor for parallel execution
        with ThreadPoolExecutor(max_workers=min(max_workers, len(runnable))) as ex:
            futures = {ex.submit(execute_one, item): item for item in runnable}
            for future in as_completed(futures):
                name, result = future.result()
                results[name] = result
        return results

    @property
    def engines(self):
        return self._engines


# ── 单例 ──

_registry: Optional[EngineRegistry] = None


def get_engine_registry() -> EngineRegistry:
    global _registry
    if _registry is None:
        _registry = EngineRegistry()
    return _registry


# 便捷装饰器
def register_engine(name: str, experimental: bool = False):
    return get_engine_registry().register(name, experimental)

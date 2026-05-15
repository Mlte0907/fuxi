"""伏羲 v1.0 — 生命周期管理"""
import logging
import threading
import time
from typing import Callable, List, Optional

logger = logging.getLogger("fuxi.kernel.lifespan")


class Lifespan:
    """管理服务启动/关闭钩子"""

    def __init__(self):
        self._startup_hooks: List[Callable] = []
        self._shutdown_hooks: List[Callable] = []
        self._running = False
        self._bg_threads: List[threading.Thread] = []

    def on_startup(self, fn: Callable):
        self._startup_hooks.append(fn)
        return fn

    def on_shutdown(self, fn: Callable):
        self._shutdown_hooks.append(fn)
        return fn

    def start(self):
        logger.info("Lifespan starting...")
        for hook in self._startup_hooks:
            try:
                hook()
            except Exception as e:
                logger.error(f"Startup hook failed: {e}")

        from fuxi.api.ws import setup_event_bridge
        setup_event_bridge()

        # BUG-002 fix: Subscribe BehaviorCollector to EventBus signals
        try:
            from fuxi.adaptive.signals import get_behavior_collector, BEHAVIOR_SIGNALS
            from fuxi.kernel.event_bus import get_event_bus
            collector = get_behavior_collector()
            bus = get_event_bus()
            for signal_type in BEHAVIOR_SIGNALS:
                bus.subscribe(signal_type, collector.on_event)
            logger.info(f"BehaviorCollector subscribed to {len(BEHAVIOR_SIGNALS)} signal types")
        except Exception as e:
            logger.warning(f"BehaviorCollector EventBus subscription failed (non-fatal): {e}")

        self._running = True

    def stop(self):
        logger.info("Lifespan stopping...")
        self._running = False
        for hook in reversed(self._shutdown_hooks):
            try:
                hook()
            except Exception as e:
                logger.error(f"Shutdown hook failed: {e}")

    def spawn_background(self, target: Callable, name: Optional[str] = None, interval: Optional[int] = None):
        """启动后台守护线程"""
        if interval:

            def _looper():
                while self._running:
                    try:
                        target()
                    except Exception as e:
                        logger.error(f"Background task [{name}] error: {e}")
                    time.sleep(interval)

            thread = threading.Thread(target=_looper, name=name, daemon=True)
        else:
            thread = threading.Thread(target=target, name=name, daemon=True)

        thread.start()
        self._bg_threads.append(thread)
        return thread

    @property
    def running(self) -> bool:
        return self._running

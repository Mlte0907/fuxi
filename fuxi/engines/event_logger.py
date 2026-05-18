"""伏羲 v1.5 — 事件日志引擎

将事件总线中的事件持久化到 event_log 表，
记录伏羲和瑾岚阁在记忆系统中的操作行为。

运行方式:
  - 由 cognitive_loop 定期调度（默认每 1 分钟）
  - 读取事件总线最近事件，写入 event_log 表
"""
import logging
from datetime import datetime

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus

logger = logging.getLogger("fuxi.engine.event_logger")

# 事件日志引擎 - 记录系统操作行为
@register_engine("event_logger", experimental=False)
class EventLoggerEngine(CognitiveEngine):
    """事件日志引擎 — 记录伏羲和瑾岚阁的操作行为"""
    name = "event_logger"
    priority = 8  # 高优先级，确保及时记录
    interval = 60  # 每分钟执行

    def run(self) -> dict:
        bus = get_event_bus()
        recent = bus.recent_events

        if not recent:
            return {"status": "ok", "logged": 0, "reason": "no_events"}

        # 获取上次处理的位置（避免重复处理）
        last_index = self._state.metadata.get("last_event_index", 0)
        events_to_log = recent[last_index:]

        if not events_to_log:
            return {"status": "ok", "logged": 0, "reason": "no_new_events"}

        # 写入 event_log 表
        from fuxi.store.connection import get_pool
        pool = get_pool()

        logged_count = 0
        try:
            with pool.connection() as conn:
                for event in events_to_log:
                    # 跳过内部事件（engine.*）
                    if event.type.startswith("engine.") and event.source.startswith("engine:"):
                        # 只记录高优先级事件或用户可见事件
                        if event.priority.value < EventPriority.HIGH.value:
                            continue

                    event_data = {
                        "type": event.type,
                        "data": event.data,
                        "source": event.source,
                        "priority": event.priority.name,
                    }

                    import json
                    conn.execute(
                        "INSERT INTO event_log (event_type, event_data, source, created_at) VALUES (?, ?, ?, ?)",
                        (event.type, json.dumps(event.data, ensure_ascii=False), event.source, datetime.now().isoformat())
                    )
                    logged_count += 1

                conn.commit()
        except Exception as e:
            logger.warning(f"Event log write failed: {e}")
            return {"status": "error", "error": str(e), "logged": 0}

        # 更新处理位置
        self._state.metadata["last_event_index"] = len(recent)

        return {
            "status": "ok",
            "logged": logged_count,
            "total_events": len(recent),
            "timestamp": datetime.now().isoformat(),
        }
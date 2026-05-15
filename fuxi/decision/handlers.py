"""伏羲 v1.0 — 内置决策处理器

5个内置处理器 + 回滚机制：记忆清理、注意力重分配、引擎优先级调整、主动通知、Agent委派"""
import logging

from fuxi.decision.executor import DecisionExecutor

logger = logging.getLogger("fuxi.decision.handlers")

# ── snapshot / rollback 机制 ──────────────────────────────────────────

_SNAPSHOTS: dict = {}  # decision_id -> snapshot


def snapshot_memory_cleanup(decision_id: str, params: dict) -> dict:
    """memory_cleanup 事前快照 — 记录即将清理的 items（用于回滚）"""
    from fuxi.memory.decay import get_purge_candidates
    dry = get_purge_candidates()
    _SNAPSHOTS[decision_id] = {"purged_ids": [r["id"] for r in dry[:50]]}
    return _SNAPSHOTS[decision_id]


def rollback_memory_cleanup(decision_id: str, params: dict, snapshot: dict) -> dict:
    """memory_cleanup 回滚 — 从 snapshot 恢复被清理的记忆"""
    if not snapshot or "purged_ids" not in snapshot:
        return {"status": "skipped", "reason": "no snapshot"}
    from fuxi.store.connection import get_pool
    pool = get_pool()
    restored = 0
    for item_id in snapshot["purged_ids"]:
        try:
            pool.execute("UPDATE items SET archived=0 WHERE id=?", (item_id,))
            restored += 1
        except Exception as e:
            logger.debug(f"Restore failed for {item_id}: {e}")
    _SNAPSHOTS.pop(decision_id, None)
    logger.info(f"memory_cleanup rollback: restored {restored} items")
    return {"status": "ok", "restored": restored}


def snapshot_attention_reallocate(decision_id: str, params: dict) -> dict:
    """attention 重分配快照 — 记录当前策略"""
    from fuxi.kernel.attention import get_attention_system
    attn = get_attention_system()
    _SNAPSHOTS[decision_id] = {"current_strategy": attn.current_strategy.value}
    return _SNAPSHOTS[decision_id]


def rollback_attention_reallocate(decision_id: str, params: dict, snapshot: dict) -> dict:
    """attention 回滚 — 恢复到原策略"""
    if not snapshot:
        return {"status": "skipped"}
    from fuxi.kernel.attention import AttentionStrategy, get_attention_system
    old_strategy = snapshot.get("current_strategy", "bottom_up")
    get_attention_system().switch(AttentionStrategy(old_strategy), "rollback")
    _SNAPSHOTS.pop(decision_id, None)
    return {"status": "ok", "restored_strategy": old_strategy}


def snapshot_engine_priority_adjust(decision_id: str, params: dict) -> dict:
    """引擎优先级调整快照"""
    from fuxi.engines.base import get_engine_registry
    engine_name = params.get("engine")
    registry = get_engine_registry()
    engine = registry.get(engine_name)
    _SNAPSHOTS[decision_id] = {
        "engine": engine_name,
        "old_priority": engine.priority if engine else None,
    }
    return _SNAPSHOTS[decision_id]


def rollback_engine_priority_adjust(decision_id: str, params: dict, snapshot: dict) -> dict:
    """引擎优先级调整回滚"""
    if not snapshot:
        return {"status": "skipped"}
    from fuxi.engines.base import get_engine_registry
    engine_name = snapshot.get("engine")
    old_priority = snapshot.get("old_priority")
    registry = get_engine_registry()
    engine = registry.get(engine_name)
    if engine and old_priority is not None:
        engine.priority = old_priority
        logger.info(f"engine_priority rollback: {engine_name} -> {old_priority}")
    _SNAPSHOTS.pop(decision_id, None)
    return {"status": "ok", "restored_priority": old_priority}


def snapshot_proactive_notify(decision_id: str, params: dict) -> dict:
    """proactive_notify 快照 — 仅为空（通知回滚意义不大）"""
    _SNAPSHOTS[decision_id] = {}
    return {}


def rollback_proactive_notify(decision_id: str, params: dict, snapshot: dict) -> dict:
    """proactive_notify 回滚 — 暂不支持（已写入的记忆难以撤回）"""
    _SNAPSHOTS.pop(decision_id, None)
    return {"status": "skipped", "reason": "notification cannot be retracted"}


def snapshot_agent_delegate(decision_id: str, params: dict) -> dict:
    """agent_delegate 快照"""
    _SNAPSHOTS[decision_id] = {"agent_id": params.get("agent_id"), "message": params.get("message", "")[:100]}
    return _SNAPSHOTS[decision_id]


def rollback_agent_delegate(decision_id: str, params: dict, snapshot: dict) -> dict:
    """agent_delegate 回滚 — 仅记录，无法撤销已发送消息"""
    _SNAPSHOTS.pop(decision_id, None)
    return {"status": "skipped", "reason": "agent action cannot be retracted"}


# ── 执行处理器 ──────────────────────────────────────────────────────

def handle_memory_cleanup(params: dict) -> dict:
    """记忆清理决策处理器 — 清理低价值记忆"""
    from fuxi.memory.decay import purge_below_floor
    result = purge_below_floor(dry_run=False)
    return {"status": "ok", "purged": result.get("purged", 0)}


def handle_attention_reallocate(params: dict) -> dict:
    """注意力重分配决策处理器"""
    from fuxi.kernel.attention import AttentionStrategy, get_attention_system
    strategy_name = params.get("strategy", "bottom_up")
    strategy = AttentionStrategy(strategy_name)
    old, new = get_attention_system().switch(strategy, params.get("reason", "auto"))
    return {"status": "ok", "from": old.value, "to": new.value}


def handle_engine_priority_adjust(params: dict) -> dict:
    """引擎优先级调整决策处理器"""
    from fuxi.engines.base import get_engine_registry
    engine_name = params.get("engine")
    new_priority = params.get("priority")
    registry = get_engine_registry()
    engine = registry.get(engine_name)
    if engine:
        old = engine.priority
        engine.priority = new_priority
        return {
            "status": "ok",
            "engine": engine_name,
            "old_priority": old,
            "new_priority": new_priority,
        }
    return {"status": "error", "reason": f"Engine {engine_name} not found"}


def handle_proactive_notify(params: dict) -> dict:
    """主动通知决策处理器 — 向用户推送重要提醒"""
    from fuxi.memory.ingestion import remember
    message = params.get("message", "")
    if not message:
        return {"status": "error", "reason": "No message"}
    item_id = remember(
        raw_text=f"[自主决策] {message}",
        drawer_id="longterm",
        importance=params.get("importance", 0.7),
        source="self",
        confidence=0.8,
        created_by="decision_engine",
        tags=["自主决策", "proactive"],
    )
    return {"status": "ok", "item_id": item_id}


def handle_agent_delegate(params: dict) -> dict:
    """Agent委派决策处理器 — 将任务委派给合适的Agent"""
    from fuxi.agent.integration import OpenClawAdapter
    adapter = OpenClawAdapter()
    agent_id = params.get("agent_id", "qinglong")
    message = params.get("message", "")
    result = adapter.call_agent(agent_id, message)
    return {
        "status": "ok" if result and "error" not in result else "error",
        "result": result,
    }


# ── 注册 ────────────────────────────────────────────────────────────

DecisionExecutor.register_handler("memory_cleanup", handle_memory_cleanup)
DecisionExecutor.register_handler("attention_reallocate", handle_attention_reallocate)
DecisionExecutor.register_handler("engine_priority_adjust", handle_engine_priority_adjust)
DecisionExecutor.register_handler("proactive_notify", handle_proactive_notify)
DecisionExecutor.register_handler("agent_delegate", handle_agent_delegate)

# 回滚处理器注册（v1.3 新增）
DecisionExecutor.ROLLBACK_HANDLERS = {
    "memory_cleanup": (snapshot_memory_cleanup, rollback_memory_cleanup),
    "attention_reallocate": (snapshot_attention_reallocate, rollback_attention_reallocate),
    "engine_priority_adjust": (snapshot_engine_priority_adjust, rollback_engine_priority_adjust),
    "proactive_notify": (snapshot_proactive_notify, rollback_proactive_notify),
    "agent_delegate": (snapshot_agent_delegate, rollback_agent_delegate),
}

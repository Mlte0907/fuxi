"""伏羲 v1.0 — 多模型路由（DB驱动，支持运行时更新）"""
import contextlib
import json
import logging
import threading
from typing import List, Optional

from fuxi.config import config

logger = logging.getLogger("fuxi.agent.model_router")

_lock = threading.Lock()
_routes_cache: List[dict] = []


def reload_routes():
    """从 DB 重新加载路由规则到内存缓存"""
    global _routes_cache
    try:
        from fuxi.store.connection import get_pool
        pool = get_pool()
        rows = pool.fetchall(
            "SELECT * FROM model_routing WHERE enabled = 1 ORDER BY priority DESC"
        )
        routes = []
        for r in rows:
            d = dict(r)
            for f in ("task_types", "agent_ids"):
                try:
                    d[f] = json.loads(d[f]) if isinstance(d[f], str) else d[f]
                except (json.JSONDecodeError, TypeError):
                    d[f] = []
            routes.append(d)
        with _lock:
            _routes_cache = routes
        logger.debug(f"Model routes reloaded: {len(routes)} rules")
    except Exception as e:
        logger.warning(f"Failed to reload model routes: {e}")


def _ensure_loaded():
    if not _routes_cache:
        with contextlib.suppress(Exception):
            reload_routes()
    if not _routes_cache:
        # DB 不可用时回退到默认规则
        fallback_model = config.openclaw_llm_model or "deepseek-v3"
        return [{"rule_id": "default", "task_types": ["*"], "agent_ids": ["*"],
                 "model_name": fallback_model, "priority": 0}]
    return _routes_cache


def route_model(task_type: str, agent_id: Optional[str] = None) -> str:
    """根据任务类型和 Agent ID 匹配最优模型

    规则按 priority 降序排列，返回第一个匹配的 model_name。
    匹配逻辑: rule.task_types 包含 task_type OR "*" AND rule.agent_ids 包含 agent_id OR "*"
    """
    routes = _ensure_loaded()
    for rule in routes:
        types_match = "*" in rule.get("task_types", []) or task_type in rule.get("task_types", [])
        agents_match = "*" in rule.get("agent_ids", []) or (agent_id and agent_id in rule.get("agent_ids", []))
        if types_match and agents_match:
            model = rule.get("model_name") or config.openclaw_llm_model or "deepseek-v3"
            logger.debug(f"Model routed: task='{task_type}' agent='{agent_id}' → {model} (rule: {rule['rule_id']})")
            return model
    return config.openclaw_llm_model or "deepseek-v3"


def get_agent_default_model(agent_id: str) -> str:
    """获取 Agent 的默认模型"""
    routes = _ensure_loaded()
    for rule in routes:
        if agent_id in rule.get("agent_ids", []) and "*" in rule.get("task_types", []):
            return rule.get("model_name") or config.openclaw_llm_model or "deepseek-v3"
    return config.openclaw_llm_model or "deepseek-v3"


def list_routing_rules() -> list:
    """列出所有活跃路由规则"""
    routes = _ensure_loaded()
    return [{
        "rule_id": r["rule_id"],
        "rule_name": r.get("rule_name", ""),
        "task_types": r.get("task_types", []),
        "agent_ids": r.get("agent_ids", []),
        "model_name": r.get("model_name") or config.openclaw_llm_model or "deepseek-v3",
        "priority": r.get("priority", 0),
    } for r in routes]

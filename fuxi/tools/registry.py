"""伏羲 v1.0 — 工具注册表（Tool Registry）"""
import json
import logging
from datetime import datetime
from typing import List, Optional

from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.tools.registry")


class ToolRegistry:
    """标准化工具注册表，支持审计和调用追踪"""

    def list_tools(self, backend: Optional[str] = None, active_only: bool = True) -> List[dict]:
        pool = get_pool()
        clauses = []
        params = []
        if active_only:
            clauses.append("is_active = 1")
        if backend:
            clauses.append("backend = ?")
            params.append(backend)
        where = " AND ".join(clauses) if clauses else "1=1"
        rows = pool.fetchall(
            f"SELECT * FROM tool_registry WHERE {where} ORDER BY tool_name",
            params
        )
        return [dict(r) for r in rows]

    def get_tool(self, tool_id: str) -> Optional[dict]:
        pool = get_pool()
        row = pool.fetchone("SELECT * FROM tool_registry WHERE tool_id = ?", (tool_id,))
        return dict(row) if row else None

    def register(self, tool_id: str, tool_name: str, description: str = "",
                 backend: str = "local", need_confirmation: bool = False,
                 config_json: Optional[dict] = None) -> str:
        pool = get_pool()
        now = datetime.now().isoformat()
        with pool.connection() as c:
            c.execute(
                "INSERT OR REPLACE INTO tool_registry "
                "(tool_id, tool_name, description, backend, need_confirmation, config_json, updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (tool_id, tool_name, description, backend,
                 1 if need_confirmation else 0,
                 json.dumps(config_json or {}, ensure_ascii=False),
                 now)
            )
        logger.info(f"Tool registered: {tool_id}")
        return tool_id

    def update_tool(self, tool_id: str, **kwargs) -> bool:
        pool = get_pool()
        allowed = {"tool_name", "description", "backend", "need_confirmation",
                    "is_active", "config_json"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return False
        if "config_json" in updates and isinstance(updates["config_json"], dict):
            updates["config_json"] = json.dumps(updates["config_json"], ensure_ascii=False)
        updates["updated_at"] = datetime.now().isoformat()
        sets = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [tool_id]
        with pool.connection() as c:
            cur = c.execute(
                f"UPDATE tool_registry SET {sets} WHERE tool_id=?",
                values
            )
        return cur.rowcount > 0

    def record_usage(self, tool_id: str, agent_id: str = "system",
                     params: Optional[dict] = None, result: Optional[dict] = None,
                     duration_ms: float = 0.0) -> None:
        pool = get_pool()
        now = datetime.now().isoformat()
        with pool.connection() as c:
            c.execute(
                "UPDATE tool_registry SET last_used=?, use_count=use_count+1 WHERE tool_id=?",
                (now, tool_id)
            )
            c.execute(
                "INSERT INTO event_log (event_type, source, event_data, created_at) "
                "VALUES (?,?,?,?)",
                ("tool_invoke", agent_id,
                 json.dumps({"tool_id": tool_id, "params": params, "result": result,
                             "duration_ms": duration_ms}, ensure_ascii=False),
                 now)
            )
        logger.debug(f"Tool usage: {tool_id} by {agent_id} ({duration_ms:.0f}ms)")

    def get_tool_stats(self) -> dict:
        pool = get_pool()
        total = pool.fetchone("SELECT COUNT(*) AS cnt FROM tool_registry WHERE is_active=1")
        by_backend = pool.fetchall(
            "SELECT backend, COUNT(*) AS cnt FROM tool_registry WHERE is_active=1 GROUP BY backend"
        )
        most_used = pool.fetchall(
            "SELECT tool_id, tool_name, use_count FROM tool_registry "
            "WHERE is_active=1 ORDER BY use_count DESC LIMIT 10"
        )
        return {
            "total_active": total["cnt"] if total else 0,
            "by_backend": {r["backend"]: r["cnt"] for r in by_backend},
            "most_used": [dict(r) for r in most_used],
        }


_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry

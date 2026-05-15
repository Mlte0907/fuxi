"""伏羲 v1.0 — Agent 视角管理"""
import logging
from datetime import datetime
from typing import List, Optional

from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.agent.perspective")


class PerspectiveManager:
    """管理每个 Agent 的记忆视角和可见性"""

    def set_view(self, agent_id: str, item_ids: Optional[List[str]] = None,
                 drawer_id: Optional[str] = None) -> dict:
        pool = get_pool()
        now = datetime.now().isoformat()

        with pool.connection() as c:
            if item_ids:
                for item_id in item_ids:
                    c.execute(
                        "INSERT OR IGNORE INTO agent_views (agent_id, item_id, drawer_id) VALUES (?,?,?)",
                        (agent_id, item_id, drawer_id or "default")
                    )
            else:
                # 设置该Agent对整个抽屉的可见性
                c.execute(
                    "INSERT OR REPLACE INTO agent_views (agent_id, drawer_id) VALUES (?,?)",
                    (agent_id, drawer_id or "default")
                )

        return {"agent_id": agent_id, "view_count": len(item_ids) if item_ids else 0}

    def get_view(self, agent_id: str, limit: int = 50) -> List[dict]:
        pool = get_pool()
        rows = pool.fetchall(
            "SELECT i.* FROM items i JOIN agent_views av ON av.item_id = i.id "
            "WHERE av.agent_id = ? AND i.archived = 0 "
            "ORDER BY i.importance DESC, i.updated_at DESC LIMIT ?",
            (agent_id, limit)
        )
        return [dict(r) for r in rows]

    def get_drawer_view(self, agent_id: str) -> List[str]:
        """获取 Agent 可访问的抽屉列表"""
        pool = get_pool()
        rows = pool.fetchall(
            "SELECT DISTINCT drawer_id FROM agent_views WHERE agent_id = ?",
            (agent_id,)
        )
        return [r["drawer_id"] for r in rows]

    def share_memory(self, from_agent: str, to_agent: str,
                     item_id: str, permission: str = "read") -> dict:
        """Agent 间共享记忆"""
        pool = get_pool()
        import uuid
        now = datetime.now().isoformat()

        with pool.connection() as c:
            c.execute(
                "INSERT OR REPLACE INTO shared_memories "
                "(id, item_id, from_agent, to_agent, permission, shared_at) "
                "VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), item_id, from_agent, to_agent, permission, now)
            )
            # 同时更新目标 Agent 的视角
            c.execute(
                "INSERT OR IGNORE INTO agent_views (agent_id, item_id) VALUES (?,?)",
                (to_agent, item_id)
            )

        logger.debug(f"Shared: {from_agent} → {to_agent} [{item_id[:8]}] ({permission})")
        return {"from": from_agent, "to": to_agent, "item": item_id, "permission": permission}

    def get_shared_memories(self, agent_id: str, limit: int = 10) -> List[dict]:
        """读取共享给目标 Agent 的记忆"""
        pool = get_pool()
        rows = pool.fetchall(
            "SELECT sm.id AS share_id, sm.item_id, sm.from_agent, sm.permission, "
            "sm.shared_at, i.raw_text, i.importance, i.tags "
            "FROM shared_memories sm "
            "LEFT JOIN items i ON i.id = sm.item_id AND i.archived = 0 "
            "WHERE sm.to_agent = ? "
            "ORDER BY sm.shared_at DESC LIMIT ?",
            (agent_id, limit)
        )
        return [dict(r) for r in rows if r["raw_text"]]

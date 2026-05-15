"""伏羲 v1.0 — Agent 路由"""
import logging
from pathlib import Path
from typing import List, Optional

import yaml

from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.agent.routing")

_agents_yml = Path(__file__).parent / "agents.yml"
with open(_agents_yml) as f:
    _config = yaml.safe_load(f)
    AGENT_ROUTES = {
        agent_id: {
            "role": info["role"],
            "capabilities": info.get("capabilities", []),
            "drawer": info.get("drawer", "default"),
        }
        for agent_id, info in _config["agents"].items()
    }


class AgentRouter:
    """Agent 路由管理器"""

    def resolve(self, agent_id: str, _intent: Optional[str] = None) -> dict:
        route = AGENT_ROUTES.get(agent_id, {})
        if not route:
            return {"agent_id": agent_id, "status": "unknown", "drawer": "default"}

        return {
            "agent_id": agent_id,
            "role": route.get("role", "unknown"),
            "capabilities": route.get("capabilities", []),
            "drawer": route.get("drawer", "default"),
            "status": "active",
        }

    def route_message(self, from_agent: str, to_agent: str, content: str) -> dict:
        """路由消息到目标 Agent 的抽屉"""
        pool = get_pool()
        from fuxi.memory.ingestion import remember

        target_route = self.resolve(to_agent)
        drawer = target_route.get("drawer", "default")

        item_id = remember(
            raw_text=content,
            drawer_id=drawer,
            source=f"agent:{from_agent}",
            created_by=to_agent,
            importance=0.7,
        )

        logger.debug(f"Routed: {from_agent} → {to_agent} ({drawer}) [{item_id[:8]}]")
        return {
            "message_id": item_id,
            "from": from_agent,
            "to": to_agent,
            "drawer": drawer,
        }

    def list_agents(self) -> List[dict]:
        return [
            {"id": aid, **info}
            for aid, info in AGENT_ROUTES.items()
        ]

    def get_agent_drawer(self, agent_id: str) -> str:
        route = AGENT_ROUTES.get(agent_id, {})
        return str(route.get("drawer", "default"))

"""伏羲 v1.0 — 多 Agent 协作"""
import logging
from typing import List

from fuxi.agent.integration import OpenClawAdapter
from fuxi.agent.routing import AgentRouter
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.agent.collaboration")


class CollaborationBus:
    """多 Agent 协作总线"""

    def __init__(self):
        self._router = AgentRouter()

    def broadcast(self, from_agent: str, message: str, importance: float = 0.5) -> dict:
        """向所有 Agent 广播消息"""
        agents = self._router.list_agents()
        results = {}
        for agent in agents:
            aid = agent["id"]
            if aid != from_agent:
                result = self._router.route_message(from_agent, aid, message)
                results[aid] = result["message_id"]

        logger.info(f"Broadcast: {from_agent} → {len(results)} agents")
        return {"from": from_agent, "delivered": len(results), "recipients": results}

    def pipeline(self, chain: List[str], message: str, importance: float = 0.7) -> dict:
        """流水线执行：消息依次经过每个 Agent"""
        results = []
        current_msg = message

        for i, agent_id in enumerate(chain):
            drawer = self._router.get_agent_drawer(agent_id)
            from fuxi.memory.ingestion import remember

            item_id = remember(
                raw_text=current_msg,
                drawer_id=drawer,
                source=f"pipeline:{chain[0]}" if i > 0 else "pipeline:start",
                created_by=agent_id,
                importance=importance,
            )

            results.append({
                "step": i + 1,
                "agent": agent_id,
                "item_id": item_id,
                "status": "processed",
            })

            # 通知 Agent 处理消息
            try:
                OpenClawAdapter().call_agent(
                    agent_id=agent_id,
                    message=current_msg,
                )
            except Exception as e:
                logger.warning(f"Pipeline notify [{agent_id}] failed: {e}")

            # 通过 ACP 协议 relay 通知外部客户端
            try:
                from fuxi.acp.client import get_acp_client
                acp = get_acp_client()
                if acp._registered:
                    import asyncio
                    asyncio.run(acp.relay(agent_id, {
                        "type": "pipeline_step",
                        "step": i + 1,
                        "chain": chain,
                        "message": current_msg[:500],
                    }))
            except Exception as e:
                logger.debug(f"ACP relay [{agent_id}] skipped: {e}")

            current_msg = f"[{agent_id}] processed: {current_msg[:200]}"

        logger.info(f"Pipeline: {' → '.join(chain)} ({len(results)} steps)")
        return {"chain": chain, "steps": results, "final_message_id": results[-1]["item_id"] if results else None}

    def negotiate(self, agents: List[str], topic: str) -> dict:
        """多 Agent 协商：各自表达观点，汇总共识"""
        pool = get_pool()
        results = {}

        for agent_id in agents:
            drawer = self._router.get_agent_drawer(agent_id)
            # 查找该 Agent 对话题的相关记忆
            related = pool.fetchall(
                "SELECT i.id, SUBSTR(i.raw_text,1,100) AS preview, i.importance FROM items i "
                "JOIN agent_views av ON av.item_id = i.id "
                "WHERE av.agent_id = ? AND i.archived = 0 AND i.raw_text LIKE ? "
                "ORDER BY i.importance DESC LIMIT 5",
                (agent_id, f"%{topic}%")
            )
            results[agent_id] = {
                "related_items": len(related),
                "top_preview": related[0]["preview"] if related else None,
            }

        return {"topic": topic, "participants": agents, "perspectives": results}

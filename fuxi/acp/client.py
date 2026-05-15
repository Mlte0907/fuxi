"""ACP 内部客户端 — 本地直连 ACP 服务

将 Fuxi 内部组件注册为 ACP 客户端，使协议消息（relay/broadcast/memory）
真正流通起来。"""
import logging
from typing import Optional

logger = logging.getLogger("fuxi.acp.client")


class InternalACPClient:
    """内部 ACP 客户端 — 注册到 ACP 服务器连接池"""

    def __init__(self, client_id: str = "fuxi-internal"):
        self.client_id = client_id
        self.session_id = "internal"
        self._registered = False

    def register(self):
        """注册到 ACP 服务器连接池"""
        from fuxi.acp.server import connections, ACPConnection

        conn = ACPConnection(None, self.client_id)
        conn.session_id = "internal"
        conn.authenticated = True
        conn.project_scope = "default"
        connections[self.client_id] = conn
        self._registered = True
        logger.info("ACP internal client registered (%d connections)", len(connections))

    def unregister(self):
        if self._registered:
            from fuxi.acp.server import connections
            connections.pop(self.client_id, None)
            self._registered = False
            logger.info("ACP internal client unregistered")

    async def relay(self, target: str, payload: dict) -> dict:
        """向目标客户端发送 relay 消息"""
        from fuxi.acp.server import connections
        target_conn = None
        for cid, conn in connections.items():
            if conn.client_id == target or conn.session_id == target:
                target_conn = conn
                break
        if target_conn is None:
            logger.warning("ACP relay target not found: %s", target)
            return {"status": "error", "error": f"target not found: {target}"}

        await target_conn.send("relay", {
            "relay_id": "direct",
            "from": self.client_id,
            "from_session": "internal",
            "payload": payload,
        })
        return {"status": "ok", "target": target}

    async def broadcast(self, payload: dict) -> dict:
        """广播消息给所有其他客户端"""
        from fuxi.acp.server import connections
        count = 0
        for cid, conn in connections.items():
            if cid == self.client_id:
                continue
            try:
                await conn.send("relay", {
                    "relay_id": "broadcast",
                    "from": self.client_id,
                    "from_session": "internal",
                    "payload": payload,
                })
                count += 1
            except Exception:
                pass
        logger.info("ACP broadcast: %d peers notified", count)
        return {"status": "ok", "relayed_to": count}


_internal_client: Optional[InternalACPClient] = None


def get_acp_client() -> InternalACPClient:
    global _internal_client
    if _internal_client is None:
        _internal_client = InternalACPClient()
    return _internal_client

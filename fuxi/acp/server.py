"""ACP 服务端 - WebSocket + ACP 协议处理（含 Relay 模式）"""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from fuxi.models import ApiResponse

logger = logging.getLogger("fuxi.acp.server")
router = APIRouter(tags=["acp"])

# ACP 协议消息类型
ACP_MSG_SESSION_INIT = "session.init"
ACP_MSG_SESSION_CONFIRM = "session.confirm"
ACP_MSG_MEMORY_QUERY = "memory.query"
ACP_MSG_MEMORY_STORE = "memory.store"
ACP_MSG_MEMORY_RECALL = "memory.recall"
ACP_MSG_SKILL_EXEC = "skill.exec"
ACP_MSG_CONTEXT_INJECT = "context.inject"
ACP_MSG_RELAY = "relay"
ACP_MSG_RELAY_RESULT = "relay.result"
ACP_MSG_RELAY_BROADCAST = "relay.broadcast"
ACP_MSG_PING = "ping"
ACP_MSG_PONG = "pong"


class ACPConnection:
    """ACP 客户端连接"""
    def __init__(self, websocket: WebSocket, client_id: str):
        self.ws = websocket
        self.client_id = client_id
        self.session_id = None
        self.authenticated = False
        self.project_scope = None
        self.last_activity = datetime.now()

    async def send(self, msg_type: str, data: dict):
        """发送 ACP 消息"""
        if self.ws is None:
            return  # 内部客户端：无 WebSocket
        if self.ws.client_state == WebSocketState.CONNECTED:
            await self.ws.send_json({
                "type": msg_type,
                "data": data,
                "timestamp": datetime.now().isoformat(),
            })

    async def receive(self) -> Optional[dict]:
        """接收 ACP 消息"""
        try:
            return await self.ws.receive_json()
        except Exception:
            return None


connections: dict[str, ACPConnection] = {}
# 挂起的 relay 请求: relay_id → {"source": conn, "event": asyncio.Event, "result": dict}
_pending_relays: dict[str, dict] = {}


async def _handle_relay(source_conn: ACPConnection, data: dict):
    """Relay 模式：将消息转发给目标客户端，并等待回复"""
    target = data.get("target", "")
    payload = data.get("payload", {})
    timeout = data.get("timeout", 30)
    relay_id = str(uuid.uuid4())[:8]

    # 查找目标客户端
    target_conn = None
    for cid, conn in connections.items():
        if conn.client_id == target or conn.session_id == target:
            target_conn = conn
            break

    if not target_conn:
        await source_conn.send(ACP_MSG_RELAY_RESULT, {
            "relay_id": relay_id,
            "status": "error",
            "error": f"Target not found: {target}",
        })
        return

    # 注册 pending relay
    event = asyncio.Event()
    result_holder = {}
    _pending_relays[relay_id] = {
        "source": source_conn,
        "event": event,
        "result": result_holder,
    }

    # 转发给目标
    await target_conn.send(ACP_MSG_RELAY, {
        "relay_id": relay_id,
        "from": source_conn.client_id,
        "from_session": source_conn.session_id,
        "payload": payload,
    })

    # 等待应答
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        await source_conn.send(ACP_MSG_RELAY_RESULT, {
            "relay_id": relay_id,
            "status": "ok",
            "result": result_holder.get("result", {}),
        })
    except asyncio.TimeoutError:
        await source_conn.send(ACP_MSG_RELAY_RESULT, {
            "relay_id": relay_id,
            "status": "timeout",
            "error": f"No response within {timeout}s",
        })
    finally:
        _pending_relays.pop(relay_id, None)


async def _handle_relay_broadcast(source_conn: ACPConnection, data: dict):
    """Relay 广播：向所有其他客户端发送消息（不需要回复）"""
    payload = data.get("payload", {})
    count = 0
    for cid, conn in connections.items():
        if conn.client_id == source_conn.client_id:
            continue
        try:
            await conn.send(ACP_MSG_RELAY, {
                "relay_id": "broadcast",
                "from": source_conn.client_id,
                "from_session": source_conn.session_id,
                "payload": payload,
            })
            count += 1
        except Exception:
            pass
    await source_conn.send(ACP_MSG_RELAY_RESULT, {
        "relay_id": "broadcast",
        "status": "ok",
        "relayed_to": count,
    })


def _complete_relay(relay_id: str, result: dict):
    """由目标客户端调用，完成一个 pending relay 请求"""
    pending = _pending_relays.get(relay_id)
    if pending:
        pending["result"]["result"] = result
        pending["event"].set()


@router.websocket("/acp")
async def acp_websocket(websocket: WebSocket):
    """ACP WebSocket 端点"""
    client_id = f"client_{id(websocket)}"
    conn = ACPConnection(websocket, client_id)
    connections[client_id] = conn

    await websocket.accept()

    try:
        while True:
            msg = await conn.receive()
            if not msg:
                break

            conn.last_activity = datetime.now()
            await handle_acp_message(conn, msg)

    except WebSocketDisconnect:
        logger.info(f"ACP client disconnected: {client_id}")
    finally:
        connections.pop(client_id, None)


async def handle_acp_message(conn: ACPConnection, msg: dict):
    """处理 ACP 协议消息"""
    msg_type = msg.get("type", "")
    data = msg.get("data", {})

    if msg_type == ACP_MSG_PING:
        await conn.send(ACP_MSG_PONG, {"seq": data.get("seq")})
        return

    if msg_type == ACP_MSG_SESSION_INIT:
        # 初始化会话
        conn.session_id = data.get("session_id")
        conn.project_scope = data.get("project_scope", "default")
        await conn.send(ACP_MSG_SESSION_CONFIRM, {
            "server_version": "1.0.0",
            "session_id": conn.session_id,
            "capabilities": ["memory_query", "memory_store", "skill_exec", "context_inject"],
        })
        logger.info(f"ACP session init: {conn.session_id} (project: {conn.project_scope})")
        return

    if msg_type == ACP_MSG_MEMORY_QUERY:
        # 记忆查询
        query = data.get("query", "")
        limit = data.get("limit", 5)
        drawer = data.get("drawer", f"{conn.project_scope}_view")

        from fuxi.memory.retrieval import recall
        results = recall(query, drawer_id=drawer, limit=limit)

        await conn.send("memory.query.result", {
            "query": query,
            "results": results,
            "count": len(results),
        })
        return

    if msg_type == ACP_MSG_MEMORY_STORE:
        # 记忆存储
        text = data.get("text", "")
        drawer = data.get("drawer", f"{conn.project_scope}_view")
        importance = data.get("importance", 0.7)

        from fuxi.memory.ingestion import remember
        item_id = remember(text, drawer_id=drawer, importance=importance)

        await conn.send("memory.store.result", {
            "item_id": item_id,
            "drawer": drawer,
        })
        return

    if msg_type == ACP_MSG_CONTEXT_INJECT:
        # 上下文注入
        context_type = data.get("context_type", "recent")
        max_chars = data.get("max_chars", 5000)

        from fuxi.memory.retrieval import recall
        memories = recall("", drawer_id=f"{conn.project_scope}_view", limit=10)

        context_text = "\n".join([
            f"- {m.get('raw_text', m.get('text', ''))[:200]}"
            for m in memories[:5]
        ])

        await conn.send("context.inject.result", {
            "context_type": context_type,
            "content": context_text,
            "char_count": len(context_text),
        })
        return

    if msg_type == ACP_MSG_SKILL_EXEC:
        skill_name = data.get("skill_name", "")
        params = data.get("params", {})

        from fuxi.store.connection import get_pool
        pool = get_pool()
        row = pool.fetchone(
            "SELECT * FROM experience_bank WHERE skill_name=? AND review_status='approved' ORDER BY quality_score DESC LIMIT 1",
            (skill_name,)
        )

        if row:
            skill = dict(row)
            await conn.send("skill.exec.result", {
                "status": "ok",
                "skill_name": skill_name,
                "skill_file_path": skill.get("skill_file_path", ""),
                "trigger_keywords": skill.get("trigger_keywords", "[]"),
                "quality_score": skill.get("quality_score", 0),
                "note": "Skill metadata retrieved; full execution runtime TBD",
            })
        else:
            await conn.send("skill.exec.result", {
                "status": "not_found",
                "skill_name": skill_name,
                "note": f"No approved skill found: {skill_name}",
            })
        return

    if msg_type == ACP_MSG_RELAY:
        await _handle_relay(conn, data)
        return

    if msg_type == ACP_MSG_RELAY_BROADCAST:
        await _handle_relay_broadcast(conn, data)
        return

    # 目标客户端回复 relay 请求
    if msg_type == ACP_MSG_RELAY_RESULT:
        relay_id = data.get("relay_id", "")
        if relay_id and relay_id in _pending_relays:
            _complete_relay(relay_id, data)
        return

    # 未知消息类型
    await conn.send("error", {"message": f"Unknown message type: {msg_type}"})


@router.get("/acp/status")
async def acp_status():
    """ACP 服务状态"""
    return ApiResponse.ok({
        "enabled": True,
        "protocol_version": "1.0.0",
        "active_connections": len(connections),
        "endpoints": {
            "websocket": "/acp",
            "status": "/acp/status",
        }
    })


@router.get("/acp/clients")
async def list_acp_clients():
    """列出活跃的 ACP 客户端"""
    client_list = []
    for cid, conn in connections.items():
        client_list.append({
            "client_id": cid,
            "session_id": conn.session_id,
            "project_scope": conn.project_scope,
            "authenticated": conn.authenticated,
            "last_activity": conn.last_activity.isoformat(),
        })
    return ApiResponse.ok({"clients": client_list, "count": len(client_list)})

"""伏羲 v1.0 — WebSocket 事件推送（带 API Key 认证 + 频道订阅）"""
import asyncio
import json
import logging
import time
from typing import Dict, Set

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from fuxi.config import config

logger = logging.getLogger("fuxi.api.ws")
router = APIRouter(tags=["ws"])

_active_connections: Set[WebSocket] = set()
_subscriptions: Dict[WebSocket, Set[str]] = {}


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, api_key: str = Query("")):
    # API Key 认证
    if not api_key or api_key != config.api_key:
        await ws.close(code=4001, reason="Invalid or missing API key")
        logger.warning(f"WS auth failed from {ws.client}")
        return

    await ws.accept()
    _active_connections.add(ws)
    _subscriptions[ws] = {"*"}  # 默认订阅所有频道
    logger.info(f"WS client connected (total: {len(_active_connections)})")

    try:
        # 发送初始状态
        await ws.send_json({
            "type": "connected",
            "timestamp": time.time(),
            "connections": len(_active_connections)
        })

        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            msg_type = msg.get("type", "unknown")

            if msg_type == "ping":
                await ws.send_json({"type": "pong", "ts": time.time()})
            elif msg_type == "subscribe":
                channels = set(msg.get("channels", ["*"]))
                _subscriptions[ws] = channels
                await ws.send_json({
                    "type": "subscribed",
                    "channels": list(channels)
                })
            else:
                await ws.send_json({
                    "type": "echo",
                    "original": msg
                })

    except WebSocketDisconnect:
        _active_connections.discard(ws)
        _subscriptions.pop(ws, None)
        logger.info(f"WS client disconnected (total: {len(_active_connections)})")
    except Exception as e:
        _active_connections.discard(ws)
        _subscriptions.pop(ws, None)
        logger.error(f"WS error: {e}")


async def broadcast(event_type: str, data: dict, channel: str = "*"):
    """向订阅了指定频道的客户端广播事件"""
    dead = set()
    message = json.dumps({"type": event_type, "data": data, "ts": time.time(), "channel": channel})

    for ws in _active_connections:
        subs = _subscriptions.get(ws, {"*"})
        if "*" not in subs and channel not in subs:
            continue
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)

    for ws in dead:
        _active_connections.discard(ws)
        _subscriptions.pop(ws, None)


def _on_eventbus_event(event):
    """Sync handler: schedule WebSocket broadcast when EventBus publishes."""
    try:
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(broadcast(event.type, event.data))
        )
    except RuntimeError:
        pass


def setup_event_bridge():
    """Subscribe to EventBus so all published events are broadcast to WebSocket clients."""
    from fuxi.kernel.event_bus import get_event_bus
    get_event_bus().subscribe("*", _on_eventbus_event)
    logger.info("EventBus-WebSocket bridge active")

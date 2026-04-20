#!/usr/bin/env python3
"""
伏羲 (Fuxi) — HTTP API 服务器
端点:
  GET  /health              — 健康检查
  POST /remember            — 存入记忆（自动事实提取 + 向量化）
  GET  /search              — 混合检索
  GET  /worlds             — 所有世界
  GET  /explore/:world_id  — 浏览世界结构
  GET  /items/:id          — 获取单条记忆
  POST /items/:id/touch    — 访问记忆（触发衰减恢复）
  GET  /stats              — 统计信息
"""

import json, os, sys
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# 导入伏羲核心
sys.path.insert(0, str(Path(__file__).parent))
from fuxi_core import (
    init_db, create_world, get_worlds, get_world, browse_world,
    create_room, get_rooms, create_drawer, get_drawers,
    create_item, get_item, get_items, touch_item, decay_all,
    extract_facts, embed_text
)
from fuxi_search import search as fuxi_search, get_chroma_client

BASE_DIR = Path(os.environ.get("FUXI_BASE_DIR", os.path.expanduser("~/.openclaw/fuxi")))
PORT = int(os.environ.get("FUXI_PORT", "18919"))

def upsert_to_chroma(item_id: str, text: str) -> str:
    """将文本向量化存入 Chroma"""
    try:
        client = get_chroma_client()
        if client is None:
            return ""
        coll = client.get_or_create_collection("fuxi_items")
        vec = embed_text(text)
        coll.upsert(
            ids=[item_id],
            embeddings=[vec],
            documents=[text],
            metadatas=[{"item_id": item_id}]
        )
        return item_id
    except Exception as e:
        print(f"[伏羲] Chroma 写入失败: {e}")
        return ""


class FuxiHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print(f"[伏羲 API] {args[0]}")

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def get_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            return json.loads(body) if body else {}
        except:
            return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/health":
            return self.send_json({"status": "ok", "service": "伏羲", "version": "1.0.0"})

        if path == "/stats":
            from fuxi_core import conn
            c = conn()
            item_count = c.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            world_count = c.execute("SELECT COUNT(*) FROM worlds").fetchone()[0]
            room_count = c.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
            drawer_count = c.execute("SELECT COUNT(*) FROM drawers").fetchone()[0]
            c.close()
            return self.send_json({
                "items": item_count, "worlds": world_count,
                "rooms": room_count, "drawers": drawer_count
            })

        if path == "/worlds":
            worlds = get_worlds()
            return self.send_json({"worlds": [
                {"id": w.id, "name": w.name, "description": w.description,
                 "icon": w.icon, "updated_at": w.updated_at}
                for w in worlds
            ]})

        if path.startswith("/explore/"):
            wid = path.split("/")[2]
            result = browse_world(wid)
            return self.send_json(result if result else {"error": "not found"},
                                  404 if not result else 200)

        if path.startswith("/items/"):
            iid = path.split("/")[2].split("?")[0]
            item = get_item(iid)
            if item:
                touch_item(iid)
                return self.send_json({
                    "id": item.id, "drawer_id": item.drawer_id,
                    "raw_text": item.raw_text, "facts": item.facts,
                    "importance": item.importance, "decay_score": item.decay_score,
                    "tags": item.tags, "created_at": item.created_at,
                    "last_accessed": item.last_accessed
                })
            return self.send_json({"error": "not found"}, 404)

        if path == "/search":
            q = qs.get("q", [""])[0]
            wid = qs.get("world_id", [None])[0] or None
            rid = qs.get("room_id", [None])[0] or None
            did = qs.get("drawer_id", [None])[0] or None
            tags = qs.get("tags", [None])[0]
            tags = tags.split(",") if tags else None
            top = int(qs.get("top_k", [10])[0])
            hybrid = qs.get("hybrid", ["true"])[0].lower() != "false"
            results = fuxi_search(q or "", world_id=wid, room_id=rid,
                                   drawer_id=did, tags=tags, top_k=top, hybrid=hybrid)
            return self.send_json({"results": results, "query": q, "count": len(results)})

        if path.startswith("/drawers/"):
            did = path.split("/")[2].split("?")[0]
            items = get_items(drawer_id=did, limit=50)
            return self.send_json({"items": [
                {"id": i.id, "raw_text": i.raw_text[:100],
                 "importance": i.importance, "decay_score": i.decay_score,
                 "created_at": i.created_at}
                for i in items
            ]})

        self.send_json({"error": "unknown endpoint"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self.get_body()

        if path == "/remember":
            text = body.get("text", "").strip()
            drawer_id = body.get("drawer_id", "").strip()
            world_id = body.get("world_id", "").strip() or None
            room_id = body.get("room_id", "").strip() or None
            drawer_name = body.get("drawer", "").strip() or "默认"
            tags = body.get("tags", [])
            importance = float(body.get("importance", 0.5))
            auto_extract = body.get("auto_extract", True)

            if not text:
                return self.send_json({"error": "text is required"}, 400)
            if not drawer_id and not (world_id and room_id):
                return self.send_json({"error": "drawer_id or (world_id+room_id) is required"}, 400)

            if not drawer_id and room_id:
                drawers = get_drawers(room_id)
                matching = [d for d in drawers if d.name == drawer_name]
                if matching:
                    drawer_id = matching[0].id
                else:
                    d = create_drawer(room_id, drawer_name)
                    drawer_id = d.id

            facts = extract_facts(text) if auto_extract else []
            chroma_id = upsert_to_chroma("", text)

            item = create_item(
                drawer_id=drawer_id, raw_text=text, facts=facts,
                importance=importance, tags=tags, chroma_id=chroma_id
            )

            if not chroma_id:
                try:
                    client = get_chroma_client()
                    if client:
                        coll = client.get_or_create_collection("fuxi_items")
                        vec = embed_text(text)
                        coll.upsert(
                            ids=[item.id], embeddings=[vec],
                            documents=[text], metadatas=[{"item_id": item.id}]
                        )
                except Exception as e:
                    print(f"[伏羲] Chroma 更新 ID 失败: {e}")

            return self.send_json({
                "id": item.id, "facts_extracted": len(facts),
                "facts": facts, "status": "stored"
            })

        if path == "/worlds":
            name = body.get("name", "").strip()
            if not name:
                return self.send_json({"error": "name is required"}, 400)
            w = create_world(name, body.get("description", ""), body.get("icon", "🌐"))
            return self.send_json({"id": w.id, "name": w.name})

        if path == "/rooms":
            world_id = body.get("world_id", "").strip()
            name = body.get("name", "").strip()
            if not world_id or not name:
                return self.send_json({"error": "world_id and name required"}, 400)
            r = create_room(world_id, name, body.get("description", ""))
            return self.send_json({"id": r.id, "name": r.name})

        if path.startswith("/items/") and path.endswith("/touch"):
            iid = path.split("/")[2]
            touch_item(iid)
            item = get_item(iid)
            return self.send_json({"id": iid, "decay_score": item.decay_score if item else 0})

        if path == "/decay":
            decay_all()
            return self.send_json({"status": "decay applied"})

        self.send_json({"error": "unknown endpoint"}, 404)


def run_server():
    init_db()
    server = HTTPServer(("127.0.0.1", PORT), FuxiHandler)
    print(f"[伏羲] API 服务器启动 @ http://127.0.0.1:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()

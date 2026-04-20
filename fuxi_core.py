#!/usr/bin/env python3
"""
伏羲 (Fuxi) — 瑾岚阁超级大脑·统一记忆内核
Phase 1: 统一数据模型 + SQLite + Chroma向量

数据模型（四层结构）:
  world → room → drawer → item
  每个 item 包含:
    - raw_text: 原始文本
    - facts: LLM 提炼的事实列表
    - importance: 重要性 (0-1)
    - decay_score: 遗忘曲线得分
    - tags: 标签列表
"""

import json, uuid, sqlite3, os, math, getpass
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path

# ── 路径配置 ─────────────────────────────────────────────
# 优先读取环境变量，支持自定义安装路径
def _get_base_dir():
    return Path(os.environ.get("FUXI_BASE_DIR", os.path.expanduser("~/.openclaw/fuxi")))

BASE_DIR = _get_base_dir()
DB_PATH  = BASE_DIR / "fuxi.db"
CHROMA_DIR = BASE_DIR / "chroma"

# ── ScNet API 配置（可替换为其他兼容接口）────────────────
SCNET_BASE = os.environ.get("SCNET_BASE", "https://api.scnet.cn/api/llm/v1")
SCNET_KEY  = os.environ.get("SCNET_KEY", "")   # 设为空，安装后需配置

# ── 数据类 ────────────────────────────────────────────────
@dataclass
class World:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""
    icon: str = "🌐"
    created_at: str = ""
    updated_at: str = ""

@dataclass
class Room:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    world_id: str = ""
    name: str = ""
    description: str = ""
    created_at: str = ""
    updated_at: str = ""

@dataclass
class Drawer:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    room_id: str = ""
    name: str = ""
    created_at: str = ""
    updated_at: str = ""

@dataclass
class Item:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    drawer_id: str = ""
    raw_text: str = ""
    facts: list = field(default=list)
    importance: float = 0.5
    decay_score: float = 1.0
    decay_factor: float = 0.95
    tags: list = field(default=list)
    created_at: str = ""
    updated_at: str = ""
    last_accessed: str = ""
    chroma_id: str = ""


# ── 数据库初始化 ───────────────────────────────────────────
def init_db():
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS worlds (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        icon TEXT DEFAULT '🌐',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS rooms (
        id TEXT PRIMARY KEY,
        world_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (world_id) REFERENCES worlds(id) ON DELETE CASCADE
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS drawers (
        id TEXT PRIMARY KEY,
        room_id TEXT NOT NULL,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id TEXT PRIMARY KEY,
        drawer_id TEXT NOT NULL,
        raw_text TEXT NOT NULL DEFAULT '',
        facts TEXT NOT NULL DEFAULT '[]',
        importance REAL NOT NULL DEFAULT 0.5,
        decay_score REAL NOT NULL DEFAULT 1.0,
        decay_factor REAL NOT NULL DEFAULT 0.95,
        tags TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        last_accessed TEXT NOT NULL DEFAULT '',
        chroma_id TEXT NOT NULL DEFAULT '',
        FOREIGN KEY (drawer_id) REFERENCES drawers(id) ON DELETE CASCADE
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""")

    cur.execute("DROP TABLE IF EXISTS items_fts")
    cur.execute("""
    CREATE VIRTUAL TABLE items_fts USING fts5(
        id,
        raw_text,
        facts,
        tags
    )""")

    conn.commit()
    conn.close()
    print(f"[伏羲] 数据库初始化完成: {DB_PATH}")


# ── CRUD 操作 ─────────────────────────────────────────────
def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def conn():
    return sqlite3.connect(str(DB_PATH))

def create_world(name: str, description: str = "", icon: str = "🌐") -> World:
    w = World(
        id=str(uuid.uuid4())[:8],
        name=name, description=description, icon=icon,
        created_at=_now(), updated_at=_now()
    )
    with conn() as c:
        c.execute("INSERT INTO worlds VALUES (?,?,?,?,?,?)",
                  (w.id, w.name, w.description, w.icon, w.created_at, w.updated_at))
    return w

def get_worlds() -> list[World]:
    with conn() as c:
        rows = c.execute("SELECT * FROM worlds ORDER BY updated_at DESC").fetchall()
    return [World(*r) for r in rows]

def get_world(wid: str) -> Optional[World]:
    with conn() as c:
        r = c.execute("SELECT * FROM worlds WHERE id=?", (wid,)).fetchone()
    return World(*r) if r else None

def create_room(world_id: str, name: str, description: str = "") -> Room:
    r = Room(
        id=str(uuid.uuid4())[:8], world_id=world_id, name=name,
        description=description, created_at=_now(), updated_at=_now()
    )
    with conn() as c:
        c.execute("INSERT INTO rooms VALUES (?,?,?,?,?,?)",
                  (r.id, r.world_id, r.name, r.description, r.created_at, r.updated_at))
    return r

def get_rooms(world_id: str) -> list[Room]:
    with conn() as c:
        rows = c.execute("SELECT * FROM rooms WHERE world_id=? ORDER BY updated_at DESC", (world_id,)).fetchall()
    return [Room(*r) for r in rows]

def create_drawer(room_id: str, name: str) -> Drawer:
    d = Drawer(
        id=str(uuid.uuid4())[:8], room_id=room_id, name=name,
        created_at=_now(), updated_at=_now()
    )
    with conn() as c:
        c.execute("INSERT INTO drawers VALUES (?,?,?,?,?)",
                  (d.id, d.room_id, d.name, d.created_at, d.updated_at))
    return d

def get_drawers(room_id: str) -> list[Drawer]:
    with conn() as c:
        rows = c.execute("SELECT * FROM drawers WHERE room_id=? ORDER BY updated_at DESC", (room_id,)).fetchall()
    return [Drawer(*r) for r in rows]

def create_item(
    drawer_id: str, raw_text: str, facts: list = None,
    importance: float = 0.5, tags: list = None, chroma_id: str = ""
) -> Item:
    now = _now()
    item = Item(
        id=str(uuid.uuid4())[:8], drawer_id=drawer_id, raw_text=raw_text,
        facts=facts or [], importance=importance, decay_score=1.0,
        tags=tags or [], created_at=now, updated_at=now,
        last_accessed=now, chroma_id=chroma_id
    )
    with conn() as c:
        c.execute("""
            INSERT INTO items
            (id,drawer_id,raw_text,facts,importance,decay_score,decay_factor,tags,created_at,updated_at,last_accessed,chroma_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            item.id, item.drawer_id, item.raw_text,
            json.dumps(item.facts, ensure_ascii=False),
            item.importance, item.decay_score, item.decay_factor,
            json.dumps(item.tags, ensure_ascii=False),
            item.created_at, item.updated_at, item.last_accessed,
            item.chroma_id
        ))
        try:
            c.execute("INSERT OR REPLACE INTO items_fts(id, raw_text, facts, tags) VALUES (?,?,?,?)",
                      (item.id, item.raw_text, json.dumps(item.facts, ensure_ascii=False),
                       json.dumps(item.tags, ensure_ascii=False)))
        except Exception as e:
            print(f"[伏羲] FTS 同步跳过: {e}")
    return item

def get_item(iid: str) -> Optional[Item]:
    with conn() as c:
        r = c.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
    if not r: return None
    item = Item(*r[:12])
    item.facts = json.loads(r[3])
    item.tags  = json.loads(r[8])
    return item

def get_items(drawer_id: str = None, limit: int = 50) -> list[Item]:
    with conn() as c:
        if drawer_id:
            rows = c.execute("SELECT * FROM items WHERE drawer_id=? ORDER BY updated_at DESC LIMIT ?",
                             (drawer_id, limit)).fetchall()
        else:
            rows = c.execute("SELECT * FROM items ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    items = []
    for r in rows:
        item = Item(*r[:12])
        item.facts = json.loads(r[3])
        item.tags  = json.loads(r[8])
        items.append(item)
    return items

def touch_item(iid: str):
    """访问记忆项，触发遗忘曲线恢复"""
    with conn() as c:
        row = c.execute("SELECT decay_score, importance FROM items WHERE id=?", (iid,)).fetchone()
        if not row: return
        old_decay, importance = row
        new_decay = min(1.0, old_decay * (1/0.95) * 1.05)
        c.execute("UPDATE items SET last_accessed=?, decay_score=? WHERE id=?",
                  (_now(), min(1.0, new_decay), iid))

def decay_all():
    """全局遗忘曲线衰减 — 定时任务调用"""
    with conn() as c:
        c.execute("""
            UPDATE items
            SET decay_score = MAX(0.0, decay_score * decay_factor),
                updated_at = ?
            WHERE decay_score > 0.01
        """, (_now(),))

# ── LLM 事实提取 ──────────────────────────────────────────
def extract_facts(text: str) -> list[dict]:
    """调用 LLM 从文本中提炼结构化事实（需配置 SCNET_KEY）"""
    if not SCNET_KEY:
        return []
    import urllib.request, urllib.error

    prompt = f"""从以下文本中提炼关键事实，以JSON数组返回。
每条事实格式: {{"subject":"主体","predicate":"谓语","object":"客体","confidence":0.9}}
confidence 取 0.7-1.0，表示事实可靠程度。
只返回纯JSON数组，不要其他内容。

文本:
{text[:2000]}"""

    payload = json.dumps({
        "model": "Qwen3-30B-A3B-Instruct-2507",
        "messages": [{"role":"user","content": prompt}],
        "max_tokens": 512,
        "temperature": 0.1
    }).encode()

    req = urllib.request.Request(
        f"{SCNET_BASE}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SCNET_KEY}"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            content = result["choices"][0]["message"]["content"]
            start = content.find('[')
            end = content.rfind(']') + 1
            if start != -1 and end != 0:
                facts = json.loads(content[start:end])
                return facts[:10]
    except Exception as e:
        print(f"[伏羲] 事实提取失败: {e}")
    return []

# ── 向量嵌入 ─────────────────────────────────────────────
def embed_text(text: str) -> list[float]:
    """调用嵌入模型获取文本向量（需配置 SCNET_KEY）"""
    if not SCNET_KEY:
        import random
        return [random.random() * 2 - 1 for _ in range(1536)]
    import urllib.request, urllib.error

    payload = json.dumps({
        "model": "Qwen3-Embedding-8B",
        "input": text[:4000]
    }).encode()

    req = urllib.request.Request(
        f"{SCNET_BASE}/embeddings",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SCNET_KEY}"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result["data"][0]["embedding"]
    except Exception as e:
        print(f"[伏羲] 向量嵌入失败: {e}")
        import random
        return [random.random() * 2 - 1 for _ in range(1536)]

# ── 浏览结构 ─────────────────────────────────────────────
def browse_world(wid: str) -> dict:
    world = get_world(wid)
    if not world: return {}
    rooms = get_rooms(wid)
    result = {"world": asdict(world), "rooms": []}
    for room in rooms:
        drawers = get_drawers(room.id)
        result["rooms"].append({
            **asdict(room),
            "drawers": [asdict(d) for d in drawers]
        })
    return result


if __name__ == "__main__":
    init_db()
    worlds = get_worlds()
    if not worlds:
        w = create_world("瑾岚阁", "瑾岚阁多Agent系统", "🏯")
        r = create_room(w.id, "系统设计", "架构与工作流设计")
        d = create_drawer(r.id, "架构决策")
        print(f"[伏羲] 创建默认世界: {w.name} / {r.name} / {d.name}")
    print("[伏羲] 内核就绪")

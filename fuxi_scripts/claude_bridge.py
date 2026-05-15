#!/usr/bin/env python3
"""Claude ↔ 伏羲 记忆桥接

用法:
  python3 claude_bridge.py push     # 将 Claude 记忆推送到伏羲
  python3 claude_bridge.py pull N   # 从伏羲拉取 N 条相关记忆到 Claude 上下文
  python3 claude_bridge.py sync     # 双向同步: 先 push 再 pull
"""
import hashlib
import json
import logging
import os
import sys
from pathlib import Path

import requests

logger = logging.getLogger("claude-bridge")

FUXI_BASE = os.environ.get("FUXI_BASE_URL", "http://127.0.0.1:19528")
API_KEY = os.environ.get("FUXI_API_KEY")
CLAUDE_MEMORY_DIR = Path.home() / ".claude" / "projects" / "-home-xiaoxin" / "memory"


def api(method, path, data=None):
    if not API_KEY:
        logger.error("FUXI_API_KEY environment variable is not set")
        return None
    url = f"{FUXI_BASE}{path}"
    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
    resp = requests.request(method, url, json=data, headers=headers, timeout=30)
    if resp.status_code != 200:
        print(f"  API 错误: {resp.status_code} {resp.text[:200]}")
        return None
    return resp.json().get("data")


def push():
    """推送 Claude 记忆文件到伏羲"""
    if not CLAUDE_MEMORY_DIR.exists():
        print("Claude 记忆目录不存在")
        return

    files = sorted(CLAUDE_MEMORY_DIR.glob("*.md"), key=os.path.getmtime)
    if not files:
        print("无 Claude 记忆文件")
        return

    # 已有的记忆指纹，防止重复推送
    fingerprint_file = CLAUDE_MEMORY_DIR / ".fuxi_push_fingerprints"
    pushed = set()
    if fingerprint_file.exists():
        pushed = set(fingerprint_file.read_text().strip().split("\n"))

    new_count = 0
    for f in files:
        if f.name in ("MEMORY.md", ".fuxi_push_fingerprints"):
            continue
        content = f.read_text()
        fp = hashlib.md5(content.encode()).hexdigest()
        if fp in pushed:
            continue

        # 读取 frontmatter
        name = f.stem
        desc = ""
        body = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().split("\n"):
                    if ":" in line:
                        k = line.split(":", 1)[0].strip()
                        v = line.split(":", 1)[1].strip()
                        if k == "description":
                            desc = v
                body = parts[2].strip()

        memory_text = f"[Claude Memory: {name}] {desc}\n{body[:500]}"
        result = api("POST", "/api/v2/memories", {
            "text": memory_text,
            "drawer_id": "longterm",
            "importance": 0.6,
            "source": "claude",
            "confidence": 0.8,
            "created_by": "claude",
            "tags": ["claude-memory", name],
            "facts": json.dumps({"source_file": str(f), "fingerprint": fp}, ensure_ascii=False),
        })
        if result:
            pushed.add(fp)
            new_count += 1

    # 保存指纹
    fingerprint_file.write_text("\n".join(pushed))
    print(f"推送完成: {new_count} 条新记忆 → 伏羲 ({len(pushed)} 总计)")


def pull(n=5):
    """从伏羲拉取相关记忆作为 Claude 上下文"""
    try:
        # 获取最新 N 条 longterm 记忆
        data = api("GET", f"/api/v2/memories?drawer_id=longterm&limit={n}&sort_by=created_at")
        if not data:
            print("未获取到任何记忆")
            return

        print(f"## 伏羲记忆上下文 (最近 {len(data)} 条)\n")
        for m in data:
            text = (m.get("raw_text", "") or m.get("text", ""))[:300]
            tags = m.get("tags", [])
            created = (m.get("created_at", ""))[:16]
            print(f"- [{created}] {text}")
            if tags:
                print(f"  标签: {', '.join(tags)}")
            print()
    except Exception as e:
        print(f"拉取失败: {e}")


def sync():
    """双向同步"""
    print("=== 推送 Claude 记忆 → 伏羲 ===")
    push()
    print("\n=== 拉取伏羲上下文 ===")
    pull(5)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sync"
    if cmd == "push":
        push()
    elif cmd == "pull":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        pull(n)
    elif cmd == "sync":
        sync()
    else:
        print(__doc__)

#!/usr/bin/env python3
"""伏羲 v1.0 — 历史数据迁移脚本

将瑾岚阁 Agent 工作区的 .md 文件导入伏羲记忆系统。
大文件按 Markdown 标题分块，小文件整体导入。
"""
import re
import sys
from pathlib import Path

# 确保 fuxi 在路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

from fuxi.memory.ingestion import remember
from fuxi.store.connection import get_pool

# Agent → Drawer 映射
AGENT_DRAWER_MAP = {
    "qinglong": "qinglong_view",
    "zhuque": "zhuque_view",
    "xuanwu": "xuanwu_view",
    "baihu": "baihu_view",
    "baihu-kun": "baihu_view",
    "baihu-qian": "baihu_view",
    "baihu-zhen": "baihu_view",
    "yinsi": "yinsi_view",
    "yangsi": "yangsi_view",
    "yansi": "yangsi_view",
    "pipi": "main_view",
    "team": "main_view",
}

# 要跳过的文件（非知识类）
SKIP_FILES = {"AGENTS.md", "IDENTITY.md", "TOOLS.md", "HEARTBEAT.md", "SOUL.md"}

# 大文件分块阈值（字节）
CHUNK_THRESHOLD = 4096

HEADER_RE = re.compile(r'^(#{2,4})\s+(.+)$', re.MULTILINE)


def split_by_headers(text: str) -> list[tuple[str, str]]:
    """按 Markdown 标题分块，返回 [(标题, 内容), ...]"""
    matches = list(HEADER_RE.finditer(text))
    if not matches:
        return [("", text)]
    chunks = []
    for i, m in enumerate(matches):
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            chunks.append((title, content))
    return chunks


def import_file(filepath: Path, agent_id: str) -> dict:
    """导入单个文件，返回统计"""
    try:
        text = filepath.read_text()
    except Exception as e:
        return {"file": str(filepath), "status": "error", "error": str(e)}

    if not text.strip():
        return {"file": str(filepath), "status": "skipped", "reason": "empty"}

    drawer = AGENT_DRAWER_MAP.get(agent_id, "default")
    filename = filepath.stem

    # 大文件按标题分块
    if len(text) > CHUNK_THRESHOLD:
        chunks = split_by_headers(text)
        if not chunks:
            chunks = [("", text)]
    else:
        # 小文件整体导入
        chunks = [(filepath.stem, text)]

    imported = 0
    for title, content in chunks:
        try:
            label = f"[{agent_id}] {filename}" + (f" / {title}" if title else "")
            remember(
                raw_text=f"# {label}\n\n{content[:8000]}",
                drawer_id=drawer,
                importance=0.6,
                tags=[agent_id, "migration", filename],
                source="migration",
                created_by=agent_id,
                facts=title if title else filename,
            )
            imported += 1
        except Exception as e:
            print(f"  WARN: chunk '{title[:40]}' failed: {e}")

    return {"file": str(filepath), "status": "ok", "chunks": imported, "drawer": drawer}


def main():
    workspace_base = Path.home() / ".openclaw" / "agents"
    if not workspace_base.is_dir():
        print(f"Workspace not found: {workspace_base}")
        return

    stats = {"total_files": 0, "imported": 0, "skipped": 0, "errors": 0}

    for agent_dir in sorted(workspace_base.iterdir()):
        if not agent_dir.is_dir():
            continue
        agent_id = agent_dir.name
        workspace = agent_dir / "workspace"
        if not workspace.is_dir():
            continue

        md_files = list(workspace.glob("*.md"))
        stats["total_files"] += len(md_files)

        for md_file in md_files:
            if md_file.name in SKIP_FILES:
                stats["skipped"] += 1
                print(f"  SKIP: {md_file.name} ({agent_id})")
                continue

            result = import_file(md_file, agent_id)
            if result["status"] == "ok":
                stats["imported"] += result.get("chunks", 1)
                print(f"  OK: {md_file.name} → {result['drawer']} ({result.get('chunks', 1)} chunks)")
            elif result["status"] == "error":
                stats["errors"] += 1
                print(f"  ERR: {md_file.name}: {result.get('error', 'unknown')}")
            else:
                stats["skipped"] += 1

    print(f"\n迁移完成: {stats['imported']} 条导入, {stats['skipped']} 跳过, {stats['errors']} 失败")

    # 验证
    pool = get_pool()
    row = pool.fetchone("SELECT COUNT(*) AS cnt FROM items WHERE tags LIKE '%migration%'")
    print(f"验证: 伏羲中新增 {row['cnt']} 条迁移记忆")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""伏羲记忆智能上传工具 — 分拣上下文后按语义分块上传。

分拣规则:
- 按 "### " 或 "## " 标题分块（Markdown 章节）
- 按编号列表分块（1. 2. 3.）
- 每块 200-800 字符，避免过大或过小
- 自动从内容中提取 tag（关键词匹配）

用法:
  python3 upload_context.py --agent owl --task "任务名" --summary "摘要"
  python3 upload_context.py --agent owl --task "任务名" --file report.md
  python3 upload_context.py --agent owl --text "短文本"
"""
import argparse
import os
import re
import sys
from pathlib import Path

import requests

FUXI_BASE = os.environ.get("FUXI_BASE_URL", "http://127.0.0.1:19528")
API_KEY = os.environ.get("FUXI_API_KEY", "")

# 关键词 → tag 映射
KEYWORD_TAGS = {
    "修复": "fix",
    "bug": "fix",
    "BUG": "fix",
    "错误": "fix",
    "问题": "issue",
    "发现": "discovery",
    "新增": "feature",
    "创建": "feature",
    "引擎": "engine",
    "测试": "test",
    "优化": "optimize",
    "性能": "performance",
    "安全": "security",
    "备份": "backup",
    "伏羲": "fuxi",
    "瑾岚阁": "jinlange",
    "bridge": "bridge",
    "API": "api",
    "数据库": "database",
    "SQLite": "database",
    "记忆": "memory",
    "collect": "ingestion",
    "采集": "ingestion",
    "上传": "upload",
}


def chunk_text(text: str, min_size: int = 200, max_size: int = 800) -> list[str]:
    """将长文本按语义分块。"""
    chunks = []

    # 先按 Markdown 标题分
    sections = re.split(r'\n#{1,3} ', text)
    if len(sections) <= 1:
        # 没有标题，按编号列表分
        sections = re.split(r'\n\d+\.\s+', text)
    if len(sections) <= 1:
        # 也没有列表，按空行分段
        sections = re.split(r'\n\n+', text)

    for section in sections:
        section = section.strip()
        if not section:
            continue
        # 如果单段太长，按行切割
        while len(section) > max_size:
            # 找最近的换行符
            cut = section[:max_size].rfind('\n')
            if cut < min_size:
                cut = max_size
            chunks.append(section[:cut].strip())
            section = section[cut:].strip()
        if len(section) >= 50:  # 太短的不要
            chunks.append(section)

    return chunks


def extract_tags(text: str, base_tags: list[str] | None = None) -> list[str]:
    """从文本内容自动提取 tag。"""
    tags = list(base_tags or [])
    seen = set(tags)
    for keyword, tag in KEYWORD_TAGS.items():
        if keyword in text and tag not in seen:
            tags.append(tag)
            seen.add(tag)
        if len(tags) >= 6:  # 最多 6 个 tag
            break
    return tags


def fuxi_remember(text: str, agent_id: str, importance: float = 0.7,
                  tags: list[str] | None = None, source: str = "task_log",
                  title: str = "") -> dict | None:
    """上传一条记忆到伏羲"""
    if not API_KEY:
        print("ERROR: FUXI_API_KEY not set", file=sys.stderr)
        return None
    url = f"{FUXI_BASE}/api/v2/memories"
    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
    drawer = f"{agent_id}_view"
    payload = {
        "text": text[:1500],
        "drawer_id": drawer,
        "importance": importance,
        "source": source,
        "created_by": agent_id,
        "tags": tags or ["auto-upload"],
        "confidence": 0.9,
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 500 and "FOREIGN KEY" in resp.text:
            payload["drawer_id"] = "default"
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        result = resp.json().get("data")
        status_id = result.get("id", "?")[:8] if result else "?"
        print(f"  ✅ uploaded [{status_id}] {title or text[:40]}")
        return result
    except Exception as e:
        print(f"  ❌ failed: {e}", file=sys.stderr)
        return None


def upload_task_context(agent_id: str, task_name: str, text: str,
                        source_label: str = "task") -> int:
    """智能分拣上传任务上下文。返回上传条数。"""
    tags_base = ["task", agent_id]

    # 分拣：提取摘要（开头段落）和分块正文
    lines = text.strip().split('\n')

    # 第一行非空作为摘要/标题
    first_line = ""
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            first_line = stripped[:100]
            break

    # 上传摘要
    summary_tags = extract_tags(text[:500], tags_base + ["summary"])
    fuxi_remember(
        f"[{source_label}] {task_name}\n\n{first_line}\n\n{text[:300]}",
        agent_id,
        importance=0.8,
        tags=summary_tags,
        source=f"{source_label}_summary",
        title=f"摘要: {task_name}",
    )

    # 分块上传正文
    chunks = chunk_text(text)
    uploaded = 1  # 摘要算 1
    for i, chunk in enumerate(chunks[:8]):  # 最多 8 块，避免爆炸
        chunk_tags = extract_tags(chunk, tags_base + ["chunk"])
        result = fuxi_remember(
            chunk,
            agent_id,
            importance=0.5,
            tags=chunk_tags,
            source=f"{source_label}_chunk",
            title=f"块{i+1}/{len(chunks)}",
        )
        if result:
            uploaded += 1

    print(f"📤 {task_name}: {uploaded} 条记忆已上传（摘要 1 + 分块 {uploaded-1}）")
    return uploaded


def main():
    parser = argparse.ArgumentParser(description="智能分拣上传上下文到伏羲记忆")
    parser.add_argument("--agent", required=True, help="Agent ID")
    parser.add_argument("--task", default="未命名任务", help="任务名称")
    parser.add_argument("--summary", help="摘要文本或文件路径")
    parser.add_argument("--text", help="直接上传的文本")
    parser.add_argument("--file", help="上传的文件路径（会自动分拣）")
    args = parser.parse_args()

    if args.text:
        upload_task_context(args.agent, args.task, args.text)
    elif args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"ERROR: file not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        text = p.read_text()
        upload_task_context(args.agent, args.task, text)
    elif args.summary:
        p = Path(args.summary)
        text = p.read_text() if p.exists() else args.summary
        upload_task_context(args.agent, args.task, text)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

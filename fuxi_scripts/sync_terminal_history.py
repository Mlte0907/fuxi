#!/usr/bin/env python3
"""终端会话历史同步器

从终端会话的session文件提取最新摘要，同步到共享位置。
优先选择最大的session文件（通常包含最多上下文）。
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

TERMINAL_SESSION_DIR = Path.home() / ".claude" / "session-data"
SYNC_DIR = Path.home() / ".claude" / "relay_v2"
SYNC_FILE = SYNC_DIR / "terminal_context.txt"
MAX_SIZE = 50000  # 最大50KB


def load_latest_session_summary():
    """找到并加载session文件摘要（优先最新日期+最大文件）"""
    if not TERMINAL_SESSION_DIR.exists():
        return None

    # 找到所有session文件，排除太旧的
    today = datetime.now().strftime("%Y-%m-%d")
    sessions = []
    for f in TERMINAL_SESSION_DIR.glob("*-session.tmp"):
        sessions.append((f.stat().st_size, f.stat().st_mtime, f))

    if not sessions:
        return None

    # 先按日期倒序（新的优先），再按大小倒序
    sessions.sort(key=lambda x: (x[1], x[0]), reverse=True)

    # 取最新的文件（最晚修改时间）
    latest = sessions[0][2]

    try:
        content = latest.read_text(encoding="utf-8")
        if len(content) > MAX_SIZE:
            content = content[:MAX_SIZE] + "\n\n...(内容已截断)"
        return content
    except Exception as e:
        return f"Error loading session: {e}"


def sync():
    """执行同步"""
    summary = load_latest_session_summary()
    if summary:
        SYNC_DIR.mkdir(parents=True, exist_ok=True)
        SYNC_FILE.write_text(summary, encoding="utf-8")
        print(f"Synced terminal context: {len(summary)} chars")
    else:
        print("No terminal session found")


if __name__ == "__main__":
    sync()
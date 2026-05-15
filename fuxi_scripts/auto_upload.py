#!/usr/bin/env python3
"""伏羲记忆自动上传 — 从 terminal_context 提取任务级上下文并分块上传。

在 stop hook 中调用，替代直接调用 upload_context.py:
1. 读取 terminal_context.txt
2. 按用户消息（user/assistant 回合）分割为独立任务段
3. 每段提取 tag、摘要、重要性评分
4. 分别上传到伏羲记忆系统

用法:
  python3 auto_upload.py --context /path/to/terminal_context.txt --agent fuxi
  python3 auto_upload.py --context /path/to/terminal_context.txt --patterns /path/to/patterns.txt
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

FUXI_BASE = os.environ.get("FUXI_BASE_URL", "http://127.0.0.1:19528")
API_KEY = os.environ.get("FUXI_API_KEY", os.environ.get("API_KEY", ""))
MAX_CHUNK_SIZE = 1200

# 关键词 → tag + 重要性
KEYWORD_MAP = {
    "修复": ("fix", 0.8), "bug": ("fix", 0.8), "BUG": ("fix", 0.8),
    "错误": ("fix", 0.8), "问题": ("issue", 0.7),
    "发现": ("discovery", 0.6), "新增": ("feature", 0.7),
    "创建": ("feature", 0.7), "引擎": ("engine", 0.6),
    "测试": ("test", 0.5), "优化": ("optimize", 0.7),
    "性能": ("performance", 0.8), "安全": ("security", 0.8),
    "备份": ("backup", 0.6), "伏羲": ("fuxi", 0.5),
    "瑾岚阁": ("jinlange", 0.6), "bridge": ("bridge", 0.5),
    "API": ("api", 0.5), "数据库": ("database", 0.6),
    "SQLite": ("database", 0.6), "记忆": ("memory", 0.7),
    "采集": ("ingestion", 0.6), "上传": ("upload", 0.5),
    "飞书": ("lark", 0.6), "feishu": ("lark", 0.6),
    "lark": ("lark", 0.6), "卡片": ("card", 0.5),
    "流式": ("streaming", 0.5), "部署": ("deploy", 0.6),
    "监控": ("monitor", 0.6), "hook": ("hook", 0.5),
    "路由": ("routing", 0.5), "代理": ("proxy", 0.6),
    "token": ("token", 0.7), "模型": ("model", 0.5),
    "配置": ("config", 0.5), "重构": ("refactor", 0.7),
    "清理": ("cleanup", 0.5), "废弃": ("deprecate", 0.5),
}


def extract_tags_and_importance(text: str, base_tags: list[str] | None = None) -> tuple[list[str], float]:
    """从文本提取 tag 和估算重要性。"""
    tags = list(base_tags or [])
    seen = set(tags)
    max_importance = 0.5  # baseline
    for keyword, (tag, imp) in KEYWORD_MAP.items():
        if keyword.lower() in text.lower():
            if tag not in seen:
                tags.append(tag)
                seen.add(tag)
            max_importance = max(max_importance, imp)
        if len(tags) >= 8:
            break
    return tags[:8], max_importance


def detect_task_segments(text: str) -> list[dict]:
    """从会话文本中检测独立任务段。

    支持两种格式:
    1. ECC 会话摘要格式（# Session: / ## Session Summary / ### Tasks / ### Files Modified）
    2. 传统角色前缀格式（user:/assistant: 行）
    """
    if not text or len(text) < 100:
        return []

    segments = []

    # ── 格式 1: ECC 会话摘要（<!-- ECC:SUMMARY:START --> ... <!-- ECC:SUMMARY:END -->）──
    ecc_blocks = re.findall(
        r'<!--\s*ECC:SUMMARY:START\s*-->(.*?)<!--\s*ECC:SUMMARY:END\s*-->',
        text, re.DOTALL,
    )
    if ecc_blocks:
        for block in ecc_blocks:
            tasks_match = re.search(r'### Tasks\s*\n(.*?)(?=\n### |\n---|\Z)', block, re.DOTALL)
            files_match = re.search(r'### Files Modified\s*\n(.*?)(?=\n### |\n---|\Z)', block, re.DOTALL)
            tools_trace = re.search(r'### Tools Used\s*\n(.*?)(?=\n### |\n---|\Z)', block, re.DOTALL)

            user_tasks = tasks_match.group(1).strip() if tasks_match else ""
            files_text = files_match.group(1).strip() if files_match else ""
            tools_text = tools_trace.group(1).strip() if tools_trace else ""

            assistant_context = "\n".join(filter(None, [files_text, tools_text]))

            task_lines = [l.strip("- ").strip() for l in user_tasks.split("\n") if l.strip()]
            for t in task_lines:
                if len(t) > 20:
                    segments.append({
                        "user_message": t[:200],
                        "assistant_reply": assistant_context[:500] if assistant_context else "",
                        "segment": f"【用户】{t}\n【伏羲】{assistant_context}" if assistant_context else f"【用户】{t}",
                    })

        if segments:
            return segments

    # ── 格式 2: 传统角色前缀格式 ──
    lines = text.split("\n")
    current_user = []
    current_assistant = []
    in_assistant = False
    user_started = False

    for line in lines:
        ulower = line.lower().strip()

        if ulower.startswith("user:") or ulower.startswith("主人:") or ulower.startswith("> user:"):
            if user_started:
                full = "\n".join(current_user + [""] + current_assistant) if current_assistant else "\n".join(current_user)
                if len(full) > 50:
                    segments.append({
                        "user_message": (current_user[0] if current_user else "")[:200],
                        "assistant_reply": ("\n".join(current_assistant))[:500] if current_assistant else "",
                        "segment": full,
                    })
            current_user = [line]
            current_assistant = []
            in_assistant = False
            user_started = True
        elif ulower.startswith("assistant:") or ulower.startswith("伏羲:") or ulower.startswith("> assistant:"):
            in_assistant = True
            current_assistant.append(line)
        elif in_assistant:
            current_assistant.append(line)
        else:
            current_user.append(line)

    if user_started:
        full = "\n".join(current_user + [""] + current_assistant) if current_assistant else "\n".join(current_user)
        if len(full) > 50:
            segments.append({
                "user_message": (current_user[0] if current_user else "")[:200],
                "assistant_reply": ("\n".join(current_assistant))[:500] if current_assistant else "",
                "segment": full,
            })

    # ── 回退: 按分隔线分割 ──
    if len(segments) <= 1 and len(text) > 500:
        parts = re.split(r"\n\n\n+|\n#{3,}\n|\*\*\[Compaction occurred", text)
        segments = [{
            "user_message": p.strip()[:100],
            "assistant_reply": "",
            "segment": p.strip(),
        } for p in parts if len(p.strip()) > 100]

    return segments


def upload_memory(text: str, agent_id: str, task_name: str = "",
                  importance: float = 0.5, tags: list[str] | None = None,
                  source: str = "auto_upload") -> bool:
    """单条记忆上传到伏羲。"""
    if not API_KEY:
        print("  ⚠️  FUXI_API_KEY not set, skipping upload", file=sys.stderr)
        return False
    if not text or len(text.strip()) < 20:
        return False

    url = f"{FUXI_BASE}/api/v2/memories"
    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
    drawer = f"{agent_id}_view"

    chunks = [text[i:i + MAX_CHUNK_SIZE] for i in range(0, len(text), MAX_CHUNK_SIZE)]
    if len(chunks) > 5:
        chunks = chunks[:5]

    success = 0
    for i, chunk in enumerate(chunks):
        chunk_tags, chunk_imp = extract_tags_and_importance(chunk, tags)
        chunk_title = f"{task_name} ({i + 1}/{len(chunks)})" if len(chunks) > 1 else task_name
        payload = {
            "text": chunk,
            "drawer_id": drawer,
            "importance": max(importance, chunk_imp),
            "source": source,
            "created_by": agent_id,
            "tags": chunk_tags or ["auto-upload"],
            "confidence": 0.85,
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code == 500 and "FOREIGN KEY" in resp.text:
                payload["drawer_id"] = "default"
                resp = requests.post(url, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            result = resp.json().get("data", {})
            rid = str(result.get("id", ""))[:8] if result else "?"
            print(f"  ✅ [{rid}] {chunk_title}")
            success += 1
        except Exception as e:
            print(f"  ❌ chunk {i}: {e}", file=sys.stderr)
        time.sleep(0.05)

    return success > 0


def upload_patterns_report(patterns_file: str, agent_id: str):
    """上传 patterns_detected.txt 到记忆，附 token 摘要。"""
    path = Path(patterns_file)
    if not path.exists():
        return False

    text = path.read_text()
    if not text.strip():
        return False

    tags = ["pattern-extraction", "session-summary", agent_id]
    upload_memory(text, agent_id, task_name="会话模式分析", importance=0.6, tags=tags, source="pattern_report")

    token_match = re.search(r"=== Token 消耗 ===\n(.+?)(?:\n\n|\Z)", text, re.DOTALL)
    if token_match:
        token_text = token_match.group(0).strip()
        upload_memory(token_text, agent_id, task_name="Token 消耗记录", importance=0.4,
                      tags=["token", "cost", agent_id], source="token_tracking")

    return True


def upload_session_summary(context_file: str, agent_id: str) -> int:
    """上传会话摘要（先按任务分割，每段独立上传）。"""
    path = Path(context_file)
    if not path.exists():
        return 0

    text = path.read_text()
    if not text.strip():
        return 0

    segments = detect_task_segments(text)
    uploaded = 0

    if len(segments) <= 1:
        tags, imp = extract_tags_and_importance(text, [agent_id, "session"])
        if upload_memory(text[:MAX_CHUNK_SIZE * 3], agent_id,
                         task_name="会话上下文", importance=imp, tags=tags):
            uploaded = 1
    else:
        for i, seg in enumerate(segments):
            user_msg = seg["user_message"]
            reply = seg["assistant_reply"]
            task_name = user_msg[:80] if user_msg else f"任务 {i + 1}"

            upload_text = f"【用户】{user_msg}\n"
            if reply:
                upload_text += f"【伏羲】{reply}\n"
            upload_text += f"\n--- 完整上下文 ---\n{seg['segment']}"

            tags, imp = extract_tags_and_importance(upload_text, [agent_id, "task"])
            if upload_memory(upload_text, agent_id, task_name=task_name,
                             importance=imp, tags=tags):
                uploaded += 1

    return uploaded


def main():
    import argparse
    parser = argparse.ArgumentParser(description="伏羲记忆自动上传")
    parser.add_argument("--context", help="terminal_context.txt 路径")
    parser.add_argument("--patterns", help="patterns_detected.txt 路径")
    parser.add_argument("--agent", default="fuxi", help="Agent ID")
    args = parser.parse_args()

    if not args.context and not args.patterns:
        print("ERROR: 至少指定 --context 或 --patterns", file=sys.stderr)
        sys.exit(1)

    total = 0

    if args.context:
        n = upload_session_summary(args.context, args.agent)
        print(f"📤 会话摘要: {n} 条记忆已上传")
        total += n

    if args.patterns:
        upload_patterns_report(args.patterns, args.agent)

    print(f"✅ 上传完成，共 {total} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())

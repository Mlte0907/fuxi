#!/usr/bin/env python3
"""Claude Code Relay v2 — 持久化会话桥接

每次调用维护完整的对话历史，新消息追加到历史后，
将历史作为上下文发送给 Claude Code，实现真正的多轮对话。

用于 飞书/QQ → Fuxi API → Claude Code 的双向通道。
"""
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("claude-relay-v2")

CLAUDE_BIN = "claude"
TIMEOUT_SEC = 180
SESSION_DIR = Path.home() / ".claude" / "relay_v2"
SESSION_FILE = SESSION_DIR / "sessions.json"
LOCK_FILE = SESSION_DIR / "lock"
MAX_HISTORY_CHARS = 80000  # 超过此长度截断旧消息


def _ensure_session_dir():
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def _acquire_lock(session_id: str) -> bool:
    _ensure_session_dir()
    lock = SESSION_DIR / f"lock_{session_id}"
    if lock.exists():
        age = time.time() - lock.stat().st_mtime
        if age > TIMEOUT_SEC + 60:
            lock.unlink(missing_ok=True)
        else:
            return False
    lock.touch()
    return True


def _release_lock(session_id: str):
    lock = SESSION_DIR / f"lock_{session_id}"
    lock.unlink(missing_ok=True)


def _load_sessions() -> dict:
    _ensure_session_dir()
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_sessions(sessions: dict):
    _ensure_session_dir()
    SESSION_FILE.write_text(json.dumps(sessions, ensure_ascii=False))


def _load_history(session_id: str) -> list:
    sessions = _load_sessions()
    return sessions.get(session_id, {}).get("history", [])


def _save_history(session_id: str, history: list):
    sessions = _load_sessions()
    if session_id not in sessions:
        sessions[session_id] = {"created_at": time.time()}
    sessions[session_id]["history"] = history
    sessions[session_id]["last_active"] = time.time()
    _save_sessions(sessions)


def _build_context_prompt(history: list, new_message: str) -> str:
    """将历史消息格式化为上下文提示"""
    if not history:
        return new_message

    ctx_parts = []
    for entry in history:
        role = entry.get("role", "user")
        content = entry.get("content", "")
        if role == "user":
            ctx_parts.append(f"用户: {content}")
        else:
            ctx_parts.append(f"助手: {content}")

    ctx_parts.append(f"用户: {new_message}")

    context = "\n\n".join(ctx_parts)

    # 超过长度限制，截断旧消息
    if len(context) > MAX_HISTORY_CHARS:
        # 保留最近的对话
        truncated = context[-MAX_HISTORY_CHARS:]
        # 找到第一个"用户:"的位置作为截断点
        cut_pos = truncated.find("用户:")
        if cut_pos > 0:
            context = "...(早期对话已截断)...\n\n" + truncated[cut_pos:]
        else:
            context = "...(早期对话已截断)...\n\n" + truncated

    return context


def relay(message: str, session_id: str = "default") -> dict:
    """将消息转发给 Claude Code，维持会话历史

    Returns:
        {"status": "ok", "reply": "...", "elapsed_ms": ...,
         "history_len": 5, "session_id": "xxx"}
        {"status": "timeout", ...}
        {"status": "error", "error": "..."}
    """
    if not message.strip():
        return {"status": "error", "error": "empty message"}

    # 清理消息中的危险字符
    message = message.replace("\r", " ").strip()

    if not _acquire_lock(session_id):
        return {"status": "error", "error": "another relay is in progress for this session"}

    try:
        # 加载历史
        history = _load_history(session_id)

        # 构建带上下文的提示
        full_prompt = _build_context_prompt(history, message)

        env = {
            **os.environ,
            "HOME": os.path.expanduser("~"),
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        }

        # 使用 --continue 继续上一会话
        cmd = [CLAUDE_BIN, "-p", full_prompt]

        t0 = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SEC,
                env=env,
                cwd=str(Path.home() / "fuxi"),
            )
            elapsed_ms = round((time.time() - t0) * 1000)

            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            if result.returncode != 0:
                logger.warning(f"Claude exited with {result.returncode}: {stderr[:200]}")
                if stdout:
                    reply = stdout
                else:
                    return {"status": "error", "error": stderr or f"exit code {result.returncode}",
                            "elapsed_ms": elapsed_ms}
            else:
                reply = stdout

            # 更新历史
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": reply})
            _save_history(session_id, history)

            return {
                "status": "ok",
                "reply": reply,
                "elapsed_ms": elapsed_ms,
                "history_len": len(history),
                "session_id": session_id,
            }

        except subprocess.TimeoutExpired:
            logger.warning(f"Claude timed out after {TIMEOUT_SEC}s")
            return {"status": "timeout", "elapsed_ms": round((time.time() - t0) * 1000)}

    except Exception as e:
        logger.error(f"Relay error: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        _release_lock(session_id)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Claude Code Relay v2")
    parser.add_argument("message", nargs="?", help="Message to relay")
    parser.add_argument("--session", default="default", help="Session ID (default: default)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    message = args.message
    if not message:
        message = sys.stdin.read().strip()
    if not message:
        print('{"status": "error", "error": "no message"}')
        sys.exit(1)

    result = relay(message, session_id=args.session)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result["status"] == "ok":
            print(result.get("reply", ""))
        else:
            print(f"[{result['status']}] {result.get('reply', result.get('error', ''))}")

    sys.exit(0 if result["status"] == "ok" else 1)


if __name__ == "__main__":
    main()

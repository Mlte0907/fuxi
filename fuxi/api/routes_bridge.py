"""伏羲 v1.0 — /api/v2/bridge 路由 — Claude Code 中继桥接

将外部通道（QQ bot / 飞书）的消息转发给 Claude Code 并返回回复。
支持持久化会话 + 终端上下文注入。
"""
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

from fuxi.models import ApiResponse

logger = logging.getLogger("fuxi.api.bridge")
router = APIRouter(tags=["bridge"])

CLAUDE_BIN = "/usr/local/bin/claude"
TIMEOUT_SEC = 180
SESSION_DIR = Path.home() / ".claude" / "relay_v2"
SESSION_FILE = SESSION_DIR / "sessions.json"
TERMINAL_CONTEXT_FILE = SESSION_DIR / "terminal_context.txt"
MAX_HISTORY_CHARS = 15000
MAX_TERMINAL_CONTEXT_CHARS = 5000


def _ensure_session_dir():
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def _acquire_lock(session_id: str) -> bool:
    lock = SESSION_DIR / f"lock_{session_id}"
    _ensure_session_dir()
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


def _load_terminal_context() -> str:
    """加载终端会话上下文"""
    if TERMINAL_CONTEXT_FILE.exists():
        try:
            ctx = TERMINAL_CONTEXT_FILE.read_text(encoding="utf-8")
            if len(ctx) > MAX_TERMINAL_CONTEXT_CHARS:
                ctx = ctx[:MAX_TERMINAL_CONTEXT_CHARS] + "\n...(已截断)"
            return ctx
        except Exception:
            return ""
    return ""


def _build_context_prompt(history: list, new_message: str) -> str:
    """构建带上下文的提示"""
    parts = []

    # 1. 注入终端会话上下文（如果有）
    terminal_ctx = _load_terminal_context()
    if terminal_ctx:
        parts.append(f"【终端会话上下文】\n{terminal_ctx}\n【/终端会话上下文】\n")

    # 2. 飞书会话历史
    if history:
        for entry in history:
            role = entry.get("role", "user")
            content = entry.get("content", "")
            if role == "user":
                parts.append(f"用户: {content}")
            else:
                parts.append(f"助手: {content}")

    # 3. 当前消息
    parts.append(f"用户: {new_message}")

    context = "\n\n".join(parts)

    if len(context) > MAX_HISTORY_CHARS:
        truncated = context[-MAX_HISTORY_CHARS:]
        cut_pos = truncated.find("用户:")
        if cut_pos > 0:
            context = "...(早期对话已截断)...\n\n" + truncated[cut_pos:]
        else:
            context = "...(早期对话已截断)...\n\n" + truncated

    return context


@router.post("/bridge/claude")
def bridge_claude(req: dict):
    """将消息桥接到 Claude Code 会话（持久化版本）

    Request body:
        {"message": "用户消息", "session_id": "可选会话ID"}

    Returns:
        {"reply": "Claude Code 回复", "elapsed_ms": ..., "status": ...}
    """
    message = req.get("message", "").strip()
    session_id = req.get("session_id", "feishu")

    if not message:
        raise HTTPException(status_code=400, detail="message required")

    if len(message) > 4000:
        message = message[:4000] + "..."

    if not _acquire_lock(session_id):
        return ApiResponse.ok({
            "reply": "（另一条消息正在处理中，请稍后重试）",
            "status": "busy",
        })

    try:
        history = _load_history(session_id)
        full_prompt = _build_context_prompt(history, message)

        env = {
            **os.environ,
            "HOME": os.path.expanduser("~"),
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        }

        cmd = [CLAUDE_BIN, "--print", "--dangerously-skip-permissions", "--bare", full_prompt]

        t0 = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SEC,
                env=env,
                cwd=str(Path.home()),
            )
            elapsed_ms = round((time.time() - t0) * 1000)

            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            if result.returncode != 0:
                logger.warning(f"Claude exited with {result.returncode}: {stderr[:200]}")
                reply = stdout if stdout else f"（错误: {stderr[:200] if stderr else result.returncode}）"
            else:
                reply = stdout

            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": reply})
            _save_history(session_id, history)

            return ApiResponse.ok({
                "reply": reply,
                "elapsed_ms": elapsed_ms,
                "status": "ok",
                "history_len": len(history),
            })

        except subprocess.TimeoutExpired:
            elapsed_ms = round((time.time() - t0) * 1000)
            return ApiResponse.ok({
                "reply": "（Claude Code 超时，请稍后重试）",
                "elapsed_ms": elapsed_ms,
                "status": "timeout",
            })

    except Exception as e:
        logger.error(f"Bridge error: {e}")
        return ApiResponse.ok({
            "reply": f"（桥接异常: {str(e)[:200]}）",
            "status": "error",
        })
    finally:
        _release_lock(session_id)

"""伏羲 v1.0 — OpenClaw 记忆同步引擎

主动从 OpenClaw trajectory 文件中提取会话记忆，
经过去重后存入伏羲记忆系统。
"""
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.memory.ingestion import remember

logger = logging.getLogger("fuxi.engines.openclaw_memory")

OPENCLAW_SESSIONS_DIR = Path.home() / ".openclaw" / "agents" / "main" / "sessions"
CHECKPOINT_FILE = Path.home() / ".openclaw" / "memory_sync_checkpoint.json"
DEDUP_SIMILARITY_THRESHOLD = 0.92  # 伏羲记忆去重阈值


class OpenClawMemoryEngine(CognitiveEngine):
    name = "openclaw_memory"
    experimental = True
    interval = 600   # 每10分钟同步一次
    priority = 4     # 提高优先级，确保被调度

    def _get_subscriptions(self):
        return {
            "openclaw.session_started": self._on_session_started,
        }

    def _on_session_started(self, event):
        """新会话启动时记录"""
        data = event.data or {}
        session_key = data.get("sessionKey", "")
        message_provider = data.get("messageProvider", "")
        if message_provider:
            try:
                remember(
                    raw_text=f"OpenClaw 新会话启动: {message_provider} ({session_key})",
                    drawer_id="openclaw",
                    importance=0.5,
                    tags=["openclaw", "session-start"],
                    source="openclaw-sync",
                    created_by="openclaw-memory-engine",
                )
            except Exception:
                pass

    def _ensure_drawer(self):
        """Ensure openclaw drawer exists"""
        from fuxi.store.connection import get_pool
        pool = get_pool()
        with pool.connection() as conn:
            cur = conn.execute("SELECT id FROM rooms LIMIT 1")
            row = cur.fetchone()
            room_id = row[0] if row else "main"
            conn.execute(
                "INSERT OR IGNORE INTO drawers (id, name, room_id, description) VALUES (?, ?, ?, ?)",
                ("openclaw", "OpenClaw记忆", room_id, "来自OpenClaw的记忆同步")
            )
            conn.commit()

    def run(self) -> dict:
        """扫描 OpenClaw trajectory 文件，提取记忆并去重存入伏羲"""
        self._ensure_drawer()
        processed = self._load_checkpoint()
        sessions_dir = OPENCLAW_SESSIONS_DIR

        if not sessions_dir.exists():
            return {"status": "skip", "reason": "sessions dir not found", "processed": 0}

        # 获取所有 trajectory 文件
        traj_files = sorted(sessions_dir.glob("*.trajectory.jsonl"), key=lambda p: p.stat().st_mtime)

        new_processed = 0
        skipped = 0
        ingested = 0

        for traj_path in traj_files:
            sid = traj_path.stem.replace(".trajectory", "")
            if sid in processed:
                skipped += 1
                continue

            result = self._process_trajectory(traj_path)
            if result["count"] > 0:
                processed[sid] = {
                    "ts": datetime.now().isoformat(),
                    "ingested": result["ingested"],
                    "count": result["count"],
                }
                new_processed += 1
                ingested += result["ingested"]

        self._save_checkpoint(processed)

        return {
            "status": "ok",
            "new_processed": new_processed,
            "skipped": skipped,
            "ingested": ingested,
            "total_tracked": len(processed),
        }

    def _process_trajectory(self, traj_path: Path) -> dict:
        """解析单个 trajectory 文件，提取记忆"""
        count = 0
        ingested = 0

        try:
            with open(traj_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    entry_type = entry.get("type", "")

                    # 处理会话结束：提取完整对话摘要
                    if entry_type == "trace.artifacts":
                        data = entry.get("data", {})
                        assistant_texts = data.get("assistantTexts", [])
                        final_prompt = data.get("finalPromptText", "")

                        # 提取用户消息和助手回复
                        for idx, assistant_text in enumerate(assistant_texts):
                            if self._is_meaningful(assistant_text):
                                text = self._clean_text(assistant_text)
                                if len(text) > 20:
                                    try:
                                        remember(
                                            raw_text=text,
                                            drawer_id="openclaw",
                                            importance=0.6,
                                            tags=["openclaw", "conversation"],
                                            source="openclaw-sync",
                                            created_by="openclaw-memory-engine",
                                        )
                                        ingested += 1
                                    except Exception as e:
                                        logger.debug(f"remember error: {e}")
                                    count += 1

                        # 提取工具使用记录作为行为记忆
                        tool_metas = data.get("toolMetas", [])
                        for tool_meta in tool_metas:
                            tool_name = tool_meta.get("toolName", "")
                            meta = tool_meta.get("meta", "")
                            if tool_name and meta:
                                tool_text = f"使用工具 [{tool_name}]: {meta}"
                                if len(tool_text) > 15:
                                    try:
                                        remember(
                                            raw_text=tool_text,
                                            drawer_id="openclaw",
                                            importance=0.4,
                                            tags=["openclaw", "tool-use"],
                                            source="openclaw-sync",
                                            created_by="openclaw-memory-engine",
                                        )
                                        ingested += 1
                                    except Exception as e:
                                        logger.debug(f"remember error: {e}")
                                    count += 1

                    # 处理会话开始：记录新会话创建
                    elif entry_type == "session.started":
                        data = entry.get("data", {})
                        session_key = entry.get("sessionKey", "")
                        message_provider = data.get("messageProvider", "")
                        if message_provider:
                            text = f"OpenClaw 新会话启动: {message_provider} ({session_key})"
                            try:
                                remember(
                                    raw_text=text,
                                    drawer_id="openclaw",
                                    importance=0.5,
                                    tags=["openclaw", "session-start"],
                                    source="openclaw-sync",
                                    created_by="openclaw-memory-engine",
                                )
                                ingested += 1
                                count += 1
                            except Exception:
                                pass

        except Exception as e:
            logger.error(f"Error processing {traj_path}: {e}")

        return {"count": count, "ingested": ingested}

    def _is_meaningful(self, text: str) -> bool:
        """判断文本是否有意义（不是空白或纯符号）"""
        if not text or len(text.strip()) < 10:
            return False
        # 过滤纯emoji或纯符号
        if re.match(r"^[^\w一-鿿]+$", text.strip()):
            return False
        return True

    def _clean_text(self, text: str) -> str:
        """清理文本中的格式标记"""
        # 移除 markdown 代码块标记
        text = re.sub(r"```[\s\S]*?```", "", text)
        # 移除 [Mon 2026-05-11 01:07 GMT+8] 时间戳前缀
        text = re.sub(r"\[.{3} \d{4}-\d{2}-\d{2}.*?\]", "", text)
        # 移除 ou_xxx 用户前缀
        text = re.sub(r"ou_[a-f0-9]+:", "", text)
        # 清理多余空白
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()
        return text

    def _load_checkpoint(self) -> dict:
        """加载已处理的会话记录"""
        if CHECKPOINT_FILE.exists():
            try:
                return json.loads(CHECKPOINT_FILE.read_text())
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_checkpoint(self, data: dict):
        """保存处理进度"""
        CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
        CHECKPOINT_FILE.write_text(json.dumps(data, ensure_ascii=False))


register_engine("openclaw_memory", experimental=True)(OpenClawMemoryEngine)

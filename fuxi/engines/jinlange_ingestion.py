"""伏羲 v1.0 — 瑾岚阁记忆自主采集引擎

扫描瑾岚阁所有 Agent 的会话文件（JSONL），提取新产生的记忆，
通过 ingestion pipeline 存入伏羲记忆系统。

运行方式:
  - 由 cognitive_loop 定期调度（默认每 5 分钟）
  - 或通过 API 手动触发
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.memory.ingestion import remember

logger = logging.getLogger("fuxi.engine.jinlange_ingestion")

# 瑾岚阁 Agent 根目录
AGENTS_DIR = Path(os.environ.get("OPENCLAW_STATE_DIR",
                                  Path.home() / ".openclaw")) / "agents"

# 状态文件（记录每个会话上次采集的位置）
_STATE_FILE = Path(__file__).parent.parent / ".jinlange_ingestion_state.json"


def _load_state() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text())
    except Exception:
        return {}


def _save_state(state: dict):
    _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False))


def _extract_memory_text(record: dict) -> str | None:
    """从会话记录中提取有意义的记忆文本。

    策略:
    - 只处理 type=message 且 role=assistant 的最终回复
    - 提取 text 内容，过滤掉过短或纯元数据的回复
    """
    if record.get("type") != "message":
        return None
    msg = record.get("message", {})
    if msg.get("role") != "assistant":
        return None
    contents = msg.get("content", [])
    if isinstance(contents, list):
        parts = []
        for c in contents:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(c.get("text", ""))
        text = "\n".join(parts).strip()
    elif isinstance(contents, str):
        text = contents.strip()
    else:
        return None
    if len(text) < 50:  # 过滤太短的回复
        return None
    return text


def _scan_session_file(session_id: str, filepath: Path, last_offset: int = 0) -> tuple[list[str], int]:
    """扫描单个会话文件，返回 (新记忆文本列表, 新 offset)。"""
    memories = []
    new_offset = last_offset
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            # 跳到上次位置
            for _ in range(last_offset):
                f.readline()
            line_num = last_offset
            for line in f:
                line_num += 1
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = _extract_memory_text(record)
                if text:
                    memories.append(text)
            new_offset = line_num
    except Exception as e:
        logger.warning(f"Scan error {filepath}: {e}")
    return memories, new_offset


@register_engine("jinlange_ingestion", experimental=False)
class JinlangeIngestionEngine(CognitiveEngine):
    """瑾岚阁记忆自主采集引擎 — 扫描所有 Agent 会话，提取新记忆存入伏羲"""

    name = "jinlange_ingestion"
    priority = 6
    interval = 300  # 5 分钟

    def run(self) -> dict:
        state = _load_state()
        total_memories = 0
        total_sessions_scanned = 0
        agent_stats = {}

        if not AGENTS_DIR.exists():
            logger.warning(f"Agents directory not found: {AGENTS_DIR}")
            return {"status": "skip", "reason": "agents_dir_not_found"}

        for agent_dir in sorted(AGENTS_DIR.iterdir()):
            if not agent_dir.is_dir():
                continue
            agent_id = agent_dir.name
            sessions_dir = agent_dir / "sessions"
            if not sessions_dir.is_dir():
                continue

            agent_memory_count = 0
            # 只扫描 .jsonl（会话文件），跳过 .trajectory.jsonl
            session_files = sorted(sessions_dir.glob("*.jsonl"))
            # 过滤掉 trajectory 文件
            session_files = [f for f in session_files if not f.name.endswith(".trajectory.jsonl")]

            for sf in session_files:
                session_id = sf.stem
                key = f"{agent_id}:{session_id}"
                last_offset = state.get(key, 0)

                # 如果文件被截断或重置，offset 可能大于行数，从头开始
                try:
                    with open(sf, "r", encoding="utf-8") as _f:
                        line_count = sum(1 for _ in _f if _.strip())
                except Exception:
                    continue

                if last_offset > line_count:
                    last_offset = 0

                memories, new_offset = _scan_session_file(session_id, sf, last_offset)

                if new_offset != last_offset:
                    state[key] = new_offset
                    total_sessions_scanned += 1

                for mem_text in memories[:5]:  # 每会话最多取 5 条，避免单次过多
                    tagged_text = f"[瑾岚阁/{agent_id}] {mem_text}"
                    try:
                        remember(
                            raw_text=tagged_text[:2000],  # 限制单条长度
                            drawer_id=f"{agent_id}_view",
                            importance=0.6,
                            source=f"agent:{agent_id}",
                            created_by=agent_id,
                            tags=["jinlange", agent_id, "auto-ingested"],
                            confidence=0.8,
                        )
                        agent_memory_count += 1
                        total_memories += 1
                    except Exception as e:
                        logger.warning(f"Failed to remember from {agent_id}: {e}")

            if agent_memory_count > 0:
                agent_stats[agent_id] = agent_memory_count

        _save_state(state)

        result = {
            "status": "ok",
            "memories_ingested": total_memories,
            "sessions_scanned": total_sessions_scanned,
            "agents": agent_stats,
            "timestamp": datetime.now().isoformat(),
        }
        logger.info(f"Jinlange ingestion: {total_memories} memories from {len(agent_stats)} agents")
        self._state.metadata["last_ingestion"] = result
        return result


def reset_ingestion_state():
    """重置采集状态（强制下次全量扫描）。"""
    _save_state({})
    logger.info("Jinlange ingestion state reset")

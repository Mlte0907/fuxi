"""伏羲 v1.5 — PerceptionEngine 外部感知（多模态框架 + 时间感知）"""
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from fuxi.config import config
from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.perception")

AGENTS_DIR = Path.home() / ".openclaw" / "agents"

# v1.5: 支持的多模态类型（已定义类型，待接入 CLIP/Whisper 管线）
SUPPORTED_MODALITIES = {"image", "audio", "video", "document"}

# v1.5: 多模态管线状态
_MULTIMODAL_PIPELINE_READY = False  # 待接入 CLIP+Whisper


@register_engine("perception", experimental=False)
class PerceptionEngine(CognitiveEngine):
    """外部感知 v1.5 — 多模态框架 + 时间感知 + 外部知识"""
    name = "perception"
    priority = 6
    interval = 120

    def run(self) -> dict:
        if not AGENTS_DIR.is_dir():
            return {"status": "idle", "reason": "agents dir not found"}

        last_scan = self._state.metadata.get("last_scan", {})
        now = time.time()
        discoveries = []

        for agent_dir in sorted(AGENTS_DIR.iterdir()):
            if not agent_dir.is_dir():
                continue
            agent_id = agent_dir.name
            sessions_dir = agent_dir / "sessions"
            if not sessions_dir.is_dir():
                continue

            # 扫描会话文件
            for sf in sorted(sessions_dir.glob("*.jsonl"), key=os.path.getmtime, reverse=True):
                sf_key = str(sf)
                mtime = os.path.getmtime(sf)
                prev_mtime = last_scan.get(sf_key, 0)

                if mtime <= prev_mtime:
                    continue

                # 读取新行
                try:
                    new_messages = self._read_new_lines(sf, prev_mtime)
                except Exception:
                    continue

                last_scan[sf_key] = mtime

                for msg in new_messages:
                    if msg.get("type") != "message":
                        continue
                    content = str(msg.get("content", ""))[:200]
                    if not content.strip():
                        continue

                    discoveries.append({
                        "agent_id": agent_id,
                        "session_id": sf.stem,
                        "content": content,
                        "timestamp": msg.get("timestamp", ""),
                    })

        self._state.metadata["last_scan"] = last_scan

        # v2.0: 时间感知分析
        time_patterns = self._analyze_time_patterns()

        # v2.0: 外部知识摄取
        external_kb = self._ingest_external_knowledge()

        # 写入发现到记忆
        written = 0
        if discoveries:
            try:
                from fuxi.memory.ingestion import remember
                for d in discoveries[-5:]:  # 最多记录 5 条
                    remember(
                        raw_text=f"[感知] Agent '{d['agent_id']}' 活动: {d['content'][:150]}",
                        drawer_id="longterm",
                        importance=0.25,
                        source="perception",
                        confidence=0.6,
                        created_by="perception",
                        tags=["感知", f"agent:{d['agent_id']}"],
                    )
                    written += 1
                    get_event_bus().publish(Event(
                        type="perception.activity",
                        data={"agent_id": d["agent_id"], "session": d["session_id"]},
                        priority=EventPriority.LOW,
                        source="engine:perception",
                    ))
            except Exception as e:
                logger.debug(f"Perception memory write failed: {e}")

        state = {
            "agents_scanned": len(list(AGENTS_DIR.iterdir())),
            "discoveries": len(discoveries),
            "written": written,
            "time_patterns": time_patterns,
            "external_kb": external_kb,
            "v": "1.5",
            "timestamp": datetime.now().isoformat(),
        }

        self._state.metadata["last_state"] = state
        return state

    def _read_new_lines(self, filepath, prev_mtime: float) -> list:
        """读取自上次扫描以来的新行"""
        messages = []
        with open(filepath) as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    msg = json.loads(stripped)
                    ts_str = msg.get("timestamp", "")
                    if ts_str:
                        try:
                            msg_time = datetime.fromisoformat(ts_str).timestamp()
                            if msg_time <= prev_mtime:
                                continue
                        except (ValueError, TypeError):
                            pass
                    messages.append(msg)
                except json.JSONDecodeError:
                    continue
        return messages

    # v2.0: 时间感知 — 基于记忆时间分布推断活跃周期
    def _analyze_time_patterns(self) -> dict:
        """分析记忆时间分布，发现活跃时段"""
        pool = get_pool()
        rows = pool.fetchall(
            "SELECT strftime('%H', created_at) AS hour, COUNT(*) AS cnt "
            "FROM items WHERE archived=0 AND created_at > datetime('now', '-7 days') "
            "GROUP BY hour ORDER BY cnt DESC"
        )
        if not rows:
            return {"peak_hour": None, "pattern": "unknown"}

        peak_hour = rows[0]["hour"]
        total = sum(r["cnt"] for r in rows)
        active_hours = [r["hour"] for r in rows if r["cnt"] > total * 0.1]

        return {
            "peak_hour": peak_hour,
            "active_hours": active_hours,
            "distribution": {r["hour"]: r["cnt"] for r in rows},
        }

    # v2.0: 外部知识摄取 — 扫描预定义目录摄取外部文档
    def _ingest_external_knowledge(self) -> dict:
        """从外部目录（如 ~/knowledge）摄取知识文档"""
        pool = get_pool()
        kb_dir = Path.home() / "knowledge"
        if not kb_dir.is_dir():
            return {"ingested": 0, "status": "no_kb_dir"}

        ingested = 0
        for f in kb_dir.glob("*.md"):
            try:
                content = f.read_text(encoding="utf-8")[:1000]
                # 检查是否已摄取（按文件名去重）
                existing = pool.fetchone(
                    "SELECT id FROM items WHERE raw_text LIKE ? AND archived=0",
                    (f"%[{f.stem}]%",)
                )
                if existing:
                    continue
                from fuxi.memory.ingestion import remember
                remember(
                    raw_text=f"[外部知识] {content}",
                    drawer_id="longterm",
                    importance=0.4,
                    source="external",
                    confidence=0.7,
                    created_by="perception",
                    tags=["外部知识", "knowledge", f"file:{f.stem}"],
                )
                ingested += 1
            except Exception as e:
                logger.debug(f"External knowledge ingestion failed for {f}: {e}")

        return {"ingested": ingested, "status": "ok" if ingested > 0 else "skipped"}

    # v2.0: 多模态检测 — 扫描附件/多媒体路径
    def _detect_multimodal(self, agent_id: str, session_id: str) -> list:
        """检测会话中的多模态内容（图片/音频/视频/文档路径）"""
        pool = get_pool()
        pool_path = config.base_dir / "multimodal"
        if not pool_path.is_dir():
            return []

        multimodal_items = []
        agent_dir = pool_path / agent_id / session_id
        if not agent_dir.is_dir():
            return []

        for f in agent_dir.iterdir():
            ext = f.suffix.lower()
            modality = None
            if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                modality = "image"
            elif ext in {".mp3", ".wav", ".m4a", ".ogg"}:
                modality = "audio"
            elif ext in {".mp4", ".webm", ".mov"}:
                modality = "video"
            elif ext in {".pdf", ".doc", ".docx", ".txt"}:
                modality = "document"

            if modality:
                try:
                    from fuxi.memory.ingestion import remember
                    remember(
                        raw_text=f"[多模态:{modality}] 文件: {f.name}",
                        drawer_id="longterm",
                        importance=0.3,
                        source="perception",
                        confidence=0.5,
                        created_by="perception",
                        tags=[f"modality:{modality}", f"file:{f.stem}"],
                    )
                    multimodal_items.append({"modality": modality, "file": f.name})
                except Exception as e:
                    logger.debug(f"Multimodal remember failed: {e}")

        return multimodal_items

    def _describe_image(self, filepath: Path) -> str | None:
        """v1.5: 使用 LLM 描述图像内容（待接入 CLIP）"""
        try:
            import base64
            from fuxi.agent.integration import OpenClawAdapter

            # 读取图片并 base64 编码
            with open(filepath, "rb") as f:
                img_data = base64.b64encode(f.read()).decode()

            adapter = OpenClawAdapter()
            prompt = (
                "描述这张图片的内容，用50字以内概括。"
                "只输出描述文字，不要前缀。"
            )
            result = adapter.call_agent(
                "qinglong",
                prompt,
                attachments=[{"type": "image", "data": img_data, "mime": "image/jpeg"}]
            )
            if result and "reply" in result:
                return result["reply"].strip()
        except Exception as e:
            logger.debug(f"Image description failed: {e}")
        return None

    def _transcribe_audio(self, filepath: Path) -> str | None:
        """v1.5: 使用 LLM 转录音频内容（待接入 Whisper）"""
        try:
            from fuxi.agent.integration import OpenClawAdapter

            with open(filepath, "rb") as f:
                audio_data = base64.b64encode(f.read()).decode()

            adapter = OpenClawAdapter()
            prompt = "转录以下音频的内容，保留关键信息。"
            result = adapter.call_agent(
                "qinglong",
                prompt,
                attachments=[{"type": "audio", "data": audio_data, "mime": "audio/wav"}]
            )
            if result and "reply" in result:
                return result["reply"].strip()
        except Exception as e:
            logger.debug(f"Audio transcription failed: {e}")
        return None

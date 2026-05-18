"""伏羲 v1.0 — MultimodalMemoryEngine 多模态记忆引擎"""
import base64
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.multimodal_memory")

# 尝试导入图像处理库
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False


@dataclass
class MediaItem:
    """媒体条目"""
    item_id: int
    media_type: str  # image/audio
    file_path: str
    mime_type: str
    transcription: Optional[str] = None
    description: Optional[str] = None
    processed_at: Optional[str] = None


@register_engine("multimodal_memory", experimental=True)
class MultimodalMemoryEngine(CognitiveEngine):
    """多模态记忆引擎 — 图片描述 / 音频转录

    功能:
    1. 图片理解：使用 PIL/LLM 生成图片描述
    2. 音频转录：使用 Whisper 将音频转为文字
    3. 多模态条目关联：索引到 items 表
    """
    name = "multimodal_memory"
    priority = 6
    interval = 300
    experimental = True

    def run(self) -> dict:
        pool = get_pool()
        results = {"image_desc": 0, "audio_transcribe": 0, "errors": 0}

        # 处理图片描述
        image_items = self._load_unprocessed_media(pool, "image")
        for item in image_items:
            try:
                ok = self._process_image(item, pool)
                if ok:
                    results["image_desc"] += 1
            except Exception as e:
                logger.error(f"[multimodal] image process error: {e}")
                results["errors"] += 1

        # 处理音频转录
        audio_items = self._load_unprocessed_media(pool, "audio")
        for item in audio_items:
            try:
                ok = self._process_audio(item, pool)
                if ok:
                    results["audio_transcribe"] += 1
            except Exception as e:
                logger.error(f"[multimodal] audio process error: {e}")
                results["errors"] += 1

        return {
            "status": "completed",
            "results": results,
            "timestamp": datetime.now().isoformat(),
        }

    def _load_unprocessed_media(self, pool, media_type: str) -> list[dict]:
        """加载未处理的多模态条目"""
        rows = pool.fetchall(
            "SELECT id, content, metadata FROM items "
            "WHERE archived=0 AND multimodal_status != 'processed' "
            "AND media_type=? "
            "ORDER BY created_at ASC LIMIT 50",
            (media_type,)
        )
        return [dict(r) for r in rows]

    def _process_image(self, item: dict, pool) -> bool:
        """处理图片：生成描述"""
        if not PIL_AVAILABLE:
            logger.warning("[multimodal] PIL not available, skipping image")
            return False

        metadata = item.get("metadata") or {}
        file_path = metadata.get("file_path") or metadata.get("image_path")
        if not file_path or not os.path.exists(file_path):
            logger.debug(f"[multimodal] image file not found: {file_path}")
            return False

        try:
            img = Image.open(file_path)
            width, height = img.size
            mode = img.mode

            # 生成图片描述（简单实现：基于元数据）
            description = self._generate_image_description(img, metadata)
            transcription = metadata.get("caption") or description

            self._update_item(pool, item["id"], transcription, description)
            return True

        except Exception as e:
            logger.error(f"[multimodal] image process error for {item['id']}: {e}")
            return False

    def _generate_image_description(self, img, metadata: dict) -> str:
        """生成图片描述"""
        size_info = f"{img.size[0]}x{img.size[1]} {img.mode}"
        if metadata.get("format"):
            size_info += f" {metadata.get('format')}"
        alt_text = metadata.get("alt") or metadata.get("description") or ""
        return f"[Image: {size_info}] {alt_text}".strip()

    def _process_audio(self, item: dict, pool) -> bool:
        """处理音频：Whisper 转录"""
        if not WHISPER_AVAILABLE:
            logger.warning("[multimodal] whisper not available, skipping audio")
            return False

        metadata = item.get("metadata") or {}
        file_path = metadata.get("file_path") or metadata.get("audio_path")
        if not file_path or not os.path.exists(file_path):
            logger.debug(f"[multimodal] audio file not found: {file_path}")
            return False

        try:
            model = whisper.load_model("base")
            result = model.transcribe(file_path, language="zh")
            transcription = result["text"].strip()

            self._update_item(pool, item["id"], transcription, None)
            logger.info(f"[multimodal] transcribed audio {item['id']}: {len(transcription)} chars")
            return True

        except Exception as e:
            logger.error(f"[multimodal] audio transcription error for {item['id']}: {e}")
            return False

    def _update_item(self, pool, item_id: int, transcription: str, description: str | None):
        """更新条目的多模态处理结果"""
        now = datetime.now().isoformat()
        with pool.connection() as c:
            c.execute(
                "UPDATE items SET content=?, multimodal_status='processed', "
                "multimodal_result=?, updated_at=? WHERE id=?",
                (
                    transcription,
                    json.dumps({"description": description, "transcribed_at": now}),
                    now,
                    item_id,
                )
            )

    def _ensure_tables(self):
        """确保多模态相关表存在"""
        pool = get_pool()
        pool.execute(
            "CREATE TABLE IF NOT EXISTS multimodal_cache ("
            "item_id INTEGER PRIMARY KEY, "
            "media_type TEXT, "
            "transcription TEXT, "
            "description TEXT, "
            "processed_at TEXT)"
        )
        pool.execute(
            "ALTER TABLE items ADD COLUMN multimodal_status TEXT DEFAULT 'pending'"
        )
        pool.execute(
            "ALTER TABLE items ADD COLUMN multimodal_result TEXT"
        )

    def _get_subscriptions(self):
        return {
            "media.image_uploaded": self._on_media_event,
            "media.audio_uploaded": self._on_media_event,
        }

    def _on_media_event(self, event):
        self._state.metadata.setdefault("_pending_events", []).append(event.data)


# json import needed
import json
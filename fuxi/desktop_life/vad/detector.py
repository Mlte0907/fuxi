"""VAD 语音活动检测模块 — Silero VAD接入（规划中）"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger("fuxi.vad")


class VADDetector:
    """语音活动检测器
    规划接入 Silero VAD，检测是否有人声活动。
    当前为占位实现。
    """

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        self.running = False

    async def detect(self, audio_chunk: bytes) -> bool:
        """检测是否有人声活动"""
        # TODO: 接入 Silero VAD
        # from silero_vad import load_silero_vad, get_speech_timestamps
        # vad = load_silero_vad()
        # speech = vad(audio_chunk, sampling_rate=16000)
        return True

    async def start(self):
        """启动VAD检测"""
        self.running = True
        logger.info("VAD检测启动")

    def stop(self):
        self.running = False
        logger.info("VAD检测已停止")

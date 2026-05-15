"""麦克风音频输入模块"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger("fuxi.audio_input")


class MicrophoneInput:
    """麦克风音频输入（占位）"""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.running = False
        self.stream: Optional[asyncio.StreamReader] = None

    async def start(self):
        """启动音频采集"""
        self.running = True
        logger.info(f"麦克风输入启动，采样率：{self.sample_rate}")
        # TODO: 接入 pyaudio 或 sounddevice
        # import sounddevice as sd
        # with sd.InputStream(samplerate=self.sample_rate, channels=1, callback=self._callback) as stream:
        #     self.stream = stream
        #     while self.running:
        #         await asyncio.sleep(0.1)

    async def read_chunk(self) -> bytes:
        """读取一段音频数据"""
        # TODO: 返回实际音频数据
        await asyncio.sleep(0.1)
        return b""

    def stop(self):
        self.running = False
        logger.info("麦克风输入已停止")

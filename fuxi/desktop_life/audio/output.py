"""音频播放模块"""
import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("fuxi.audio_output")

class AudioOutput:
    """音频播放（使用mpv）"""

    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None

    async def play(self, audio_path: str):
        """播放音频文件"""
        if not Path(audio_path).exists():
            logger.error(f"Audio file not found: {audio_path}")
            return
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=2)
            except asyncio.TimeoutError:
                self.process.kill()
        self.process = await asyncio.create_subprocess_exec(
            "mpv", "--no-terminal", "--pause=no", audio_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        logger.info(f"Playing: {audio_path}")

    async def play_bytes(self, audio_data: bytes, format: str = "mp3"):
        """播放音频数据"""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as f:
            f.write(audio_data)
            f.flush()
            await self.play(f.name)

    def stop(self):
        if self.process:
            try:
                self.process.terminate()
            except:
                pass

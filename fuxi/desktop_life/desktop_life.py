"""伏羲桌面生命体 — 主入口

Phase 1: 唤醒 → STT → Fuxi对话 → TTS → 播放
"""
import asyncio
import logging
import signal
import sys
import threading
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fuxi.desktop_life.fuxi.client import FuxiClient
from fuxi.desktop_life.tts.edge_tts import EdgeTTSClient

logger = logging.getLogger("fuxi.desktop_life")

fuxi_client = FuxiClient()
tts_client = EdgeTTSClient()


class AudioPlayer:
    """音频播放（Linux版本使用mpv）"""

    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None

    async def play(self, audio_path: str):
        if self.process:
            self.process.terminate()
            await self.process.wait()
        self.process = await asyncio.create_subprocess_exec(
            "mpv", "--no-terminal", audio_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await self.process.wait()

    def stop(self):
        if self.process:
            self.process.terminate()


class WakeWordDetector:
    """唤醒词检测（占位，后续接入openWakeWord）"""

    def __init__(self, wake_word: str = "伏羲"):
        self.wake_word = wake_word
        self.running = False

    async def listen(self):
        logger.info(f"唤醒词检测启动，唤醒词：{self.wake_word}")
        logger.info("按回车键唤醒（后续改为语音唤醒）...")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, input, "")
        logger.info("唤醒词检测到！")
        return True


class VADDetector:
    """语音活动检测（占位，后续接入Silero VAD）"""

    def __init__(self):
        self.running = False

    async def detect(self, audio_chunk: bytes) -> bool:
        return True


class DesktopLife:
    """伏羲桌面生命体主控"""

    def __init__(self):
        self.state = "idle"
        self.running = False
        self.interrupted = False
        self.wake_detector = WakeWordDetector()
        self.vad = VADDetector()
        self.player = AudioPlayer()
        self.conversation_context: list[dict] = []

    async def run(self):
        logger.info("=" * 50)
        logger.info("伏羲桌面生命体启动")
        logger.info("=" * 50)
        self.running = True
        while self.running:
            try:
                self.state = "idle"
                await self.wake_detector.listen()
                self.state = "listening"
                user_text = await self.listen_and_transcribe()
                if not user_text:
                    continue
                logger.info(f"用户说: {user_text}")
                if self.is_interrupted(user_text):
                    logger.info("收到打断指令")
                    continue
                self.state = "thinking"
                response = await self.think(user_text)
                self.state = "speaking"
                await self.speak(response)
                self.state = "idle"
            except KeyboardInterrupt:
                logger.info("收到终止信号")
                self.running = False
            except Exception as e:
                logger.error(f"Error in main loop: {e}")

    async def listen_and_transcribe(self) -> str:
        logger.info("正在聆听...（按回车结束聆听）")
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, input, "请输入: ")
        return text.strip()

    async def think(self, user_text: str) -> str:
        logger.info("伏羲正在思考...")
        memories = fuxi_client.recall_context(agent_id="fuxi_desktop")
        response = fuxi_client.chat(
            message=user_text,
            agent_id="fuxi_desktop",
            context=self.conversation_context,
        )
        self.conversation_context.append({"role": "user", "content": user_text})
        self.conversation_context.append({"role": "assistant", "content": response})
        if len(self.conversation_context) > 20:
            self.conversation_context = self.conversation_context[-20:]
        return response

    async def speak(self, text: str):
        logger.info(f"伏羲回应: {text}")
        try:
            audio_path = tts_client.synthesize_sync(text)
            await self.player.play(audio_path)
        except Exception as e:
            logger.error(f"TTS error: {e}")

    def is_interrupted(self, text: str) -> bool:
        stop_words = ["停止", "别说了", "够了", "stop", "安静"]
        return any(word in text for word in stop_words)

    def stop(self):
        self.running = False
        self.player.stop()


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    life = DesktopLife()
    def signal_handler(sig, frame):
        logger.info("收到终止信号")
        life.stop()
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    await life.run()
    logger.info("伏羲桌面生命体已退出")


if __name__ == "__main__":
    asyncio.run(main())

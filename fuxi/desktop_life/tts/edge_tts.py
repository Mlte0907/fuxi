"""Edge-TTS 客户端 — 免费中文情感TTS"""

import asyncio
import subprocess
from pathlib import Path
from typing import Optional


class EdgeTTSClient:
    """Edge-TTS 客户端，支持中文情感音色"""

    VOICE_XIAOXIAO = "zh-CN-XiaoxiaoNeural"
    VOICE_YUNXIA = "zh-CN-YunxiaNeural"

    def __init__(self, voice: str = VOICE_XIAOXIAO, output_dir: str = "/tmp/fuxi_tts"):
        self.voice = voice
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def synthesize(self, text: str, output_path: Optional[str] = None) -> str:
        """将文本转为语音，返回音频文件路径"""
        if not output_path:
            output_path = self.output_dir / f"tts_{asyncio.get_event_loop().time()}.mp3"

        cmd = [
            "edge-tts",
            "--voice", self.voice,
            "--text", text,
            "--write-media", str(output_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"Edge-TTS failed: {stderr.decode()}")

        return str(output_path)

    def synthesize_sync(self, text: str, output_path: Optional[str] = None) -> str:
        """同步版本"""
        return asyncio.run(self.synthesize(text, output_path))


if __name__ == "__main__":
    client = EdgeTTSClient()
    path = client.synthesize_sync("你好，我是伏羲。")
    print(f"Audio saved to: {path}")

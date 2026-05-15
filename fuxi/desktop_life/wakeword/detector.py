"""唤醒词检测模块 — openWakeWord接入（规划中）"""
import asyncio
import logging
from typing import Callable, Optional

logger = logging.getLogger("fuxi.wakeword")


class WakeWordDetector:
    """唤醒词检测器
    规划接入 openWakeWord，支持中文唤醒词微调。
    当前为占位实现。
    """

    def __init__(self, wake_word: str = "伏羲", model_path: Optional[str] = None):
        self.wake_word = wake_word
        self.model_path = model_path
        self.running = False
        self.callback: Optional[Callable] = None

    async def start(self, on_wake: Callable):
        """启动唤醒词检测"""
        self.callback = on_wake
        self.running = True
        logger.info(f"唤醒词检测启动，唤醒词：{self.wake_word}")
        # TODO: 接入 openWakeWord
        while self.running:
            await asyncio.sleep(0.1)

    def stop(self):
        """停止检测"""
        self.running = False
        logger.info("唤醒词检测已停止")

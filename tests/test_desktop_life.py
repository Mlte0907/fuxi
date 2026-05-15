"""测试 desktop_life 子系统的TTS、播放器和唤醒词检测"""
import pytest
import time

from fuxi.desktop_life.desktop_life import (
    AudioPlayer,
    WakeWordDetector,
    VADDetector,
    fuxi_client,
    tts_client,
)


class TestWakeWordDetector:
    """唤醒词检测测试"""

    def test_wake_word_default(self):
        """默认唤醒词是'伏羲'"""
        detector = WakeWordDetector()
        assert detector.wake_word == "伏羲"
        assert not detector.running

    def test_wake_word_custom(self):
        """自定义唤醒词"""
        detector = WakeWordDetector(wake_word="小伏")
        assert detector.wake_word == "小伏"


class TestVADDetector:
    """语音活动检测测试"""

    def test_vad_init(self):
        """VAD初始化"""
        detector = VADDetector()
        assert not detector.running


class TestAudioPlayer:
    """音频播放器测试"""

    def test_player_init(self):
        """播放器初始化"""
        player = AudioPlayer()
        assert player.process is None

    def test_player_stop_no_process(self):
        """无进程时的stop不应报错"""
        player = AudioPlayer()
        player.stop()


class TestDesktopLifeComponents:
    """桌面生命体组件测试"""

    def test_fuxi_client_imported(self):
        """FuxiClient已导入"""
        assert fuxi_client is not None

    def test_tts_client_imported(self):
        """TTS客户端已导入"""
        assert tts_client is not None
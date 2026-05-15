"""MiniMax STT 客户端 — 语音转文本"""

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Optional

import requests


class MiniMaxSTTClient:
    """MiniMax API STT客户端"""

    API_URL = "https://api.minimax.io/v1/speech/recognition"

    def __init__(self, api_key: str, group_id: str):
        self.api_key = api_key
        self.group_id = group_id

    def transcribe(self, audio_path: str, language: str = "zh") -> str:
        """将音频文件转为文本"""
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        files = {
            "file": ("audio.mp3", audio_data, "audio/mpeg"),
            "model": (None, "speech-01"),
            "language_boost": (None, language),
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "GroupId": self.group_id,
        }

        resp = requests.post(self.API_URL, files=files, headers=headers, timeout=30)
        resp.raise_for_status()

        result = resp.json()
        if result.get("data", {}).get("text"):
            return result["data"]["text"]
        return ""


class MiniMaxTTSClient:
    """MiniMax API TTS客户端（备选，当Edge-TTS不可用时）"""

    API_URL = "https://api.minimax.io/v1/t2a_v2"

    def __init__(self, api_key: str, group_id: str):
        self.api_key = api_key
        self.group_id = group_id

    def synthesize(self, text: str, voice_setting: str = "female_shaonv") -> str:
        """将文本转为语音，返回音频文件路径"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "speech-02-hd",
            "text": text,
            "stream": False,
            "voice_setting": voice_setting,
        }

        resp = requests.post(self.API_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()

        result = resp.json()
        audio_url = result.get("data", {}).get("audio", {}).get("audio_url", "")
        return audio_url

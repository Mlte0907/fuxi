"""Fuxi 对话 API 客户端"""

import json
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger("fuxi.desktop_life")

DEFAULT_BASE_URL = "http://localhost:19528"


class FuxiClient:
    """Fuxi 对话API客户端"""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, api_key: str = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("FUXI_API_KEY", "your_fuxi_api_key_here")

    def chat(self, message: str, agent_id: str = "fuxi_desktop", context: Optional[list] = None) -> str:
        """发送对话请求，返回AI响应文本"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "message": message,
            "agent_id": agent_id,
            "stream": False,
        }
        if context:
            payload["context"] = context

        try:
            resp = requests.post(
                f"{self.base_url}/chat",
                headers=headers,
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            result = resp.json()
            return result.get("reply", result.get("text", ""))
        except requests.exceptions.ConnectionError:
            logger.error(f"Cannot connect to Fuxi API at {self.base_url}")
            return "无法连接到伏羲系统，请检查服务状态。"
        except Exception as e:
            logger.error(f"Fuxi chat error: {e}")
            return f"对话出错：{e}"

    def recall_context(self, agent_id: str = "fuxi_desktop", limit: int = 10) -> list:
        """召回最近的上下文记忆"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            resp = requests.get(
                f"{self.base_url}/memory/recall",
                headers=headers,
                params={"agent_id": agent_id, "limit": limit},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("contexts", [])
        except Exception as e:
            logger.warning(f"Memory recall failed: {e}")
            return []

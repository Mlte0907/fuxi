"""伏羲 v1.0 — OpenClaw 集成适配"""
import json
import logging
import os
import subprocess
from typing import Optional

import httpx

from fuxi.config import config

logger = logging.getLogger("fuxi.agent.integration")

_OPENCLAW_BIN = "/home/xiaoxin/.npm-global/bin/openclaw"


class OpenClawAdapter:
    """与 OpenClaw Gateway 集成 — 通过 CLI 调用 Agent"""

    def __init__(self):
        self.gateway = config.openclaw_gateway

    def health(self) -> dict:
        try:
            url = f"{self.gateway}/health"
            with httpx.Client(timeout=5) as client:
                resp = client.get(url)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning(f"OpenClaw health check failed: {e}")
            return {"status": "unreachable", "error": str(e)}

    def call_agent(self, agent_id: str, message: str,
                   model: Optional[str] = None) -> Optional[dict]:
        """调用 OpenClaw Agent — 通过 CLI"""
        cmd = [
            _OPENCLAW_BIN, "agent",
            "--agent", agent_id,
            "--message", message,
            "--json",
            "--timeout", "120",
        ]
        if model:
            cmd += ["--model", model]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=130,
            )
            if result.returncode != 0:
                logger.error(f"Agent call [{agent_id}] CLI failed: {result.stderr}")
                return {"error": result.stderr or f"exit code {result.returncode}"}

            data = json.loads(result.stdout)
            if data.get("status") == "ok" and "result" in data:
                payloads = data["result"].get("payloads", [])
                reply_text = payloads[0].get("text", "") if payloads else ""
                return {
                    "reply": reply_text,
                    "run_id": data.get("runId"),
                    "meta": data["result"].get("meta", {}),
                }
            return {"error": data.get("summary", "unknown error")}
        except subprocess.TimeoutExpired:
            logger.error(f"Agent call [{agent_id}] timed out")
            return {"error": "timeout"}
        except json.JSONDecodeError as e:
            logger.error(f"Agent call [{agent_id}] JSON parse failed: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Agent call [{agent_id}] failed: {e}")
            return {"error": str(e)}

    def deliver_to_channel(self, agent_id: str, message: str,
                           channel: str = "qqbot",
                           reply_to: Optional[str] = None,
                           model: Optional[str] = None) -> Optional[dict]:
        """调用 Agent 并推送到指定通道（QQ/飞书等）

        使用 --channel <channel> --deliver 标志，将 Agent 回复推送到外部通道。
        reply_to: QQ openid 或飞书 open_id，指定投递目标用户。
        """
        cmd = [
            _OPENCLAW_BIN, "agent",
            "--agent", agent_id,
            "--message", message,
            "--channel", channel,
            "--deliver",
            "--json",
            "--timeout", "120",
        ]
        if reply_to:
            cmd += ["--reply-to", reply_to]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=130,
            )
            if result.returncode != 0:
                logger.error(f"Deliver to [{channel}] via [{agent_id}] failed: {result.stderr}")
                return {"error": result.stderr or f"exit code {result.returncode}"}

            data = json.loads(result.stdout)
            if data.get("status") == "ok" and "result" in data:
                payloads = data["result"].get("payloads", [])
                reply_text = payloads[0].get("text", "") if payloads else ""
                return {
                    "reply": reply_text,
                    "run_id": data.get("runId"),
                    "channel": channel,
                    "meta": data["result"].get("meta", {}),
                }
            return {"error": data.get("summary", "unknown error")}
        except subprocess.TimeoutExpired:
            logger.error(f"Deliver to [{channel}] via [{agent_id}] timed out")
            return {"error": "timeout"}
        except json.JSONDecodeError as e:
            logger.error(f"Deliver JSON parse failed: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Deliver failed: {e}")
            return {"error": str(e)}

    def send_message(self, channel: str, target: str, message: str,
                     account: Optional[str] = None,
                     reply_to: Optional[str] = None) -> Optional[dict]:
        """通过 openclaw message send 主动推送消息到外部通道

        与 deliver_to_channel（session-reply）不同，此方法用于主动推送，
        不依赖已有会话上下文。适用于 QQbot 等渠道的 bot 主动发消息场景。
        target 格式: qqbot:c2c:<openid> 或 qqbot:group:<groupid>
        account: 多渠道账号 ID，如 "fuxi"、"default"
        """
        cmd = [
            _OPENCLAW_BIN, "message", "send",
            "--channel", channel,
            "--target", target,
            "--message", message,
            "--json",
        ]
        if account:
            cmd += ["--account", account]
        if reply_to:
            cmd += ["--reply-to", reply_to]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=130,
            )
            if result.returncode != 0:
                logger.error(f"Send message to [{channel}] failed: {result.stderr}")
                return {"error": result.stderr or f"exit code {result.returncode}"}

            data = json.loads(result.stdout)
            return data
        except subprocess.TimeoutExpired:
            logger.error(f"Send message to [{channel}] timed out")
            return {"error": "timeout"}
        except json.JSONDecodeError as e:
            logger.error(f"Send message JSON parse failed: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Send message failed: {e}")
            return {"error": str(e)}

    def list_openclaw_agents(self) -> list:
        """列出所有 OpenClaw 注册的 Agent — 通过 CLI"""
        try:
            result = subprocess.run(
                [_OPENCLAW_BIN, "agents", "list", "--json"],
                capture_output=True, text=True, timeout=15,
                env={**os.environ, "HOME": os.path.expanduser("~")},
            )
            if result.returncode != 0:
                logger.warning(f"List agents CLI failed: rc={result.returncode} stderr={result.stderr[:200]}")
                return []
            return json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            logger.warning("List agents timed out")
            return []
        except json.JSONDecodeError as e:
            logger.warning(f"List agents JSON parse failed: {e}")
            return []
        except Exception as e:
            logger.warning(f"List agents failed: {e}")
            return []

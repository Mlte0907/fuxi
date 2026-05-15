#!/usr/bin/env python3
"""通过 OpenClaw 向 QQ bot 发送主动消息

用法:
  python3 send_qq.py "消息内容"
  echo "消息" | python3 send_qq.py

目标用户从 FUXI_QQ_OPENID 环境变量或 fuxi/config.py 的 qq_openid 读取。
"""
import os
import subprocess
import sys
from pathlib import Path

OPENCLAW_BIN = "/home/xiaoxin/.npm-global/bin/openclaw"

# 尝试从多个来源获取 openid
OPENID = os.environ.get("FUXI_QQ_OPENID", "")

# 如果环境变量没有，尝试从 config 读取
if not OPENID:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from fuxi.config import config
        OPENID = config.qq_openid
    except Exception:
        pass


def send_qq(message: str, openid: str = None) -> dict:
    """主动发送 QQ bot 消息"""
    target = openid or OPENID
    if not target:
        return {"status": "error", "error": "no openid configured"}

    cmd = [
        OPENCLAW_BIN, "message", "send",
        "--channel", "qqbot",
        "--account", "fuxi",
        "--target", target,
        "--message", message,
        "--json",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        import json
        return json.loads(result.stdout) if result.stdout.strip() else {
            "status": "error" if result.returncode != 0 else "ok",
            "stderr": result.stderr[:200],
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()
    if not msg:
        print("Usage: python3 send_qq.py <message>")
        sys.exit(1)
    import json
    result = send_qq(msg)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result.get("status") == "ok" else 1)

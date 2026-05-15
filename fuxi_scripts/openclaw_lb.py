#!/usr/bin/env python3
"""
OpenClaw 多实例负载均衡管理器
在伏羲 API 代理层 (:19528) 实现基于 session 的路由分发。

策略：
- 不修改 OpenClaw 源码
- 利用伏羲代理的请求路由功能，按 user/session 将请求分发到不同端口
- 使用时需要在伏羲 API 中集成此路由逻辑

用法（概念验证）：
    python3 openclaw_lb.py status     # 查看当前实例状态
    python3 openclaw_lb.py start      # 启动多实例（需手动配置不同端口）
    python3 openclaw_lb.py stop       # 停止所有实例
"""
import subprocess
import json
import urllib.request
import sys
import os

ORIGINAL_PORT = 18789
ORIGINAL_DATA_DIR = os.path.expanduser("~/.openclaw")

# 多实例配置
INSTANCES = [
    {"port": ORIGINAL_PORT, "name": "gateway-main", "data_dir": ORIGINAL_DATA_DIR},
    # 扩展更多实例时需要额外的数据目录和端口
    # {"port": 18790, "name": "gateway-2", "data_dir": "~/.openclaw-2"},
    # {"port": 18791, "name": "gateway-3", "data_dir": "~/.openclaw-3"},
    # {"port": 18792, "name": "gateway-4", "data_dir": "~/.openclaw-4"},
]


def check_health(port: int) -> dict:
    """检查 OpenClaw 实例健康状态"""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def status():
    print(f"{'Port':<8} {'Instance':<25} {'Status'}")
    print("-" * 55)
    for inst in INSTANCES:
        health = check_health(inst["port"])
        if "error" in health:
            print(f"{inst['port']:<8} {inst['name']:<25} ❌ {health['error']}")
        else:
            print(f"{inst['port']:<8} {inst['name']:<25} ✅ OK")


def check_processes():
    """检查 OpenClaw 进程运行状态"""
    try:
        result = subprocess.run(
            ["pgrep", "-af", "openclaw"],
            capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip():
            print("Running OpenClaw processes:")
            for line in result.stdout.strip().split("\n"):
                print(f"  {line}")
        else:
            print("No OpenClaw processes found")
    except Exception as e:
        print(f"Error checking processes: {e}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 openclaw_lb.py [status|processes]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "status":
        status()
    elif cmd == "processes":
        check_processes()
    else:
        print(f"Unknown command: {cmd}")
        print("Available: status, processes")


if __name__ == "__main__":
    main()
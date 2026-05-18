#!/usr/bin/env python3
"""
伏羲工具箱 - Claude Code 调用 Fuxi 能力的统一接口
用法:
  python3 fuxi_tool.py decide <任务描述>   # 决策建议（基于记忆）
  python3 fuxi_tool.py bbon <任务描述>     # 多轨迹决策
  python3 fuxi_tool.py engines              # 查看所有引擎状态
  python3 fuxi_tool.py health              # 系统健康状态
  python3 fuxi_tool.py experience <关键词>  # 经验库检索
"""
import sys
import os
import json
import urllib.request
import urllib.error
import urllib.parse

FUXI_API = "http://localhost:19528"
FUXI_KEY = os.environ.get("FUXI_API_KEY", "jinlange-fuxi-2026")

def api_get(path):
    """GET 请求"""
    url = f"{FUXI_API}{path}"
    headers = {"X-API-Key": FUXI_KEY, "Accept": "application/json"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

def api_post(path, data):
    """POST 请求"""
    url = f"{FUXI_API}{path}"
    headers = {"X-API-Key": FUXI_KEY, "Content-Type": "application/json"}
    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

def cmd_decide(task):
    """决策建议 - 基于记忆系统获取决策建议"""
    result = api_get(f"/api/v2/decisions/advice?task={urllib.parse.quote(task)}")
    if "error" in result:
        print(f"❌ 调用失败: {result['error']}")
        return
    code = result.get("code", 0)
    if code != 0:
        print(f"🤔 没有找到相关决策建议")
        return
    data = result.get("data") or {}
    suggestions = data.get("suggestions", [])
    print(f"💡 决策建议 (task: {task})")
    print(f"   找到 {len(suggestions)} 条历史经验")
    if suggestions:
        for i, s in enumerate(suggestions, 1):
            print(f"\n  方案 {i}: [{s.get('type', 'unknown')}]")
            print(f"    {s.get('advice', '')[:100]}")
            if s.get('outcome'):
                print(f"    效果: {s.get('outcome')}")
    else:
        print("\n📭 没有历史经验，建议人工决策或使用 /bbon 命令")

def cmd_bbon(task):
    """多轨迹决策 - 完整的 bBoN 分析"""
    print(f"🎯 bBoN 多轨迹决策启动: {task}")
    print("=" * 50)
    # 先获取历史建议
    result = api_get(f"/api/v2/decisions/advice?task={urllib.parse.quote(task)}")
    data = result.get("data") or {}
    suggestions = data.get("suggestions", [])
    print(f"\n📊 历史经验: {len(suggestions)} 条")
    print(f"\n💡 请使用 /bbon {task} 命令进行完整的多轨迹分析")
    print("   (bBoN 需要生成多个候选方案并评估，超出当前工具能力)")
    if suggestions:
        print("\n参考历史决策:")
        for s in suggestions[:3]:
            print(f"  • [{s.get('type')}] {s.get('advice', '')[:60]}...")

def cmd_engines():
    """查看引擎状态"""
    result = api_get("/api/v2/engines/health")
    if "error" in result:
        print(f"❌ 调用失败: {result['error']}")
        return
    data = result.get("data") or {}
    engines = data.get("engines", [])
    running = [e for e in engines if e.get("running")]
    print(f"🧠 伏羲引擎状态 (共 {len(engines)} 个，运行中 {len(running)} 个)")
    print()
    # 显示实验性引擎
    exp = [e for e in engines if e.get("experimental")]
    if exp:
        print("⚙️  实验性引擎:")
        for e in exp:
            status = "✅" if e.get("running") else "❌"
            print(f"  {status} {e.get('name')}: run_count={e.get('run_count', 0)}")

def cmd_health():
    """系统健康状态"""
    result = api_get("/health")
    if "error" in result:
        print(f"❌ 调用失败: {result['error']}")
        return
    data = result.get("data") or {}
    print(f"✅ 伏羲系统健康")
    print(f"   版本: {data.get('version', 'unknown')}")
    print(f"   运行时间: {int(data.get('uptime_seconds', 0))} 秒")

def cmd_experience(keyword):
    """经验库检索"""
    result = api_get(f"/api/v2/decisions/experiences?limit=10")
    if "error" in result:
        print(f"❌ 调用失败: {result['error']}")
        return
    data = result.get("data") or {}
    exps = data.get("experiences", [])
    # 简单过滤
    filtered = [e for e in exps if keyword.lower() in json.dumps(e).lower()]
    print(f"🔍 经验库检索 '{keyword}': 找到 {len(filtered)} 条")
    for e in filtered[:5]:
        print(f"\n  • {e.get('task_type', 'unknown')}")
        print(f"    结论: {e.get('conclusion', '')[:80]}...")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1].lower()
    args = sys.argv[2:]
    if cmd == "decide" and args:
        cmd_decide(" ".join(args))
    elif cmd == "bbon" and args:
        cmd_bbon(" ".join(args))
    elif cmd == "engines":
        cmd_engines()
    elif cmd == "health":
        cmd_health()
    elif cmd == "experience" and args:
        cmd_experience(" ".join(args))
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)
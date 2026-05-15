#!/usr/bin/env python3
"""伏羲 CLI 管理工具 — 供 fuxi Agent 通过 bash 调用

所有命令通过 jinlange_bridge 调用伏羲 REST API。
需要 FUXI_API_KEY 环境变量（从 ~/.openclaw/keys/fuxi.env 加载）。

用法:
  python3 fuxi_cli.py memory search <query>
  python3 fuxi_cli.py memory recent [limit]
  python3 fuxi_cli.py memory remember <text> [importance] [tags...]
  python3 fuxi_cli.py system health
  python3 fuxi_cli.py system stats
  python3 fuxi_cli.py engine list
  python3 fuxi_cli.py engine status <name>
  python3 fuxi_cli.py engine run <name>
  python3 fuxi_cli.py engine control <name> <start|stop|pause|resume>
  python3 fuxi_cli.py persona report
  python3 fuxi_cli.py persona speak
  python3 fuxi_cli.py backup create
  python3 fuxi_cli.py backup list
  python3 fuxi_cli.py maintenance decay [--dry-run]
  python3 fuxi_cli.py maintenance purge [--dry-run]
  python3 fuxi_cli.py judge <task_type> <description> <summary>
"""
import json
import os
import sys

# 确保加载 fuxi.env 中的 API key
_env_file = os.path.expanduser("~/.openclaw/keys/fuxi.env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# 添加 fuxi 源码路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def print_json(data):
    if data is None:
        print(json.dumps({"error": "API returned null"}, ensure_ascii=False))
    elif isinstance(data, (dict, list)):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(str(data))


def cmd_memory(args):
    from fuxi_scripts.jinlange_bridge import (
        agent_context,
        agent_recall,
        agent_remember,
        agent_search,
    )

    sub = args[0] if args else "recent"
    agent_id = "fuxi"

    if sub == "search":
        query = " ".join(args[1:])
        result = agent_search(agent_id, query)
    elif sub == "recent":
        limit = int(args[1]) if args[1:2] else 10
        result = agent_recall(agent_id, limit=limit)
    elif sub == "remember":
        if len(args) < 2:
            print_json({"error": "用法: memory remember <text> [importance] [tags...]"})
            return
        text = args[1]
        importance = float(args[2]) if args[2:3] else 0.5
        tags = args[3:] if args[3:] else []
        result = agent_remember(agent_id, text, importance=importance, tags=tags)
    elif sub == "context":
        budget = int(args[1]) if args[1:2] else 500
        result = agent_context(agent_id, budget=budget)
    else:
        result = {"error": f"未知子命令: {sub}"}

    print_json(result)


def cmd_system(args):
    from fuxi_scripts.jinlange_bridge import get_fuxi_stats, get_health_score, get_system_info

    sub = args[0] if args else "health"

    if sub == "health":
        result = get_health_score()
    elif sub == "stats":
        result = get_fuxi_stats()
    elif sub == "info":
        result = get_system_info()
    else:
        result = {"error": f"未知子命令: {sub}"}

    print_json(result)


def cmd_engine(args):
    from fuxi_scripts.jinlange_bridge import (
        control_engine,
        get_engine_detail,
        get_engine_status,
        run_engine,
    )

    sub = args[0] if args else "list"

    if sub == "list":
        result = get_engine_status()
    elif sub == "status":
        if len(args) < 2:
            print_json({"error": "用法: engine status <name>"})
            return
        result = get_engine_detail(args[1])
    elif sub == "run":
        if len(args) < 2:
            print_json({"error": "用法: engine run <name>"})
            return
        result = run_engine(args[1])
    elif sub == "control":
        if len(args) < 3:
            print_json({"error": "用法: engine control <name> <start|stop|pause|resume>"})
            return
        result = control_engine(args[1], args[2])
    else:
        result = {"error": f"未知子命令: {sub}"}

    print_json(result)


def cmd_persona(args):
    sub = args[0] if args else "report"

    if sub == "report":
        from fuxi_scripts.jinlange_bridge import _api
        result = _api("GET", "/api/v2/persona/reports?limit=5")
    elif sub == "speak":
        from fuxi_scripts.jinlange_bridge import _api
        result = _api("POST", "/api/v2/persona/speak")
    elif sub == "state":
        from fuxi_scripts.jinlange_bridge import _api
        result = _api("GET", "/api/v2/persona")
    else:
        result = {"error": f"未知子命令: {sub}"}

    print_json(result)


def cmd_backup(args):
    from fuxi_scripts.jinlange_bridge import create_backup, list_backups

    sub = args[0] if args else "list"

    if sub == "create":
        result = create_backup()
    elif sub == "list":
        result = list_backups()
    else:
        result = {"error": f"未知子命令: {sub}"}

    print_json(result)


def cmd_maintenance(args):
    from fuxi_scripts.jinlange_bridge import trigger_decay, trigger_purge

    sub = args[0] if args else "status"
    dry_run = "--dry-run" in args

    if sub == "decay":
        result = trigger_decay(dry_run=dry_run)
    elif sub == "purge":
        result = trigger_purge(dry_run=dry_run)
    else:
        result = {"error": f"未知子命令: {sub}"}

    print_json(result)


def cmd_judge(args):
    from fuxi_scripts.jinlange_bridge import judge_memory_value

    if len(args) < 3:
        print_json({"error": "用法: judge <task_type> <description> <summary>"})
        return
    result = judge_memory_value(
        task_type=args[0],
        task_description=args[1],
        output_summary=args[2],
        agent_id="fuxi",
    )
    print_json(result)


def cmd_agent(args):
    from fuxi_scripts.jinlange_bridge import get_agent, list_agents

    sub = args[0] if args else "list"

    if sub == "list":
        result = list_agents()
    elif sub == "get":
        if len(args) < 2:
            print_json({"error": "用法: agent get <agent_id>"})
            return
        result = get_agent(args[1])
    else:
        result = {"error": f"未知子命令: {sub}"}

    print_json(result)


COMMANDS = {
    "memory": cmd_memory,
    "system": cmd_system,
    "engine": cmd_engine,
    "persona": cmd_persona,
    "backup": cmd_backup,
    "maintenance": cmd_maintenance,
    "judge": cmd_judge,
    "agent": cmd_agent,
}

USAGE = """伏羲 CLI 管理工具

用法: python3 fuxi_cli.py <命令> [参数...]

命令:
  memory search <query>        搜索全局记忆
  memory recent [limit]        获取最近记忆
  memory remember <text> [importance] [tags...]  写入记忆
  memory context [budget]      获取记忆上下文
  system health                系统健康度
  system stats                 系统统计
  system info                  系统信息
  engine list                  列出所有引擎
  engine status <name>         引擎详情
  engine run <name>            触发引擎运行
  engine control <name> <动作>  控制引擎 (start/stop/pause/resume)
  persona report               报告历史
  persona speak                强制发言
  persona state                人格状态
  backup create                创建备份
  backup list                  列出备份
  maintenance decay [--dry-run]   触发记忆衰减
  maintenance purge [--dry-run]   触发记忆清理
  judge <类型> <描述> <摘要>      判断记忆价值 (A/B/C)
  agent list                   列出所有 Agent
  agent get <id>               Agent 详情
"""

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(USAGE)
        sys.exit(0)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd in COMMANDS:
        COMMANDS[cmd](args)
    else:
        print(f"未知命令: {cmd}")
        print(USAGE)
        sys.exit(1)

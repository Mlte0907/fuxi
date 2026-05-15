#!/usr/bin/env python3
"""伏羲 Instinct CLI - 完整本能生命周期管理工具
基于 ECC Instinct 模型:
- 观察捕获 (observations.jsonl)
- 模式检测 (pattern detection)
- 本能演化 (instinct evolution)
- 聚类到技能 (evolve clustering)
"""
import argparse, json, sys
from datetime import datetime
from pathlib import Path

HOMUNCULUS_DIR = Path.home() / ".claude" / "homunculus"
OBS_DIR = Path.home() / ".claude" / "projects"


def cmd_capture(args):
    obs = {"timestamp": datetime.now().isoformat(), "tool": args.tool or "unknown",
          "prompt": args.prompt or "", "tool_calls": args.tool_calls or [],
          "outcome": args.outcome or "", "project": args.project or "default",
          "project_hash": args.project_hash or hash_project(args.project or "default")}
    obs_file = OBS_DIR / args.project / "instinct" / "observations.jsonl"
    obs_file.parent.mkdir(parents=True, exist_ok=True)
    with open(obs_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(obs, ensure_ascii=False) + "\n")
    print(f"Captured to {obs_file}")


def cmd_list(args):
    instinct_dir = HOMUNCULUS_DIR / "instincts"
    if not instinct_dir.exists():
        print("No instincts found"); return
    for f in sorted(instinct_dir.glob("*.yaml")):
        print(f"  - {f.stem}")


def cmd_evolve(args):
    project = args.project or "default"
    obs_file = OBS_DIR / project / "instinct" / "observations.jsonl"
    if not obs_file.exists():
        print(f"No observations for {project}"); return
    observations = [json.loads(line) for line in open(obs_file)]
    patterns = detect_patterns(observations)
    print(f"Detected {len(patterns)} patterns")
    instinct_dir = HOMUNCULUS_DIR / "instincts"
    instinct_dir.mkdir(parents=True, exist_ok=True)
    for p in patterns:
        instinct_file = instinct_dir / f"{p['id']}.yaml"
        with open(instinct_file, "w") as f:
            f.write(f"---\nid: {p['id']}\ntrigger: {p.get('trigger','')}\n")
            f.write(f"confidence: {p.get('confidence',0.5)}\ndomain: {p.get('domain','general')}\n")
            f.write(f"source: session-observation\nscope: project\n---\n\n## Action\n{p.get('action','')}\n")
        print(f"  Evolved: {p['id']}")


def detect_patterns(observations):
    patterns, tool_counts, cmd_counts = [], {}, {}
    for obs in observations:
        tool = obs.get("tool",""); tool_counts[tool] = tool_counts.get(tool,0) + 1
        if tool == "Bash":
            cmd = obs.get("tool_calls",[{}])[0].get("command","")
            if cmd:
                cn = cmd.split()[0] if cmd else "unknown"
                cmd_counts[cn] = cmd_counts.get(cn,0) + 1
    for tool, count in tool_counts.items():
        if count >= 3:
            patterns.append({"id": f"prefer-{tool.lower()}", "trigger": f"When using {tool}",
                           "confidence": min(0.3+count*0.1,0.9), "domain": "tool-preference",
                           "action": f"Consider using {tool} based on {count}x usage"})
    for cmd, count in cmd_counts.items():
        if count >= 3:
            patterns.append({"id": f"frequent-{cmd.lower()}", "trigger": "When running commands",
                           "confidence": min(0.35+count*0.1,0.85), "domain": "command-habit",
                           "action": f"Command '{cmd}' used {count} times"})
    return patterns


def hash_project(project):
    import hashlib
    return hashlib.sha256(project.encode()).hexdigest()[:12]


def main():
    parser = argparse.ArgumentParser(description="伏羲 Instinct CLI")
    sub = parser.add_subparsers()
    p1 = sub.add_parser("capture", help="捕获观察"); p1.add_argument("--tool"); p1.add_argument("--prompt")
    p1.add_argument("--tool-calls", nargs="*"); p1.add_argument("--outcome"); p1.add_argument("--project", default="default")
    p1.set_defaults(func=cmd_capture)
    p2 = sub.add_parser("list", help="列出本能"); p2.set_defaults(func=cmd_list)
    p3 = sub.add_parser("evolve", help="聚类到本能"); p3.add_argument("--project", default="default"); p3.set_defaults(func=cmd_evolve)
    args = parser.parse_args()
    if hasattr(args, "func"): args.func(args)
    else: parser.print_help()


if __name__ == "__main__": main()

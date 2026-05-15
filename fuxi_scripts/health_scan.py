#!/usr/bin/env python3
"""伏羲引擎批量健康扫描 — 全量巡检 + 错误诊断报告。

用法:
  python3 health_scan.py                    # 全量扫描，输出报告
  python3 health_scan.py --json             # JSON 格式输出
  python3 health_scan.py --alert            # 仅输出有问题的引擎
  python3 health_scan.py --save /tmp/report # 保存报告到文件

配合 cron 定时运行可自动监控引擎状态。
"""
import json
import os
import sys
from datetime import datetime

import requests

FUXI_BASE = os.environ.get("FUXI_BASE_URL", "http://127.0.0.1:19528")
API_KEY = os.environ.get("FUXI_API_KEY", os.environ.get("API_KEY", "jinlange-fuxi-2026"))


def scan() -> dict | None:
    """全量扫描所有引擎健康状态。"""
    headers = {"X-API-Key": API_KEY}
    url = f"{FUXI_BASE}/api/v2/engines/health"
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        return data
    except requests.RequestException as e:
        print(f"❌ 连接 Fuxi API 失败: {e}", file=sys.stderr)
        return None


def check_single(name: str) -> dict | None:
    """查询单个引擎详细状态。"""
    headers = {"X-API-Key": API_KEY}
    url = f"{FUXI_BASE}/api/v2/engines/{name}"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", {})
    except requests.RequestException:
        return None


def generate_report(data: dict) -> str:
    """生成人类可读的健康报告。"""
    lines = []
    lines.append("=" * 50)
    lines.append(f"  伏羲引擎健康扫描报告")
    lines.append(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 50)
    lines.append("")

    lines.append(f"  总计: {data['total']} 个引擎")
    lines.append(f"  运行: {data['running']} / 停止: {data['stopped']}")
    lines.append(f"  错误: {data['total_errors']}")
    lines.append("")

    engines = data.get("engines", [])
    if not engines:
        lines.append("  ⚠️ 未找到引擎")
        return "\n".join(lines)

    with_errors = [e for e in engines if e["health"].get("error_count", 0) > 0]
    stopped = [e for e in engines if not e["running"] and e not in with_errors]
    running_ok = [e for e in engines if e["running"] and e not in with_errors]

    if with_errors:
        lines.append("━" * 50)
        lines.append("  🔴 有错误的引擎:")
        lines.append("━" * 50)
        for e in sorted(with_errors, key=lambda x: -x["health"].get("error_count", 0)):
            h = e["health"]
            lines.append(f"    {e['name']}")
            lines.append(f"      错误数: {h.get('error_count', 0)}")
            lines.append(f"      运行次数: {h.get('run_count', 0)}")
            lines.append(f"      上次运行: {h.get('last_run', 'N/A')}")
            detail = check_single(e["name"])
            if detail and "state" in detail:
                s = detail["state"]
                lines.append(f"      状态: running={s.get('running', '?')}, "
                            f"experimental={s.get('experimental', '?')}")
            lines.append("")

    if stopped:
        lines.append("━" * 50)
        lines.append("  ⏸️  已停止的引擎:")
        lines.append("━" * 50)
        for e in stopped:
            lines.append(f"    {e['name']}")

    if running_ok:
        lines.append("━" * 50)
        lines.append(f"  ✅ 正常运行: {len(running_ok)} 个")
        lines.append("━" * 50)
        for e in running_ok:
            h = e["health"]
            lines.append(f"    {e['name']} (运行 {h.get('run_count', 0)} 次)")

    lines.append("")
    lines.append("=" * 50)
    lines.append(f"  扫描完成: {datetime.now().strftime('%H:%M:%S')}")
    lines.append("=" * 50)

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="伏羲引擎批量健康扫描")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--alert", action="store_true", help="仅输出有问题的引擎")
    parser.add_argument("--save", help="保存报告到文件")
    args = parser.parse_args()

    print("🔍 [HealthScan] 扫描引擎状态...", file=sys.stderr)
    data = scan()

    if not data:
        print("❌ 扫描失败", file=sys.stderr)
        sys.exit(1)

    engines = data.get("engines", [])
    with_errors = [e for e in engines if e["health"].get("error_count", 0) > 0]

    if args.json:
        output = json.dumps(data, ensure_ascii=False, indent=2)
    elif args.alert:
        alert_data = {
            "timestamp": datetime.now().isoformat(),
            "total_errors": data["total_errors"],
            "problem_engines": [
                {"name": e["name"], "error_count": e["health"].get("error_count", 0),
                 "run_count": e["health"].get("run_count", 0)}
                for e in with_errors
            ],
            "stopped_engines": [e["name"] for e in engines if not e["running"]],
        }
        if alert_data["problem_engines"] or alert_data["stopped_engines"]:
            output = json.dumps(alert_data, ensure_ascii=False, indent=2)
        else:
            output = json.dumps({"status": "healthy", "total_errors": 0})
    else:
        output = generate_report(data)

    if args.save:
        path = args.save
        with open(path, "w") as f:
            f.write(output)
        relay_dir = os.path.expanduser("~/.claude/relay_v2")
        if os.path.isdir(relay_dir):
            with open(os.path.join(relay_dir, "health_report.txt"), "w") as f:
                f.write(output)
        print(f"  ✅ 报告已保存: {path}", file=sys.stderr)
        print(f"  ✅ 同步到: {relay_dir}/health_report.txt", file=sys.stderr)

    print(output)


if __name__ == "__main__":
    main()

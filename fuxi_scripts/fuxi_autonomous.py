#!/usr/bin/env python3
"""
伏羲自主判断引擎 - 根据任务类型自动决定调用哪些能力
当任务涉及复杂决策时，建议使用 /bbon 多轨迹决策
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

FUXI_API = "http://localhost:19528"
FUXI_KEY = os.environ.get("FUXI_API_KEY", "jinlange-fuxi-2026")

# 引擎映射场景
ENGINE_SCENARIOS = {
    "memory_recall": {
        "keywords": ["记忆", "之前", "上次", "过去", "历史", "记得", "检索", "查询"],
        "engine": "perception",
        "action": "memory_recall"
    },
    "self_reflection": {
        "keywords": ["反思", "复盘", "回顾", "思考自己", "总结", "成长"],
        "engine": "metacognition",
        "action": "self_reflection"
    },
    "decision_advice": {
        "keywords": ["决策", "决定", "选择", "权衡", "方案", "建议"],
        "engine": "cognitive_loop",
        "action": "decision_advice"
    },
    "skill_learning": {
        "keywords": ["学习", "掌握", "技能", "能力提升", "进化"],
        "engine": "skill_evolution",
        "action": "skill_upgrade"
    },
    "creative_work": {
        "keywords": ["创作", "文案", "运营", "市场", "营销", "自媒体", "内容"],
        "engine": "openclaw",
        "action": "delegate_to_pipi"
    }
}

# 需要 bBoN 决策的关键词
DECISION_KEYWORDS = [
    "重构", "重写", "迁移", "设计方案", "架构",
    "多个", "方案", "选择", "对比", "权衡",
    "分析", "评估", "优化", "改进", "升级",
]

# 复杂任务特征（建议触发 bBoN）
COMPLEX_PATTERNS = [
    "多个文件", "跨模块", "多步骤", "涉及",
    "重构", "迁移", "重写", "设计",
]


def fuxi_api_get(path):
    """GET 请求到 Fuxi API"""
    url = f"{FUXI_API}{path}"
    headers = {"X-API-Key": FUXI_KEY, "Accept": "application/json"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def analyze_task(task_text: str) -> dict:
    """分析任务，决定需要什么能力"""
    text = task_text.lower()

    # 1. 检查引擎场景
    matched_scenarios = []
    for scenario, config in ENGINE_SCENARIOS.items():
        for kw in config["keywords"]:
            if kw in text:
                matched_scenarios.append({
                    "scenario": scenario,
                    "engine": config["engine"],
                    "action": config["action"],
                    "matched_keyword": kw
                })
                break

    # 2. bBoN 复杂度分析
    decision_hits = sum(1 for kw in DECISION_KEYWORDS if kw in text)
    complex_hits = sum(1 for p in COMPLEX_PATTERNS if p in text)
    complexity = min(10, decision_hits * 2 + complex_hits * 2)
    needs_bbon = complexity >= 6 or decision_hits >= 2

    # 3. 记忆检索检查
    needs_memory = "记忆" in text or "记得" in text or "之前" in text

    # 4. 检查 Fuxi 引擎状态
    engine_status = {}
    try:
        result = fuxi_api_get("/api/v2/engines/health")
        if "error" not in result:
            for e in result.get("data", {}).get("engines", []):
                engine_status[e.get("name")] = e.get("running", False)
    except Exception:
        pass

    return {
        "complexity": complexity,
        "decision_hits": decision_hits,
        "complex_hits": complex_hits,
        "needs_bbon": needs_bbon,
        "needs_memory": needs_memory,
        "matched_scenarios": matched_scenarios,
        "engine_status": engine_status,
    }


def format_recommendation(result: dict, task: str) -> str:
    """格式化输出推荐"""
    outputs = []

    # bBoN 建议
    if result["needs_bbon"]:
        outputs.append(f"\033[93m💡 复杂任务检测（复杂度 {result['complexity']}/10）: 建议使用 /bbon 进行多轨迹决策\033[0m")

    # 引擎场景匹配
    if result["matched_scenarios"]:
        outputs.append("\033[96m🎯 引擎场景匹配:\033[0m")
        for m in result["matched_scenarios"]:
            outputs.append(f"   • {m['scenario']} → {m['engine']} ({m['action']})")

    # 记忆检索建议
    if result["needs_memory"]:
        outputs.append(f"\033[96m🧠 记忆检索建议: 调用 fuxi_tool.py decide \"{task[:30]}...\"\033[0m")

    # 引擎状态
    if result["engine_status"]:
        running = [k for k, v in result["engine_status"].items() if v]
        if running:
            outputs.append(f"\033[92m✅ 运行中引擎: {', '.join(running[:5])}...\033[0m")

    return "\n".join(outputs) if outputs else ""


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: fuxi_autonomous.py <任务描述>")
        sys.exit(0)

    task_text = sys.argv[1]
    result = analyze_task(task_text)

    recommendation = format_recommendation(result, task_text)
    if recommendation:
        print(recommendation)

    # 输出 JSON 格式结果供调用者使用
    if os.environ.get("FUXI_AUTONOMOUS_JSON"):
        print(json.dumps(result, ensure_ascii=False))

    sys.exit(0)

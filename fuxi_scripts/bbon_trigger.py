#!/usr/bin/env python3
"""
bBoN 自动触发脚本
当任务涉及复杂决策时，建议使用 /bbon 多轨迹决策
"""
import sys
import json

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

def analyze_task(task_text: str) -> dict:
    """分析任务，决定是否需要 bBoN"""
    text = task_text.lower()
    
    # 命中决策关键词
    decision_hits = sum(1 for kw in DECISION_KEYWORDS if kw in text)
    
    # 命中复杂任务模式
    complex_hits = sum(1 for p in COMPLEX_PATTERNS if p in text)
    
    # 计算复杂度评分 (1-10)
    complexity = min(10, decision_hits * 2 + complex_hits * 2)
    
    needs_bbon = complexity >= 6 or decision_hits >= 2
    
    return {
        "complexity": complexity,
        "decision_hits": decision_hits,
        "complex_hits": complex_hits,
        "needs_bbon": needs_bbon,
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(0)
    
    task_text = sys.argv[1]
    result = analyze_task(task_text)
    
    if result["needs_bbon"]:
        print(f"\033[93m💡 复杂任务检测（复杂度 {result['complexity']}/10）: 建议使用 /bbon 进行多轨迹决策\033[0m")
    
    sys.exit(0)

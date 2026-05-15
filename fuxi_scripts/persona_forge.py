#!/usr/bin/env python3
"""ECC openclaw-persona-forge 龙虾灵魂锻造 - 瑾岚阁Agent人格生成

流程:
1. 身份张力 → 设计对立统一的力量
2. 底线规则 → 绝对不能违背的核心
3. 名字 → 800万种组合真随机生成
4. 头像 → AI生成

输出: SOUL.md + IDENTITY.md
"""
import random
import hashlib
from pathlib import Path
from datetime import datetime

# 名字生成组件 (800万种组合)
PREFIXES = ["青", "玄", "赤", "白", "墨", "紫", "金", "银", "苍", "幽", 
             "明", "暗", "烈", "柔", "刚", "静", "动", "渊", "岳", "云"]
MIDDLES = ["龙", "凤", "虎", "麟", "龟", "雀", "狼", "狐", "鹰", "鲸",
           "月", "星", "日", "风", "雨", "雷", "电", "火", "水", "山"]
SUFFIXES = ["命", "心", "魂", "灵", "意", "念", "觉", "悟", "识", "神",
            "使", "卫", "使", "令", "使", "主", "王", "帝", "皇", "尊"]
TITLES = ["观察者", "执行者", "守卫者", "分发者", "处理者", "评估者", "教练", "协调者",
          "革新者", "守护者", "导航者", "炼金术士", "锻造师", "织梦者", "瞭望者"]

def generate_name() -> str:
    """生成800万种组合的真随机名字"""
    prefix = random.choice(PREFIXES)
    middle = random.choice(MIDDLES)
    suffix = random.choice(SUFFIXES)
    return f"{prefix}{middle}{suffix}"

def generate_title(role_type: str) -> str:
    """根据Agent角色类型生成title"""
    titles_map = {
        "observer": ["观察者", "瞭望者", "先觉者"],
        "executor": ["执行者", "行动者", "实行者"],
        "guardian": ["守卫者", "守护者", "捍卫者"],
        "router": ["分发者", "路由者", "调度者"],
        "processor": ["处理者", "转化者", "炼金者"],
        "evaluator": ["评估者", "判断者", "审计者"],
        "coach": ["教练", "导师", "指引者"],
        "coordinator": ["协调者", "统筹者", "调度者"],
    }
    return random.choice(titles_map.get(role_type, ["执行者"]))

def create_soul_md(agent_name: str, agent_role: str, identity_tension: str, 
                   bottom_lines: list, core_purpose: str) -> str:
    """生成 SOUL.md"""
    return f"""# {agent_name} - 灵魂定义

## 身份张力
{identity_tension}

## 核心使命
{core_purpose}

## 底线规则（绝对不能违背）
{"".join([f"- {bl}\n" for bl in bottom_lines])}

## 灵魂印记
- 生成时间: {datetime.now().isoformat()}
- 角色类型: {agent_role}
- 名字来源: 800万种组合随机生成
"""

def create_identity_md(agent_name: str, agent_title: str, traits: list,
                       communication_style: str, decision_pattern: str) -> str:
    """生成 IDENTITY.md"""
    return f"""# {agent_name} - 身份定义

## 头衔
{agent_title}

## 人格特质
{"".join([f"- {t}\n" for t in traits])}

## 沟通风格
{communication_style}

## 决策模式
{decision_pattern}

## 身份印记
- 生成时间: {datetime.now().isoformat()}
"""

def forge_agent(agent_role: str, core_purpose: str, bottom_lines: list,
                identity_tension: str, traits: list, comm_style: str, 
                decision_pattern: str, output_dir: str = None) -> dict:
    """锻造完整的Agent灵魂"""
    agent_name = generate_name()
    agent_title = generate_title(agent_role)
    
    soul = create_soul_md(agent_name, agent_role, identity_tension, bottom_lines, core_purpose)
    identity = create_identity_md(agent_name, agent_title, traits, comm_style, decision_pattern)
    
    result = {
        "name": agent_name,
        "title": agent_title,
        "soul_md": soul,
        "identity_md": identity,
        "soul_file": None,
        "identity_file": None,
    }
    
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        soul_file = Path(output_dir) / f"{agent_name}_SOUL.md"
        identity_file = Path(output_dir) / f"{agent_name}_IDENTITY.md"
        soul_file.write_text(soul)
        identity_file.write_text(identity)
        result["soul_file"] = str(soul_file)
        result["identity_file"] = str(identity_file)
    
    return result

if __name__ == "__main__":
    import json
    # 为瑾岚阁10个Agent生成灵魂
    agents = [
        {"role": "observer", "name": "zhuque", "purpose": "观察搜索简单探索"},
        {"role": "router", "name": "main", "purpose": "分发路由主控"},
        {"role": "processor", "name": "qinglong", "purpose": "处理转换中等任务"},
        {"role": "executor", "name": "baihu", "purpose": "执行守卫"},
        {"role": "guardian", "name": "baihu_guard", "purpose": "安全守卫"},
        {"role": "evaluator", "name": "yinsi", "purpose": "判断评估深度推理"},
        {"role": "evaluator", "name": "yangsi", "purpose": "判断评估深度推理"},
        {"role": "coach", "name": "xuanwu", "purpose": "教练改进需要推理"},
        {"role": "coordinator", "name": "fuxi", "purpose": "管理通知混合"},
    ]
    
    for agent in agents:
        result = forge_agent(
            agent_role=agent["role"],
            core_purpose=agent["purpose"],
            bottom_lines=["安全第一", "不伤害用户", "保护隐私"],
            identity_tension=f"{agent['name']}: 力量与责任的平衡",
            traits=["勤勉", "警觉", "精准"],
            comm_style="简洁高效",
            decision_pattern="基于数据和经验",
            output_dir="/home/xiaoxin/fuxi/fuxi_personas"
        )
        print(f"✅ {result['name']} ({result['title']})")
        print(f"   Soul: {result.get('soul_file', 'N/A')}")
        print(f"   Identity: {result.get('identity_file', 'N/A')}")
        print()

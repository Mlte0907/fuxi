#!/usr/bin/env python3
"""瑾岚阁 ↔ 伏羲 桥接模块

在瑾岚阁 server.py 中导入此模块即可为 Agent 提供完整的伏羲能力。
每个瑾岚阁 Agent 可以通过伏羲 API 读写记忆、搜索上下文、
查询经验库、控制引擎、管理 Agent 视角、触发维护操作等。

环境变量:
    FUXI_BASE_URL  伏羲服务地址 (默认 http://127.0.0.1:19528)
    FUXI_API_KEY   伏羲 API 密钥 (必须从环境变量或 fuxi.env 读取)
"""
import logging
import os
from typing import List, Optional

import requests

logger = logging.getLogger("jinlange.fuxi")

FUXI_BASE = os.environ.get("FUXI_BASE_URL", "http://127.0.0.1:19528")
FUXI_KEY = os.environ.get("FUXI_API_KEY")


def _api(method, path, data=None, timeout=10):
    """调用伏羲 REST API 的统一入口"""
    if not FUXI_KEY:
        logger.error("FUXI_API_KEY environment variable is not set")
        return None
    url = f"{FUXI_BASE}{path}"
    headers = {"X-API-Key": FUXI_KEY, "Content-Type": "application/json"}
    try:
        resp = requests.request(method, url, json=data, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("data")
    except Exception as e:
        logger.warning(f"FuXi API error [{method} {path}]: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# 一、Agent 记忆接口
# ═══════════════════════════════════════════════════════════════

def agent_remember(agent_id: str, text: str, importance: float = 0.5,
                   tags: Optional[List[str]] = None, perspective: str = ""):
    """Agent 写入一条记忆到伏羲

    Args:
        agent_id: Agent 标识
        text: 记忆文本
        importance: 重要度 0-1
        tags: 标签列表
        perspective: Agent 视角（差异化记忆视图）
    """
    drawer = f"{agent_id}_view"
    return _api("POST", "/api/v2/memories", {
        "text": text, "drawer_id": drawer, "importance": importance,
        "source": f"agent:{agent_id}", "created_by": agent_id,
        "tags": tags or [], "confidence": 0.85,
    })


def agent_recall(agent_id: str, query: Optional[str] = None, limit: int = 10):
    """Agent 召回自己的记忆"""
    drawer = f"{agent_id}_view"
    path = f"/api/v2/memories?drawer_id={drawer}&limit={limit}&sort_by=created_at"
    if query:
        path += f"&query={query}"
    return _api("GET", path)


def agent_search(agent_id: str, q: str, limit: int = 20):
    """Agent 在全局记忆库中搜索"""
    return _api("GET", f"/api/v2/memories/search?q={q}&limit={limit}")


def agent_context(agent_id: str, budget: Optional[int] = None):
    """获取给 Agent 用的记忆上下文（用于注入对话）"""
    return _api("GET", f"/api/v2/memories/context?drawer_id={agent_id}_view&budget={budget or 500}")


def agent_dialogue_context(agent_id: str, budget: int = 500):
    """为 Agent 对话注入最新记忆上下文（格式化字符串）"""
    ctx = agent_context(agent_id, budget=budget)
    if not ctx:
        return ""
    if isinstance(ctx, list):
        parts = [f"[记忆] {item.get('raw_text', '')[:120]}" for item in ctx[:5] if item.get('raw_text')]
        return "\n".join(parts)
    if isinstance(ctx, dict):
        items = ctx.get("items", [])
        parts = [f"[记忆] {item.get('raw_text', '')[:120]}" for item in items[:5] if item.get('raw_text')]
        return "\n".join(parts)
    return str(ctx)[:500]


def agent_search_similar(agent_id: str, text: str, limit: int = 5):
    """语义相似记忆搜索"""
    results = agent_search(agent_id, text, limit=limit)
    if not results:
        return []
    if isinstance(results, dict):
        return results.get("results", results.get("items", []))[:limit]
    return results[:limit] if isinstance(results, list) else []


def broadcast_memory(from_agent: str, message: str, importance: float = 0.5):
    """向所有 Agent 广播一条记忆"""
    return _api("POST", "/api/v2/collaboration/broadcast", {
        "from_agent": from_agent, "message": message, "importance": importance,
    })


# ═══════════════════════════════════════════════════════════════
# 二、Agent 视角管理
# ═══════════════════════════════════════════════════════════════

def set_agent_view(agent_id: str, drawer_id: str = "", item_ids: Optional[List[str]] = None,
                   perspective: str = ""):
    """设置 Agent 的记忆视角

    Args:
        agent_id: Agent 标识
        drawer_id: 抽屉 ID
        item_ids: 绑定的记忆 ID 列表
        perspective: 视角描述（如 "analytical", "creative"）
    """
    body = {"drawer_id": drawer_id, "perspective": perspective}
    if item_ids:
        body["item_ids"] = item_ids
    return _api("PUT", f"/api/v2/agents/{agent_id}/view", data=body)


def get_agent_view(agent_id: str, limit: int = 20):
    """获取 Agent 的记忆视角"""
    return _api("GET", f"/api/v2/agents/{agent_id}/view?limit={limit}")


# ═══════════════════════════════════════════════════════════════
# 三、经验银行
# ═══════════════════════════════════════════════════════════════

def query_experiences(task_type: str = "", limit: int = 10):
    """查询经验库

    Args:
        task_type: 任务类型过滤（模糊匹配）
        limit: 返回条数
    """
    path = f"/api/v2/admin/experiences?limit={limit}"
    if task_type:
        path += f"&task_type={task_type}"
    return _api("GET", path)


def get_experience(exp_id: str):
    """获取单条经验详情"""
    return _api("GET", f"/api/v2/admin/experiences/{exp_id}")


# ═══════════════════════════════════════════════════════════════
# 四、引擎控制
# ═══════════════════════════════════════════════════════════════

def get_engine_status():
    """获取所有引擎状态"""
    return _api("GET", "/api/v2/engines")


def get_engine_detail(engine_name: str):
    """获取单个引擎详情"""
    return _api("GET", f"/api/v2/engines/{engine_name}")


def control_engine(engine_name: str, action: str):
    """控制引擎启停

    Args:
        engine_name: 引擎名称
        action: start | stop | pause | resume
    """
    return _api("POST", f"/api/v2/engines/{engine_name}/control",
                data={"action": action})


def run_engine(engine_name: str):
    """手动触发引擎执行一次"""
    return _api("POST", f"/api/v2/engines/{engine_name}/run")


def run_all_engines(include_experimental: bool = False):
    """批量运行所有引擎"""
    return _api("POST", f"/api/v2/engines/run_all?include_experimental={include_experimental}")


# ═══════════════════════════════════════════════════════════════
# 五、Agent 管理
# ═══════════════════════════════════════════════════════════════

def list_agents():
    """列出所有 Agent 及其 ACL 信息"""
    return _api("GET", "/api/v2/agents")


def get_agent(agent_id: str):
    """获取单个 Agent 详情"""
    return _api("GET", f"/api/v2/agents/{agent_id}")


# ═══════════════════════════════════════════════════════════════
# 六、协作接口
# ═══════════════════════════════════════════════════════════════

def collaboration_pipeline(chain: List[str], message: str, importance: float = 0.7):
    """执行多 Agent 流水线

    Args:
        chain: Agent 链，如 ["qinglong", "zhuque", "xuanwu"]
        message: 要处理的消息
        importance: 重要度
    """
    return _api("POST", "/api/v2/collaboration/pipeline", data={
        "chain": chain, "message": message, "importance": importance,
    })


def collaboration_negotiate(agents: List[str], topic: str):
    """多 Agent 协商

    Args:
        agents: 参与协商的 Agent 列表
        topic: 协商主题
    """
    return _api("POST", "/api/v2/collaboration/negotiate", data={
        "agents": agents, "topic": topic,
    })


# ═══════════════════════════════════════════════════════════════
# 七、系统维护
# ═══════════════════════════════════════════════════════════════

def get_fuxi_stats():
    """获取伏羲系统统计"""
    return _api("GET", "/api/v2/admin/stats")


def get_health_score():
    """获取健康度评分"""
    return _api("GET", "/api/v2/engines/soul")


def trigger_decay(dry_run: bool = False):
    """触发记忆衰减"""
    return _api("POST", f"/api/v2/memories/decay?dry_run={dry_run}")


def trigger_purge(dry_run: bool = True):
    """触发低分记忆清理"""
    return _api("POST", f"/api/v2/memories/purge?dry_run={dry_run}")


def create_backup():
    """创建数据库备份"""
    return _api("POST", "/api/v2/admin/backup")


def list_backups():
    """列出所有备份"""
    return _api("GET", "/api/v2/admin/backups")


def restore_backup(filename: str):
    """从备份恢复（含完整性校验）"""
    return _api("POST", f"/api/v2/admin/restore/{filename}")


def export_memories(drawer_id: Optional[str] = None, format: str = "json"):
    """导出记忆"""
    path = f"/api/v2/memories/export?format={format}"
    if drawer_id:
        path += f"&drawer_id={drawer_id}"
    return _api("GET", path)


def query_events(event_type: Optional[str] = None, source: Optional[str] = None,
                 limit: int = 100):
    """查询事件日志"""
    path = f"/api/v2/memories/events?limit={limit}"
    if event_type:
        path += f"&event_type={event_type}"
    if source:
        path += f"&source={source}"
    return _api("GET", path)


def get_system_info():
    """获取系统信息"""
    return _api("GET", "/api/v2/system/info")


# ═══════════════════════════════════════════════════════════════
# 八、OpenClaw 网关集成
# ═══════════════════════════════════════════════════════════════

def openclaw_health():
    """检查 OpenClaw 网关健康状态"""
    return _api("GET", "/api/v2/agents/openclaw/health")


def openclaw_list_agents():
    """列出 OpenClaw Agent"""
    return _api("GET", "/api/v2/agents/openclaw/agents")


def openclaw_invoke(agent_id: str, message: str, model: Optional[str] = None):
    """调用 OpenClaw Agent"""
    body = {"message": message}
    if model:
        body["model"] = model
    return _api("POST", f"/api/v2/agents/openclaw/{agent_id}/invoke", data=body)


# ═══════════════════════════════════════════════════════════════
# 九、记忆价值判断 (Nudge)
# ═══════════════════════════════════════════════════════════════

def judge_memory_value(
    task_type: str = "",
    task_description: str = "",
    output_summary: str = "",
    agent_id: str = "",
    auto_apply: bool = False,
    raw_text: str = "",
    drawer_override: Optional[str] = None,
):
    """调用 LLM 判断任务产出是否值得写入长期记忆。返回 A/B/C 分类。"""
    body = {
        "task_type": task_type,
        "task_description": task_description,
        "output_summary": output_summary,
        "agent_id": agent_id,
        "auto_apply": auto_apply,
        "raw_text": raw_text,
    }
    if drawer_override:
        body["drawer_override"] = drawer_override
    return _api("POST", "/api/v2/memory/judge", data=body)

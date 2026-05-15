"""伏羲 v1.0 — DialogueEngine 双向对话"""
import json
import logging
import time
from datetime import datetime

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.dialogue")

# 问题类型 → 瑾岚阁 Agent 映射
AGENT_ROUTING = {
    "question": "qinglong",       # 反思问题 → 青龙分析
    "stale_important": "zhuque",  # 过期重要记忆 → 朱雀执行
    "trending_drawer": "qinglong", # 趋势分析 → 青龙
    "knowledge_gap": "qinglong",  # 知识空白 → 青龙
    "tag_diversity": "xuanwu",    # 分类整理 → 玄武归档
    "health_concern": "main",     # 健康问题 → 皮皮主控
    "emotion_shift": "baihu",     # 情绪波动 → 白虎审查
    "proactive": "qinglong",      # 主动洞察 → 青龙分析
}


@register_engine("dialogue", experimental=False)
class DialogueEngine(CognitiveEngine):
    """双向对话 — 主动向瑾岚阁 Agent 提问并消化回复"""
    name = "dialogue"
    priority = 5
    interval = 300  # 5 分钟
    experimental = False

    def _get_subscriptions(self):
        return {
            "wm.item_pushed": self._on_event,
            "proactive.insight": self._on_event,
        }

    def run(self) -> dict:
        pool = get_pool()
        now = time.time()

        # 防止重复调用：最近一次对话未完成时跳过
        last_call = self._state.metadata.get("last_call_ts", 0)
        if (now - last_call) < 60:
            return {"status": "skipped", "reason": "cooldown"}

        # 收集待问的问题
        question = self._pick_question(pool)
        if not question:
            return {"status": "idle", "reason": "no questions to ask"}

        target_agent = self._route_agent(question)
        qtype = question.get("type", "question")

        # 自动发现匹配的技能并注入上下文
        skill_context = ""
        try:
            from fuxi.skill_market.integration import inject_skill_context
            skill_context = inject_skill_context(
                task_type=qtype,
                keywords=[qtype, target_agent],
                agent_id=target_agent,
            )
        except Exception:
            pass

        # 查询 experience_bank 中类似对话的历史经验
        exp_context = ""
        try:
            exp_rows = pool.fetchall(
                "SELECT task_type, conclusion, outcome FROM experience_bank "
                "WHERE task_type LIKE ? OR outcome = 'success' "
                "ORDER BY created_at DESC LIMIT 3",
                (f"%{question.get('type', 'question')}%",)
            )
            if exp_rows:
                exp_snippets = [f"[{r['task_type']}]: {r.get('conclusion', '')[:80]}" for r in exp_rows]
                exp_context = " | 历史经验: " + "; ".join(exp_snippets)
        except Exception:
            pass

        # 查询模型路由
        try:
            from fuxi.agent.model_router import route_model
            model = route_model(task_type=qtype, agent_id=target_agent)
        except Exception:
            model = None

        # 召回目标 Agent 的相关记忆作为上下文
        recall_context_str = ""
        try:
            from fuxi.memory.retrieval import recall_context
            recall_items = recall_context(drawer_id=f"{target_agent}_view", budget=5)
            if recall_items:
                snippets = [f"[{r.get('importance','?'):.1f}] {r.get('raw_text','')[:100]}" for r in recall_items]
                recall_context_str = "\n相关记忆:\n" + "\n".join(snippets)
        except Exception:
            pass

        # 注入共享记忆（shared_memories）
        shared_context = ""
        try:
            from fuxi.agent.perspective import PerspectiveManager
            shared_items = PerspectiveManager().get_shared_memories(target_agent, limit=5)
            if shared_items:
                shared_snippets = [f"[来自 {s['from_agent']}] {s['raw_text'][:100]}" for s in shared_items]
                shared_context = "\n共享记忆:\n" + "\n".join(shared_snippets)
        except Exception:
            pass

        # 发起对话
        self._state.metadata["last_call_ts"] = now
        try:
            from fuxi.agent.integration import OpenClawAdapter
            adapter = OpenClawAdapter()
            response = adapter.call_agent(
                agent_id=target_agent,
                message=question["content"] + exp_context + skill_context + recall_context_str + shared_context,
                model=model,
            )
        except Exception as e:
            logger.warning(f"Dialogue call to {target_agent} failed: {e}")
            return {"status": "error", "error": str(e), "target": target_agent}

        if not response or "error" in response:
            error_msg = (response or {}).get("error", "no response")
            logger.debug(f"Dialogue with {target_agent} returned error: {error_msg}")
            return {"status": "error", "error": error_msg, "target": target_agent}

        # 将回复写入记忆
        reply_text = self._extract_reply(response)
        if reply_text:
            try:
                from fuxi.memory.ingestion import remember
                remember(
                    raw_text=f"[对话] 向{target_agent}提问: {question['content'][:100]} → 回复: {reply_text[:300]}",
                    drawer_id="longterm",
                    importance=0.4,
                    source="self",
                    confidence=0.7,
                    created_by="dialogue",
                    tags=["对话", f"agent:{target_agent}", "dialogue"],
                )
            except Exception as e:
                logger.debug(f"Dialogue memory write failed: {e}")

        state = {
            "question": question["content"][:150],
            "target_agent": target_agent,
            "reply_preview": reply_text[:200] if reply_text else "(empty)",
            "timestamp": datetime.now().isoformat(),
        }

        get_event_bus().publish(Event(
            type="dialogue.completed",
            data={"target": target_agent, "question_type": question.get("type", "?")},
            priority=EventPriority.NORMAL,
            source="engine:dialogue",
        ))

        self._state.metadata["last_dialogue"] = state
        return state

    def _pick_question(self, pool) -> dict | None:
        """选择最有价值的问题去问"""
        pending = self._pop_pending_events()

        # 从 pending 事件中提取问题
        for evt in pending:
            if evt["type"] == "proactive.insight":
                return {
                    "type": evt["data"].get("type", "proactive"),
                    "content": evt["data"].get("message", str(evt["data"])),
                }
            if evt["type"] == "wm.item_pushed":
                data = evt["data"]
                src = data.get("source", "")
                if src in ("engine:reflection", "engine:curiosity"):
                    return {
                        "type": "question" if "reflection" in src else "knowledge_gap",
                        "content": f"请分析这条观察: {data.get('id', '?')}",
                    }

        # 从 WM 中找高紧迫项
        from fuxi.kernel.working_memory import get_working_memory
        wm = get_working_memory()
        for item in wm.slots:
            if item.urgency > 0.5 and "engine:" in item.source:
                return {
                    "type": item.source.replace("engine:", ""),
                    "content": item.content,
                }

        # 从 engine_states 找 reflection 产出的最新问题
        row = pool.fetchone(
            "SELECT state_json FROM engine_states WHERE engine_name='reflection' "
            "ORDER BY updated_at DESC LIMIT 1"
        )
        if row:
            try:
                data = json.loads(row["state_json"])
                results = data.get("results", {})
                actions = results.get("actions", [])
                if actions:
                    action = actions[0]
                    return {
                        "type": action.get("type", "question"),
                        "content": f"[反思问题] {action.get('detail', action.get('type', ''))}",
                    }
            except (json.JSONDecodeError, KeyError):
                pass

        return None

    def _route_agent(self, question: dict) -> str:
        qtype = question.get("type", "question")
        return AGENT_ROUTING.get(qtype, "main")

    def _extract_reply(self, response: dict) -> str:
        """从 OpenClaw 响应中提取文本"""
        if not response:
            return ""
        # 尝试多种响应格式
        for key in ("reply", "response", "text", "content", "message", "data"):
            if key in response:
                val = response[key]
                if isinstance(val, str):
                    return val
                if isinstance(val, dict):
                    return str(val)[:500]
        return str(response)[:500]

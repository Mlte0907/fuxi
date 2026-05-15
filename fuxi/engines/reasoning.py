"""伏羲 v1.0 — ReasoningEngine 推理链"""
import json
import logging
from datetime import datetime

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.reasoning")

# 问题分解规则：按问题类型拆分为子问题
DECOMPOSE_RULES = {
    "疑问": ["已知什么?", "缺失什么?", "从哪里可以找到答案?"],
    "建议": ["当前状态是什么?", "期望目标是什么?", "可能的步骤有哪些?"],
    "提醒": ["为什么需要关注?", "影响范围是什么?", "建议采取什么行动?"],
    "knowledge_gap": ["目前已有哪些相关信息?", "需要补充什么知识?", "这个空白的优先级有多高?"],
    "question": ["问题的核心是什么?", "有哪些相关记忆?", "有什么历史经验可以借鉴?"],
    "stale_important": ["这个记忆为什么重要?", "它和其他记忆有什么关联?", "现在应该怎么处理?"],
    "trending_drawer": ["什么导致了趋势?", "这个趋势会持续么?", "应该采取什么行动?"],
    "tag_diversity": ["当前有哪些标签?", "缺少哪些维度的分类?", "如何系统性地扩展标签?"],
    "health_concern": ["健康度下降的具体指标?", "可能的原因有哪些?", "应该优先修复什么?"],
}


@register_engine("reasoning", experimental=False)
class ReasoningEngine(CognitiveEngine):
    """推理链 — 分解问题、查询经验、综合推理、得出结论"""
    name = "reasoning"
    priority = 6
    interval = 600  # 10 分钟
    experimental = False

    def _get_subscriptions(self):
        return {"wm.item_pushed": self._on_event}

    def run(self) -> dict:
        pool = get_pool()
        pending = self._pop_pending_events()

        # 收集待推理的问题
        questions = self._collect_questions(pool, pending)
        if not questions:
            return {"status": "idle", "reason": "no questions to reason about"}

        results = []
        for q in questions[:2]:  # 每次最多推理 2 个问题
            result = self._reason(q, pool)
            results.append(result)

        state = {
            "questions_processed": len(results),
            "results": results,
            "timestamp": datetime.now().isoformat(),
        }

        # 持久化
        with pool.connection() as c:
            c.execute(
                "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
                "VALUES (?,?,?)",
                ("reasoning", json.dumps(state, ensure_ascii=False), datetime.now().isoformat())
            )

        self._state.metadata["last_reasoning"] = state
        return state

    def _collect_questions(self, pool, pending: list) -> list:
        """收集待推理的问题"""
        questions = []

        # 从 pending 事件中提取 WM 推送（reflection/proactive/curiosity 来源）
        for evt in pending:
            data = evt.get("data", {})
            src = evt.get("source", "")
            if any(s in src for s in ("reflection", "proactive", "curiosity")):
                questions.append({
                    "type": src.replace("engine:", ""),
                    "content": data.get("id", data.get("content", "")),
                })

        # 从 engine_states 读取 reflection 的最新产出
        row = pool.fetchone(
            "SELECT state_json FROM engine_states WHERE engine_name='reflection' "
            "ORDER BY updated_at DESC LIMIT 1"
        )
        if row:
            try:
                data = json.loads(row["state_json"])
                actions = data.get("results", {}).get("actions", [])
                for action in actions[:2]:
                    questions.append({
                        "type": action.get("type", "question"),
                        "content": action.get("detail", action.get("type", "")),
                    })
            except (json.JSONDecodeError, KeyError):
                pass

        # 从 proactive 读取最新洞察
        row = pool.fetchone(
            "SELECT state_json FROM engine_states WHERE engine_name='proactive' "
            "ORDER BY updated_at DESC LIMIT 1"
        )
        if row:
            try:
                data = json.loads(row["state_json"])
                for insight in data.get("insights", [])[:2]:
                    questions.append({
                        "type": insight.get("type", "insight"),
                        "content": insight.get("message", ""),
                    })
            except (json.JSONDecodeError, KeyError):
                pass

        # 去重（按 content 去重）
        seen = set()
        unique = []
        for q in questions:
            key = q["content"][:80]
            if key not in seen:
                seen.add(key)
                unique.append(q)
        return unique

    def _reason(self, question: dict, pool) -> dict:
        """对一个问题进行推理"""
        qtype = question.get("type", "question")
        content = question.get("content", "")
        logger.info(f"Reasoning about [{qtype}]: {content[:80]}")

        # 1. 分解问题
        sub_questions = DECOMPOSE_RULES.get(qtype, DECOMPOSE_RULES["question"])

        # 2. 查询 experience_bank 中的相关经验
        experiences = self._query_experiences(qtype, pool)

        # 3. 查询相关记忆
        related = self._query_related_memories(content, pool)

        # 4. 综合形成结论
        conclusion = self._synthesize(content, qtype, sub_questions, experiences, related)

        # 5. 写入 longterm 记忆
        try:
            from fuxi.memory.ingestion import remember
            remember(
                raw_text=f"[推理] 问题: {content[:100]} → 结论: {conclusion[:300]}",
                drawer_id="longterm",
                importance=0.5,
                source="self",
                confidence=0.6,
                created_by="reasoning",
                tags=["推理", qtype, "reasoning"],
                facts=json.dumps({
                    "question_type": qtype,
                    "sub_questions": sub_questions,
                    "experiences_found": len(experiences),
                    "related_memories": len(related),
                }, ensure_ascii=False),
            )
        except Exception as e:
            logger.debug(f"Reasoning memory write failed: {e}")

        # 6. 推入工作记忆
        from fuxi.kernel.working_memory import WMItem, get_working_memory
        get_working_memory().push(WMItem(
            id=f"reasoning:{qtype}:{datetime.now().strftime('%H%M%S')}",
            content=f"[推理结论] {conclusion[:150]}",
            source="engine:reasoning",
            emotional_valence=0.1,
            urgency=0.5,
            tokens=30,
        ))

        # 7. 发布事件
        get_event_bus().publish(Event(
            type="reasoning.conclusion",
            data={"question_type": qtype, "conclusion_preview": conclusion[:100]},
            priority=EventPriority.NORMAL,
            source="engine:reasoning",
        ))

        return {
            "question": content[:100],
            "type": qtype,
            "sub_questions": sub_questions,
            "experiences_used": len(experiences),
            "related_count": len(related),
            "conclusion": conclusion[:200],
        }

    def _query_experiences(self, qtype: str, pool) -> list:
        """查询经验库中相关经验"""
        try:
            rows = pool.fetchall(
                "SELECT task_type, reasoning_summary, conclusion, outcome "
                "FROM experience_bank WHERE task_type LIKE ? "
                "ORDER BY created_at DESC LIMIT 5",
                (f"%{qtype}%",)
            )
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _query_related_memories(self, content: str, pool) -> list:
        """查询相关记忆"""
        try:
            # 提取关键词
            keywords = [w for w in content[:100].split() if len(w) >= 2][:3]
            if not keywords:
                keywords = [content[:20]]
            clauses = " OR ".join(["raw_text LIKE ?" for _ in keywords])
            params = [f"%{kw}%" for kw in keywords]
            rows = pool.fetchall(
                f"SELECT SUBSTR(raw_text,1,100) AS preview, importance "
                f"FROM items WHERE archived=0 AND ({clauses}) "
                f"ORDER BY importance DESC LIMIT 5",
                params,
            )
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _synthesize(self, content: str, qtype: str, sub_questions: list,
                    experiences: list, related: list) -> str:
        """综合子问题、经验和相关记忆，生成结论

        优先尝试通过 OpenClaw Gateway 调用 LLM 做真正推理，
        LLM 不可用时回退到模板化结论。

        DEAD-005 备注: _synthesize 和 _template_fallback 目前是主从关系
        (主: LLM推理, 从: 模板回退)，不是并列双套。后续可考虑将模板
        改为可配置的推理链，但需保持 LLM 优先 + 回退保障的结构。
        """
        # 尝试 LLM 推理
        try:
            from fuxi.agent.integration import OpenClawAdapter
            adapter = OpenClawAdapter()
            prompt = self._build_reasoning_prompt(content, qtype, sub_questions, experiences, related)
            result = adapter.call_agent("qinglong", prompt)
            if result and "reply" in result:
                reply = result.get("reply", "")
                if reply and len(reply) > 10:
                    logger.info(f"LLM reasoning result: {reply[:100]}")
                    return reply[:300]
        except Exception as e:
            logger.debug(f"LLM reasoning unavailable, using template fallback: {e}")

        # 回退到模板化结论
        return self._template_fallback(content, qtype, sub_questions, experiences, related)

    def _build_reasoning_prompt(self, content: str, qtype: str, sub_questions: list,
                                experiences: list, related: list) -> str:
        """构建推理 prompt"""
        parts = [f"请分析以下问题并给出简洁的推理结论（不超过300字）：\n问题类型: {qtype}\n问题内容: {content}"]
        if sub_questions:
            parts.append("分析维度:\n- " + "\n- ".join(sub_questions[:3]))
        if experiences:
            exp = experiences[0]
            parts.append(f"历史经验: {exp.get('conclusion', '') or exp.get('reasoning_summary', '')[:150]}")
        if related:
            previews = [r.get("preview", "")[:60] for r in related[:3]]
            parts.append("相关记忆: " + " | ".join(previews))
        return "\n\n".join(parts)

    def _template_fallback(self, content: str, qtype: str, sub_questions: list,
                           experiences: list, related: list) -> str:
        """模板化结论 — LLM 不可用时的回退"""
        parts = []
        if sub_questions:
            parts.append(f"分析维度: {'; '.join(sub_questions[:3])}")
        if experiences:
            best = experiences[0]
            exp_conclusion = best.get("conclusion", "") or best.get("reasoning_summary", "")
            if exp_conclusion:
                parts.append(f"历史经验: {exp_conclusion[:100]}")
        if related:
            related_previews = [r.get("preview", "")[:60] for r in related[:3]]
            parts.append(f"相关记忆: {' | '.join(related_previews)}")

        suggestions = {
            "疑问": "建议: 将问题提交给青龙(分析Agent)进行深度分析",
            "question": "建议: 将问题提交给青龙(分析Agent)进行深度分析",
            "stale_important": "建议: 通知朱雀(执行Agent)复查并更新相关记忆",
            "提醒": "建议: 通知朱雀(执行Agent)复查并更新相关记忆",
            "tag_diversity": "建议: 委托玄武(归档Agent)系统性扩展标签体系",
            "建议": "建议: 委托玄武(归档Agent)系统性扩展标签体系",
            "trending_drawer": "建议: 关注趋势变化，如有必要通知主控Agent",
            "knowledge_gap": "建议: 将知识空白加入好奇心引擎的探索优先级",
            "health_concern": "建议: 启动自愈巡检，排查健康度下降根因",
        }
        parts.append(suggestions.get(qtype, "建议: 持续监测，视情况升级处理优先级"))
        return " | ".join(parts)

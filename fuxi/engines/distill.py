"""伏羲 v1.5 — DistillationTower 记忆蒸馏（LLM驱动）

v1.5 升级: 增强知识卡片格式 — 增加因果链、证据数、知识空白字段。
知识卡片格式: 概念 → 原理 → 应用 → 关联 → 因果链 → 证据数 → 置信度 → 知识空白
"""
import json
import logging
import re
import uuid
from datetime import datetime

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.distill")


@register_engine("distill", experimental=False)
class DistillationTower(CognitiveEngine):
    """记忆蒸馏 v1.1 — LLM驱动的结构化知识卡片生成"""
    name = "distill"
    priority = 6
    interval = 3600  # 1小时

    def _generate_knowledge_card(self, items: list, drawer_id: str) -> dict:
        """v1.1: 使用 LLM 生成结构化知识卡片"""
        texts = [i["raw_text"][:300] for i in items]
        combined = "\n\n".join(f"- {t}" for t in texts)

        prompt = (
            "你是一个知识整理助手。请根据以下记忆片段，生成一个结构化知识卡片（JSON格式）。\n"
            "只需要输出JSON，不要解释。格式如下：\n"
            '{\n'
            '  "concept": "核心概念（一句话）",\n'
            '  "principle": "基本原理（50字）",\n'
            '  "applications": ["应用场景1", "应用场景2", "应用场景3"],\n'
            '  "relations": ["关联概念1", "关联概念2"],\n'
            '  "causal_links": ["因为X所以Y", "X导致Y"],\n'
            '  "evidence_count": 3,\n'
            '  "confidence": 0.85,\n'
            '  "knowledge_gaps": ["未确定的方面"]\n'
            "}\n\n"
            f"记忆片段:\n{combined}\n"
            "请直接输出JSON："
        )

        try:
            from fuxi.agent.integration import OpenClawAdapter
            adapter = OpenClawAdapter()
            result = adapter.call_agent("qinglong", prompt)
            if result and "reply" in result:
                card_text = result["reply"]
                # 提取 JSON
                json_match = re.search(r"\{[\s\S]*\}", card_text)
                if json_match:
                    card = json.loads(json_match.group())
                    return card
        except Exception as e:
            logger.debug(f"LLM knowledge card generation failed: {e}")

        # Fallback: 简单拼接
        return {
            "concept": texts[0][:50] if texts else "未知",
            "principle": "见原始记忆",
            "applications": [drawer_id],
            "relations": [],
            "causal_links": [],
            "evidence_count": len(texts),
            "confidence": 0.5,
            "knowledge_gaps": [],
        }

    def run(self) -> dict:
        pool = get_pool()

        # 选择蒸馏候选：高重要性 + 近期活跃
        candidates = pool.fetchall(
            "SELECT i.id, i.raw_text, i.facts, i.importance, i.decay_score, i.drawer_id "
            "FROM items i WHERE i.archived = 0 AND i.importance > 0.6 AND i.decay_score > 0.7 "
            "ORDER BY i.importance DESC, i.updated_at DESC LIMIT 20"
        )

        # 按抽屉分组
        by_drawer: dict = {}
        for c in candidates:
            d = c["drawer_id"]
            if d not in by_drawer:
                by_drawer[d] = []
            by_drawer[d].append(dict(c))

        # 对每组生成知识卡片
        distilled = []
        experiences_stored = 0
        for drawer_id, items in by_drawer.items():
            if len(items) < 2:
                continue
            source_ids = [i["id"] for i in items]

            # v1.1: LLM 生成知识卡片
            card = self._generate_knowledge_card(items, drawer_id)
            card_text = (
                f"[知识卡片] {card.get('concept', '')}\n"
                f"原理: {card.get('principle', '')}\n"
                f"应用: {'; '.join(card.get('applications', [])[:3])}\n"
                f"关联: {'; '.join(card.get('relations', [])[:5])}\n"
                f"因果链: {'; '.join(card.get('causal_links', [])[:3])}\n"
                f"证据数: {card.get('evidence_count', 0)}\n"
                f"置信度: {card.get('confidence', 0):.2f}\n"
                f"知识空白: {'; '.join(card.get('knowledge_gaps', [])[:2])}"
            )

            distilled.append({
                "drawer_id": drawer_id,
                "source_count": len(items),
                "concept": card.get("concept", ""),
                "confidence": card.get("confidence", 0),
                "distill_time": datetime.now().isoformat(),
            })

            # 保存知识卡片到 longterm 抽屉
            from fuxi.memory.ingestion import remember
            remember(
                raw_text=card_text,
                drawer_id="longterm",
                importance=0.9,
                source="distillation",
                facts=json.dumps({
                    "distilled_from": source_ids,
                    "knowledge_card": card,
                    "v": "1.5",
                }, ensure_ascii=False),
            )

            # 写入经验银行
            exp_id = str(uuid.uuid4())
            try:
                pool.execute(
                    "INSERT INTO experience_bank (id, task_type, input_desc, reasoning_summary, "
                    "conclusion, outcome, created_at) VALUES (?,?,?,?,?,?,?)",
                    (exp_id, "distillation", f"{len(items)} memories from {drawer_id}",
                     card.get("concept", "")[:200],
                     card_text[:300], "success", datetime.now().isoformat())
                )
                experiences_stored += 1
            except Exception as e:
                logger.warning(f"Failed to store experience: {e}")

        state = {
            "candidates": len(candidates),
            "groups": len(by_drawer),
            "distilled": len(distilled),
            "experiences_stored": experiences_stored,
            "timestamp": datetime.now().isoformat(),
        }

        with pool.connection() as c:
            c.execute(
                "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
                "VALUES (?,?,?)",
                ("distill", json.dumps(state, ensure_ascii=False), datetime.now().isoformat())
            )

        self._state.metadata["last_distill"] = state

        # 蒸馏完成后推入 WM 并发布事件
        if experiences_stored > 0:
            from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus
            from fuxi.kernel.working_memory import WMItem, get_working_memory
            get_working_memory().push(WMItem(
                id=f"distill:{datetime.now().strftime('%H%M%S')}",
                content=f"蒸馏完成: {experiences_stored}条知识卡片入库",
                source="engine:distill",
                emotional_valence=0.2,
                urgency=0.3,
                tokens=20,
            ))
            get_event_bus().publish(Event(
                type="distill.experience_created",
                data={"count": experiences_stored, "groups": len(distilled)},
                priority=EventPriority.LOW,
                source="engine:distill",
            ))

        return state

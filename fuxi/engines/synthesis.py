"""伏羲 v1.5 — 自主知识合成引擎 (synthesis)
跨集群联想引擎 / 模式发现 / 反事实推理 / 矛盾检测
"""
import logging
from datetime import datetime
from typing import Optional

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.synthesis")


@register_engine("synthesis", experimental=True)
class SynthesisEngine(CognitiveEngine):
    """自主知识合成引擎 v1.5 — 跨集群联想、模式发现、反事实推理、矛盾检测"""
    name = "synthesis"
    priority = 7
    interval = 1800
    experimental = True

    def _get_subscriptions(self):
        return {"memory.new": self._on_event, "engine.executed": self._on_event}

    def run(self) -> dict:
        pool = get_pool()

        # 处理 pending 事件
        pending = self._pop_pending_events()

        # 1. 跨集群联想 — 在不同抽屉之间寻找隐藏关联
        cross_cluster_insights = self._cross_cluster_association(pool)

        # 2. 模式发现 — 从频繁出现的记忆序列中提取重复模式
        discovered_patterns = self._pattern_discovery(pool)

        # 3. 反事实推理 — 生成"如果当初...会怎样"的假设场景
        counterfactual_scenarios = self._counterfactual_reasoning(pool)

        # 4. 矛盾检测 — 识别记忆中相互冲突的信念或陈述
        contradictions = self._contradiction_resolver(pool)

        synthesized_count = (
            len(cross_cluster_insights)
            + len(discovered_patterns)
            + len(counterfactual_scenarios)
            + len(contradictions)
        )

        state = {
            "cross_cluster_insights": cross_cluster_insights,
            "discovered_patterns": discovered_patterns,
            "counterfactual_scenarios": counterfactual_scenarios,
            "contradictions": contradictions,
            "synthesized_count": synthesized_count,
            "timestamp": datetime.now().isoformat(),
        }

        self._state.metadata["last_synthesis"] = state
        return state

    def _cross_cluster_association(self, pool) -> list:
        """跨集群联想引擎 — 在不同抽屉之间寻找隐藏关联"""
        insights = []

        try:
            # 找出连接不同抽屉的记忆（跨抽屉边）
            cross_drawer_edges = pool.fetchall("""
                SELECT e.id, e.source_id, e.target_id, e.weight,
                       s.drawer_id AS source_drawer, t.drawer_id AS target_drawer
                FROM edges e
                JOIN items s ON e.source_id = s.id
                JOIN items t ON e.target_id = t.id
                WHERE s.drawer_id != t.drawer_id
                ORDER BY e.weight DESC
                LIMIT 5
            """)
            for edge in cross_drawer_edges:
                if edge["source_drawer"] != edge["target_drawer"]:
                    insights.append({
                        "edge_id": str(edge["id"])[:8],
                        "source_drawer": edge["source_drawer"],
                        "target_drawer": edge["target_drawer"],
                        "weight": edge["weight"],
                        "type": "cross_cluster_link",
                    })
        except Exception as e:
            logger.warning(f"[synthesis] cross_cluster_association failed: {e}")

        return insights

    def _pattern_discovery(self, pool) -> list:
        """模式发现 — 从频繁出现的记忆序列中提取重复模式"""
        patterns = []

        try:
            # 查找时间上相邻的记忆序列，识别重复出现的主题
            recent_items = pool.fetchall("""
                SELECT id, raw_text, created_at, importance
                FROM items
                WHERE archived = 0
                ORDER BY created_at DESC
                LIMIT 20
            """)

            if not recent_items:
                return patterns

            # 简单的 n-gram 模式检测（基于连续时间窗口）
            for i in range(len(recent_items) - 2):
                text1 = recent_items[i]["raw_text"]
                text2 = recent_items[i + 1]["raw_text"]
                text3 = recent_items[i + 2]["raw_text"]

                # 检测共享关键词
                words1 = set(text1.split()) & set(text2.split())
                words2 = set(text2.split()) & set(text3.split())
                shared = words1 & words2
                if len(shared) >= 3:
                    patterns.append({
                        "shared_keywords": list(shared)[:5],
                        "items": [str(recent_items[j]["id"])[:8] for j in range(i, i + 3)],
                        "type": "sequential_theme",
                    })
        except Exception as e:
            logger.warning(f"[synthesis] pattern_discovery failed: {e}")

        return patterns[:3]

    def _counterfactual_reasoning(self, pool) -> list:
        """反事实推理 — 生成"如果当初...会怎样"的假设场景"""
        scenarios = []

        try:
            # 获取最近的高重要性失败/挫折记忆
            negative_items = pool.fetchall("""
                SELECT id, raw_text, importance, emotion_valence
                FROM items
                WHERE archived = 0 AND emotion_valence < -0.3
                ORDER BY importance DESC
                LIMIT 3
            """)

            for item in negative_items:
                text = item["raw_text"]
                # 简单的反事实生成：提取关键行动/决策
                words = text.split()
                if len(words) > 5:
                    scenarios.append({
                        "trigger_item": str(item["id"])[:8],
                        "premise": text[:80],
                        "question": f"如果当时采取了不同的方式，结果会怎样？",
                        "type": "counterfactual",
                    })
        except Exception as e:
            logger.warning(f"[synthesis] counterfactual_reasoning failed: {e}")

        return scenarios

    def _contradiction_resolver(self, pool) -> list:
        """矛盾检测 — 识别记忆中相互冲突的信念或陈述"""
        contradictions = []

        try:
            # 获取同一话题的正负情感记忆（矛盾信号）
            items = pool.fetchall("""
                SELECT id, raw_text, tags, emotion_valence, importance
                FROM items
                WHERE archived = 0 AND tags != '' AND emotion_valence != 0
                ORDER BY tags, created_at DESC
                LIMIT 50
            """)

            tag_groups: dict = {}
            for item in items:
                if not item["tags"]:
                    continue
                primary_tag = item["tags"].split(",")[0].strip()
                if primary_tag not in tag_groups:
                    tag_groups[primary_tag] = []
                tag_groups[primary_tag].append(item)

            # 检测同一标签下正负情感矛盾
            for tag, group in tag_groups.items():
                if len(group) < 2:
                    continue
                positive = [i for i in group if i["emotion_valence"] > 0.2]
                negative = [i for i in group if i["emotion_valence"] < -0.2]
                if positive and negative:
                    contradictions.append({
                        "topic": tag,
                        "positive_count": len(positive),
                        "negative_count": len(negative),
                        "items": [str(i["id"])[:8] for i in group[:4]],
                        "type": "emotional_contradiction",
                    })
        except Exception as e:
            logger.warning(f"[synthesis] contradiction_resolver failed: {e}")

        return contradictions
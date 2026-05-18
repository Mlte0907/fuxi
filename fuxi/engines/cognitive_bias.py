"""伏羲 v1.5 — 认知偏见检测引擎 (cognitive_bias)
偏见证别器 / 校正式回忆 / 思维模式报告
"""
import logging
from datetime import datetime
from typing import Optional

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.cognitive_bias")


@register_engine("cognitive_bias", experimental=True)
class CognitiveBiasEngine(CognitiveEngine):
    """认知偏见检测引擎 v1.5 — 偏见证别器、校正式回忆、思维模式报告"""
    name = "cognitive_bias"
    priority = 5
    interval = 3600
    experimental = True

    # 常见认知偏见类型
    BIAS_TYPES = [
        "confirmation_bias",   # 确认偏见
        "availability_bias",   # 可得性偏见
        "anchoring_bias",      # 锚定偏见
        "hindsight_bias",      # 后见之明偏见
        "optimism_bias",       # 乐观偏见
        "negativity_bias",     # 负面偏见
    ]

    def _get_subscriptions(self):
        return {"memory.new": self._on_event, "reflection.completed": self._on_event}

    def run(self) -> dict:
        pool = get_pool()

        # 处理 pending 事件
        pending = self._pop_pending_events()

        # 1. 偏见证别器 — 检测记忆中的认知偏见
        detected_biases = self._bias_detector(pool)

        # 2. 校正式回忆 — 生成更客观的记忆版本
        corrective_memories = self._corrective_recall(pool, detected_biases)

        # 3. 思维模式报告 — 生成思维模式分析报告
        thinking_report = self._thinking_pattern_report(pool, detected_biases)

        state = {
            "detected_biases": detected_biases,
            "corrective_memories": corrective_memories,
            "thinking_report": thinking_report,
            "timestamp": datetime.now().isoformat(),
        }

        self._state.metadata["last_bias_check"] = state
        return state

    def _bias_detector(self, pool) -> list:
        """偏见证别器 — 检测记忆中的认知偏见"""
        biases = []

        try:
            # 获取最近的高重要性记忆进行分析
            recent_items = pool.fetchall("""
                SELECT id, raw_text, emotion_valence, importance, created_at
                FROM items
                WHERE archived = 0
                AND importance > 0.5
                ORDER BY created_at DESC
                LIMIT 20
            """)

            for item in recent_items:
                text = item["raw_text"]
                detected_types = []

                # 确认偏见检测：只引用支持自己观点的记忆
                if ("但是" in text or "然而" in text) and item["emotion_valence"] > 0.3:
                    detected_types.append("confirmation_bias")

                # 负面偏见检测：负面情绪记忆权重过高
                if item["emotion_valence"] < -0.4 and item["importance"] > 0.7:
                    detected_types.append("negativity_bias")

                # 乐观偏见检测：过度正面的预测/预期
                if item["emotion_valence"] > 0.6 and "一定" in text or "肯定" in text:
                    detected_types.append("optimism_bias")

                # 可得性偏见检测：近期记忆影响过大（刚发生的印象深刻）
                if "刚才" in text or "最近" in text:
                    detected_types.append("availability_bias")

                if detected_types:
                    biases.append({
                        "item_id": str(item["id"])[:8],
                        "preview": text[:60],
                        "bias_types": detected_types,
                        "confidence": 0.5 + 0.1 * len(detected_types),
                    })
        except Exception as e:
            logger.warning(f"[cognitive_bias] bias_detector failed: {e}")

        return biases

    def _corrective_recall(self, pool, biases: list) -> list:
        """校正式回忆 — 生成更客观的记忆版本"""
        corrections = []

        try:
            for bias in biases[:3]:  # 每次最多处理3个
                item_id = bias.get("item_id", "")
                bias_types = bias.get("bias_types", [])

                correction_note = ""
                if "negativity_bias" in bias_types:
                    correction_note += "提示：负面记忆可能被过度放大，请考虑当时情境的完整性。"
                if "optimism_bias" in bias_types:
                    correction_note += "提示：乐观预期可能忽略了风险因素，请回顾实际结果。"
                if "confirmation_bias" in bias_types:
                    correction_note += "提示：确认偏见可能过滤了反对证据，建议寻找相反证据。"

                if correction_note:
                    corrections.append({
                        "original_item": item_id,
                        "corrective_note": correction_note,
                        "corrected_perspective": f"重新评估：{bias.get('preview', '')[:50]}",
                    })
        except Exception as e:
            logger.warning(f"[cognitive_bias] corrective_recall failed: {e}")

        return corrections

    def _thinking_pattern_report(self, pool, biases: list) -> dict:
        """思维模式报告 — 生成思维模式分析报告"""
        report = {
            "dominant_bias": None,
            "bias_distribution": {},
            "overall_score": 0.0,
            "recommendations": [],
        }

        try:
            if not biases:
                return report

            # 统计偏见分布
            type_counts: dict = {}
            for bias in biases:
                for btype in bias.get("bias_types", []):
                    type_counts[btype] = type_counts.get(btype, 0) + 1

            report["bias_distribution"] = type_counts

            # 找出主导偏见
            if type_counts:
                dominant = max(type_counts.items(), key=lambda x: x[1])
                report["dominant_bias"] = dominant[0]

            # 计算整体偏见得分（越低越好）
            total_bias_events = len(biases)
            report["overall_score"] = round(
                min(1.0, total_bias_events / 20.0), 4
            )

            # 生成建议
            if "confirmation_bias" in type_counts:
                report["recommendations"].append(
                    "刻意寻找反对观点，挑战自己的假设"
                )
            if "negativity_bias" in type_counts:
                report["recommendations"].append(
                    "平衡正面事件记忆，建立更完整的叙事"
                )
            if "optimism_bias" in type_counts:
                report["recommendations"].append(
                    "加入风险评估环节，列出可能的负面影响"
                )
        except Exception as e:
            logger.warning(f"[cognitive_bias] thinking_pattern_report failed: {e}")

        return report
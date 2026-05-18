"""伏羲 v1.5 — 深度情绪智能引擎 (deep_emotion)
情绪轨迹追踪 / 混合情绪解耦 / 个性化情绪学习
"""
import logging
from datetime import datetime
from typing import Optional

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.deep_emotion")


@register_engine("deep_emotion", experimental=True)
class DeepEmotionEngine(CognitiveEngine):
    """深度情绪智能引擎 v1.5 — 情绪轨迹追踪、混合情绪解耦、个性化情绪学习"""
    name = "deep_emotion"
    priority = 8
    interval = 300
    experimental = True

    def _get_subscriptions(self):
        return {"emotion.updated": self._on_event, "memory.new": self._on_event}

    def run(self) -> dict:
        pool = get_pool()

        # 处理 pending 事件
        pending = self._pop_pending_events()

        # 1. 情绪轨迹追踪 — 追踪情绪随时间的变化趋势
        trajectory = self._emotional_trajectory(pool)

        # 2. 混合情绪解耦 — 识别复杂情绪状态中的多个成分
        decomposed = self._mixed_emotion_decomposition(pool)

        # 3. 个性化情绪学习 — 基于用户特征调整情绪模型
        personalized = self._personalized_affect_model(pool)

        state = {
            "trajectory": trajectory,
            "decomposed_emotions": decomposed,
            "personalized_model": personalized,
            "timestamp": datetime.now().isoformat(),
        }

        self._state.metadata["last_deep_emotion"] = state
        return state

    def _emotional_trajectory(self, pool) -> dict:
        """情绪轨迹追踪 — 追踪情绪随时间的变化趋势"""
        trajectory = {"trend": "stable", "velocity": 0.0, "acceleration": 0.0, "data_points": []}

        try:
            # 获取最近的情绪数据点（24小时内）
            emotion_points = pool.fetchall("""
                SELECT created_at, valence, arousal, frustration
                FROM items
                WHERE archived = 0
                AND emotion_valence != 0
                AND created_at > datetime('now', '-24 hours')
                ORDER BY created_at ASC
                LIMIT 20
            """)

            if len(emotion_points) >= 2:
                # 计算情绪速度（一阶导数）
                velocities = []
                for i in range(1, len(emotion_points)):
                    dt = 1.0  # 假设单位间隔
                    dv = emotion_points[i]["valence"] - emotion_points[i - 1]["valence"]
                    velocities.append(dv / dt)

                avg_velocity = sum(velocities) / len(velocities) if velocities else 0.0

                # 计算情绪加速度（二阶导数）
                accelerations = []
                for i in range(1, len(velocities)):
                    accelerations.append(velocities[i] - velocities[i - 1])

                avg_acceleration = sum(accelerations) / len(accelerations) if accelerations else 0.0

                # 确定趋势
                if avg_velocity > 0.1:
                    trend = "improving"
                elif avg_velocity < -0.1:
                    trend = "declining"
                else:
                    trend = "stable"

                trajectory = {
                    "trend": trend,
                    "velocity": round(avg_velocity, 4),
                    "acceleration": round(avg_acceleration, 4),
                    "data_points": [
                        {"ts": p["created_at"], "valence": p["valence"]}
                        for p in emotion_points[-5:]
                    ],
                }
        except Exception as e:
            logger.warning(f"[deep_emotion] emotional_trajectory failed: {e}")

        return trajectory

    def _mixed_emotion_decomposition(self, pool) -> list:
        """混合情绪解耦 — 识别复杂情绪状态中的多个成分"""
        decomposed = []

        try:
            # 获取最近的高复杂性情绪状态（多种情绪维度都较高）
            mixed_states = pool.fetchall("""
                SELECT id, raw_text, emotion_valence, arousal, frustration, interest
                FROM items
                WHERE archived = 0
                AND emotion_valence != 0
                AND created_at > datetime('now', '-6 hours')
                ORDER BY created_at DESC
                LIMIT 10
            """)

            for item in mixed_states:
                components = []

                # 检测多种情绪成分
                if item["emotion_valence"] > 0.2:
                    components.append("positive")
                elif item["emotion_valence"] < -0.2:
                    components.append("negative")

                if item["arousal"] > 0.6:
                    components.append("high_arousal")
                elif item["arousal"] < 0.3:
                    components.append("low_arousal")

                if item["frustration"] > 0.4:
                    components.append("frustrated")

                if item["interest"] > 0.5:
                    components.append("interested")

                # 如果有多个成分，说明是混合情绪
                if len(components) >= 2:
                    decomposed.append({
                        "item_id": str(item["id"])[:8],
                        "preview": item["raw_text"][:50],
                        "components": components,
                        "primary": components[0],
                    })
        except Exception as e:
            logger.warning(f"[deep_emotion] mixed_emotion_decomposition failed: {e}")

        return decomposed

    def _personalized_affect_model(self, pool) -> dict:
        """个性化情绪学习 — 基于用户特征调整情绪模型"""
        model = {
            "baseline_valence": 0.0,
            "typical_arousal": 0.5,
            "emotion_patterns": [],
            "personalization_score": 0.0,
        }

        try:
            # 分析历史情绪数据，建立个性化基线
            historical = pool.fetchall("""
                SELECT AVG(emotion_valence) AS avg_valence,
                       AVG(arousal) AS avg_arousal,
                       AVG(frustration) AS avg_frustration,
                       COUNT(*) AS sample_count
                FROM items
                WHERE archived = 0
                AND emotion_valence != 0
                AND created_at > datetime('now', '-7 days')
            """)

            if historical and historical[0]["sample_count"] > 5:
                row = historical[0]
                model["baseline_valence"] = round(row["avg_valence"] or 0.0, 4)
                model["typical_arousal"] = round(row["avg_arousal"] or 0.5, 4)
                model["personalization_score"] = min(1.0, row["sample_count"] / 50.0)

            # 检测个人特有的情绪模式
            patterns = pool.fetchall("""
                SELECT emotion_valence, COUNT(*) AS cnt
                FROM items
                WHERE archived = 0
                AND emotion_valence != 0
                AND created_at > datetime('now', '-7 days')
                GROUP BY ROUND(emotion_valence, 1)
                ORDER BY cnt DESC
                LIMIT 3
            """)

            model["emotion_patterns"] = [
                {"valence": p["emotion_valence"], "frequency": p["cnt"]}
                for p in patterns
            ]
        except Exception as e:
            logger.warning(f"[deep_emotion] personalized_affect_model failed: {e}")

        return model
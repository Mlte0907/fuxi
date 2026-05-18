"""伏羲 v1.5 — 用户意图预测引擎 (intent_prediction)
时序意图建模 / 任务链追踪 / 上下文感知建议
"""
import logging
from datetime import datetime, timedelta

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.intent_prediction")


@register_engine("intent_prediction", experimental=True)
class IntentPredictionEngine(CognitiveEngine):
    """用户意图预测引擎 v1.5 — 时序意图建模、任务链追踪、上下文感知建议"""
    name = "intent_prediction"
    priority = 6
    interval = 600
    experimental = True

    def _get_subscriptions(self):
        return {"action.user": self._on_event, "task.started": self._on_event}

    def run(self) -> dict:
        pool = get_pool()

        # 处理 pending 事件
        pending = self._pop_pending_events()

        # 1. 时序意图建模 — 从用户行为序列推断当前意图
        intent_model = self._temporal_intent_model(pool)

        # 2. 任务链追踪 — 跟踪多步骤任务的进度
        task_chain = self._task_chain_tracker(pool)

        # 3. 上下文感知建议 — 基于当前上下文生成智能建议
        suggestions = self._contextual_suggestion(pool, intent_model, task_chain)

        state = {
            "current_intent": intent_model,
            "task_chain": task_chain,
            "suggestions": suggestions,
            "timestamp": datetime.now().isoformat(),
        }

        self._state.metadata["last_prediction"] = state
        return state

    def _temporal_intent_model(self, pool) -> dict:
        """时序意图建模 — 从用户行为序列推断当前意图"""
        model = {"intent": "unknown", "confidence": 0.0, "context": []}

        try:
            # 获取最近的用户行为
            recent_actions = pool.fetchall("""
                SELECT event_type, data, created_at
                FROM event_log
                WHERE event_type LIKE 'action.%'
                AND created_at > datetime('now', '-30 minutes')
                ORDER BY created_at DESC
                LIMIT 10
            """)

            if not recent_actions:
                return model

            # 简单的意图推断：基于行为序列模式
            action_types = [a["event_type"] for a in recent_actions]

            # 检测常见意图模式
            if any("search" in t for t in action_types):
                model["intent"] = "information_seeking"
                model["confidence"] = 0.7
            elif any("write" in t for t in action_types) or any("edit" in t for t in action_types):
                model["intent"] = "content_creation"
                model["confidence"] = 0.6
            elif any("read" in t for t in action_types):
                model["intent"] = "consuming_content"
                model["confidence"] = 0.5

            model["context"] = action_types[:5]
        except Exception as e:
            logger.warning(f"[intent_prediction] temporal_intent_model failed: {e}")

        return model

    def _task_chain_tracker(self, pool) -> dict:
        """任务链追踪 — 跟踪多步骤任务的进度"""
        tracker = {"active_tasks": [], "completed_steps": 0, "total_steps": 0}

        try:
            # 获取最近创建的任务（标记为进行中）
            active_tasks = pool.fetchall("""
                SELECT id, raw_text, created_at
                FROM items
                WHERE archived = 0
                AND (tags LIKE '%任务%' OR tags LIKE '%task%')
                ORDER BY created_at DESC
                LIMIT 5
            """)

            for task in active_tasks:
                tracker["active_tasks"].append({
                    "id": str(task["id"])[:8],
                    "preview": task["raw_text"][:50],
                    "created_at": task["created_at"],
                })

            # 估算完成步骤
            total = len(active_tasks)
            # 简单估算：每3个记忆约等于1个完成步骤
            completed = min(total, pool.fetchone(
                "SELECT COUNT(*) AS cnt FROM items WHERE archived=0"
            )["cnt"] // 3)

            tracker["completed_steps"] = completed
            tracker["total_steps"] = total + completed
        except Exception as e:
            logger.warning(f"[intent_prediction] task_chain_tracker failed: {e}")

        return tracker

    def _contextual_suggestion(self, pool, intent_model: dict, task_chain: dict) -> list:
        """上下文感知建议 — 基于当前上下文生成智能建议"""
        suggestions = []

        try:
            # 基于当前意图给出建议
            current_intent = intent_model.get("intent", "unknown")
            if current_intent == "information_seeking":
                suggestions.append({
                    "type": "next_action",
                    "content": "考虑深入探索相关主题",
                    "confidence": 0.6,
                })
            elif current_intent == "content_creation":
                suggestions.append({
                    "type": "next_action",
                    "content": "建议保存当前进度并记录灵感",
                    "confidence": 0.5,
                })

            # 基于任务链给出建议
            active = task_chain.get("active_tasks", [])
            if len(active) > 3:
                suggestions.append({
                    "type": "task_overload",
                    "content": "当前有较多进行中任务，建议专注完成其一",
                    "confidence": 0.7,
                })
        except Exception as e:
            logger.warning(f"[intent_prediction] contextual_suggestion failed: {e}")

        return suggestions
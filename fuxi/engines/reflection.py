"""伏羲 v1.0 — ReflectionEngine 主动反思与问题生成"""
import contextlib
import json
import logging
from datetime import datetime
from typing import Optional

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.config import config
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.reflection")


@register_engine("reflection", experimental=False)
class ReflectionEngine(CognitiveEngine):
    """主动反思 — 从记忆中发现问题、生成洞见、提出疑问"""
    name = "reflection"
    priority = 7
    interval = 900  # 15分钟

    def _get_subscriptions(self):
        return {"memory.created": self._on_event}

    def run(self) -> dict:
        pool = get_pool()

        # 处理 pending 事件：检查新记忆是否与孤立记忆相关
        pending = self._pop_pending_events()
        new_memory_ids = set()
        for evt in pending:
            if evt["type"] == "memory.created" and evt["data"].get("id"):
                new_memory_ids.add(evt["data"]["id"])

        # 1. 读取最近的长期记忆（排除自省类）
        recent = pool.fetchall(
            "SELECT id, raw_text, drawer_id, importance, tags FROM items "
            "WHERE archived=0 AND drawer_id='longterm' "
            "ORDER BY created_at DESC LIMIT 30"
        )
        if not recent:
            return {"status": "idle", "reason": "no longterm memories"}

        # 2. 查找记忆中的缺口模式
        ids = [r["id"] for r in recent]
        placeholders = ",".join("?" * len(ids))
        edges = pool.fetchall(
            f"SELECT source_id, target_id, edge_type FROM edges "
            f"WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})",
            ids + ids,
        )

        # 3. 找孤立记忆（没有连接的）
        connected = set()
        for e in edges:
            connected.add(e["source_id"])
            connected.add(e["target_id"])
        isolated = [r for r in recent if r["id"] not in connected]

        actions: list[dict] = []
        results = {"observed": len(recent), "connected": len(connected), "isolated": len(isolated), "actions": actions}

        # 4. 查询经验库，为后续问题提供过往经验
        try:
            exp_rows = pool.fetchall(
                "SELECT task_type, conclusion FROM experience_bank "
                "ORDER BY created_at DESC LIMIT 10"
            )
            past_experiences = [dict(r) for r in exp_rows]
        except Exception:
            past_experiences = []

        # 5. 为孤立记忆生成关联问题（每日写入上限，防止记忆库膨胀）
        today_reflections = pool.fetchone(
            "SELECT COUNT(*) AS cnt FROM items WHERE created_by='reflection' "
            "AND created_at > datetime('now', 'start of day')"
        )
        daily_cap = config.reflection_daily_cap
        if today_reflections and today_reflections["cnt"] >= daily_cap:
            logger.debug(f"ReflectionEngine daily cap reached ({daily_cap}), skipping write")
            return {"status": "idle", "reason": "daily cap reached", **results}

        from fuxi.memory.ingestion import remember

        for item in isolated[:3]:  # 最多处理 3 条
            question = self._generate_question(item, past_experiences)
            if question:
                try:
                    remember(
                        raw_text=question,
                        drawer_id="longterm",
                        importance=0.35,
                        source="self",
                        confidence=0.5,
                        created_by="reflection",
                        tags=["疑问", "reflection"],
                    )
                    actions.append({"type": "question", "related_to": item["id"][:8]})
                except Exception as e:
                    logger.debug(f"Reflection question failed: {e}")

        # 6. 如果记忆增长但缺乏多样性，提出建议
        tags_row = pool.fetchall(
            "SELECT tags FROM items WHERE archived=0 AND drawer_id='longterm' ORDER BY created_at DESC LIMIT 100"
        )
        all_tags = set()
        for r in tags_row:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                all_tags.update(json.loads(r["tags"]))

        if len(all_tags) < 3 and len(recent) > 20:
            suggestion = f"[建议] 记忆库中标签多样新较低(仅{len(all_tags)}种)，建议丰富记忆分类维度"
            try:
                remember(
                    raw_text=suggestion,
                    drawer_id="longterm",
                    importance=0.3,
                    source="self",
                    confidence=0.7,
                    created_by="reflection",
                    tags=["建议", "reflection"],
                )
                actions.append({"type": "suggestion", "detail": "tag_diversity"})
            except Exception as e:
                logger.debug(f"Reflection suggestion failed: {e}")

        # 7. 持久化
        state = {
            "results": results,
            "timestamp": datetime.now().isoformat(),
        }
        with pool.connection() as c:
            c.execute(
                "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
                "VALUES (?,?,?)",
                ("reflection", json.dumps(state, ensure_ascii=False), datetime.now().isoformat())
            )
        self._state.metadata["last_reflection"] = state

        # 推送孤立记忆问题到工作记忆
        from fuxi.kernel.working_memory import WMItem, get_working_memory
        wm = get_working_memory()
        for action in actions[:2]:
            wm.push(WMItem(
                id=f"reflection:{action.get('type','?')}:{datetime.now().strftime('%H%M%S')}",
                content=action.get("detail", action.get("type", "reflection insight")),
                source="engine:reflection",
                emotional_valence=-0.1,
                urgency=0.4,
                tokens=10,
            ))

        return state

    def _generate_question(self, item, past_experiences: Optional[list] = None) -> str:
        text = item["raw_text"][:200] if item["raw_text"] else ""
        importance = item["importance"] if item["importance"] is not None else 0
        # 附加过往经验提示
        exp_hint = ""
        if past_experiences:
            relevant = [e for e in past_experiences[:3] if e["conclusion"]]
            if relevant:
                snippets = [e["conclusion"][:60] for e in relevant[:2]]
                exp_hint = f" | 过往经验参考: {'; '.join(snippets)}"
        if importance > 0.7:
            return f"[疑问] 关于'{text[:80]}...'这条重要记忆，是否需要补充更多背景？与其他记忆存在什么关联？{exp_hint}"
        return f"[疑问] 注意到孤立记忆'{text[:80]}...'，它和什么相关？是否需要回顾？{exp_hint}"

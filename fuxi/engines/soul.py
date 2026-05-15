"""伏羲 v1.0 — SoulEngine 灵魂核心驱动"""
import json
import logging
from datetime import datetime

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.soul")


@register_engine("soul", experimental=False)
class SoulEngine(CognitiveEngine):
    """灵魂核心驱动 — 维护系统"自我"感知和整体状态"""
    name = "soul"
    priority = 10
    interval = 60

    def run(self) -> dict:
        pool = get_pool()

        # 收集全局状态
        total_items = pool.fetchone("SELECT COUNT(*) AS cnt FROM items WHERE archived=0")
        total_edges = pool.fetchone("SELECT COUNT(*) AS cnt FROM edges")
        recent = pool.fetchall(
            "SELECT id, SUBSTR(raw_text,1,50) AS preview, importance, created_at "
            "FROM items WHERE archived=0 ORDER BY created_at DESC LIMIT 5"
        )

        # 健康度评分
        total = total_items["cnt"] if total_items else 0
        edges_cnt = total_edges["cnt"] if total_edges else 0

        # 1. 嵌入覆盖率
        embed_row = pool.fetchone("SELECT COUNT(*) AS cnt FROM items WHERE archived=0 AND embedding IS NOT NULL")
        embed_coverage = (embed_row["cnt"] / total) if total > 0 else 0.0

        # 2. 衰减健康度 (平均衰减分)
        decay_row = pool.fetchone("SELECT AVG(decay_score) AS avg FROM items WHERE archived=0")
        decay_health = float(decay_row["avg"]) if decay_row and decay_row["avg"] else 1.0

        # 3. 连接密度 (边/记忆)
        connectivity = (edges_cnt / total) if total > 0 else 0.0
        conn_score = min(1.0, connectivity / 3.0)  # 3 edges per item = full score

        # 4. 新鲜度 (7天内更新比例)
        fresh_row = pool.fetchone(
            "SELECT COUNT(*) AS cnt FROM items WHERE archived=0 "
            "AND updated_at >= datetime('now','-7 days')"
        )
        freshness = (fresh_row["cnt"] / total) if total > 0 else 0.0

        # 综合健康度 (加权)
        health_score = round(
            embed_coverage * 0.15 +
            decay_health * 0.35 +
            conn_score * 0.25 +
            freshness * 0.25, 4
        )

        if health_score >= 0.7:
            health_label = "healthy"
        elif health_score >= 0.4:
            health_label = "moderate"
        else:
            health_label = "needs_attention"

        state = {
            "identity": "伏羲 v1.0 — JinLanGe Memory Core",
            "timestamp": datetime.now().isoformat(),
            "total_memories": total,
            "total_connections": edges_cnt,
            "health": "alive",
            "health_score": {
                "overall": health_score,
                "label": health_label,
                "breakdown": {
                    "embed_coverage": round(embed_coverage, 4),
                    "decay_health": round(decay_health, 4),
                    "connectivity": round(conn_score, 4),
                    "freshness": round(freshness, 4),
                },
            },
            "recent_activity": [
                {"id": r["id"][:8], "preview": r["preview"], "importance": r["importance"]}
                for r in recent
            ],
        }

        # 持久化引擎状态
        with pool.connection() as c:
            c.execute(
                "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
                "VALUES (?,?,?)",
                ("soul", json.dumps(state, ensure_ascii=False), datetime.now().isoformat())
            )

        self._state.metadata["last_state"] = state

        # 主动写入自省记忆（仅健康度变化或每小时一次）
        last_label = self._state.metadata.get("last_state", {}).get("health_score", {}).get("label", "")
        last_ts = self._state.metadata.get("last_state", {}).get("timestamp", "")
        should_write = (health_label != last_label)
        if last_ts and not should_write:
            try:
                dt = datetime.fromisoformat(last_ts)
                if (datetime.now() - dt).total_seconds() > 3600:
                    should_write = True
            except (ValueError, TypeError):
                should_write = True
        if should_write:
            # 限制每日自省记忆写入上限（防止反馈循环）
            today_reflections = pool.fetchone(
                "SELECT COUNT(*) AS cnt FROM items WHERE created_by='soul' "
                "AND created_at > datetime('now','start of day')"
            )
            daily_cap = 10
            if today_reflections and today_reflections["cnt"] >= daily_cap:
                logger.debug(f"Soul self-reflection daily cap ({daily_cap}) reached, skipping write")
            else:
                from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus
                if health_label != last_label:
                    get_event_bus().publish(Event(
                        type="soul.health_changed",
                        data={"old_label": last_label, "new_label": health_label, "score": health_score},
                        priority=EventPriority.NORMAL,
                        source="engine:soul",
                    ))
                try:
                    from fuxi.memory.ingestion import remember
                    remember(
                        raw_text=f"[自省] 健康度 {health_label}({health_score:.2f})，"
                                 f"记忆{total}条，连接{edges_cnt}条，嵌入覆盖{embed_coverage:.0%}",
                        drawer_id="longterm",
                        importance=0.3,
                        source="self",
                        confidence=0.85,
                        created_by="soul",
                        emotion_valence=0.05,
                        tags=["自省", "soul"],
                    )
                except Exception as e:
                    logger.debug(f"Self-reflection memory failed: {e}")

        # 推入工作记忆
        from fuxi.kernel.working_memory import WMItem, get_working_memory
        get_working_memory().push(WMItem(
            id=f"soul:{datetime.now().strftime('%H%M')}",
            content=f"健康度 {health_label}({health_score:.2f}) 记忆{total} 连接{edges_cnt}",
            source="engine:soul",
            emotional_valence=0.05,
            urgency=0.7 if health_label == "needs_attention" else 0.2,
            tokens=20,
        ))

        return state

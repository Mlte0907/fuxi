"""伏羲 v1.0 — NudgeEngine 轻推引擎

基于系统状态检测，对记忆系统做出温和的建议性干预。
不自主执行，只生成建议供决策引擎或用户审阅。"""
import json
import uuid
from datetime import datetime

from fuxi.engines.base import CognitiveEngine, register_engine


@register_engine("nudge", experimental=False)
class NudgeEngine(CognitiveEngine):
    """轻推引擎 — 温和建议，干预提示

    检测系统状态异常，生成建议性的轻推提示。
    不自主执行变更，仅提供可执行的建议列表。
    """

    name = "nudge"
    priority = 10  # 在 adaptive 和 decision 之后运行
    interval = 900  # 15分钟

    NUDGE_CHECKS = [
        "unused_drawers",
        "memory_decay_surge",
        "fts_staleness",
        "orphan_edges",
        "cold_engine",
        "confidence_drop",
    ]

    def run(self) -> dict:
        from fuxi.store.connection import get_pool

        pool = get_pool()
        nudges = []

        for check_name in self.NUDGE_CHECKS:
            check_fn = getattr(self, f"_check_{check_name}", None)
            if check_fn:
                result = check_fn(pool)
                if result:
                    nudges.append(result)

        # 持久化轻推建议
        if nudges:
            self._persist_nudges(nudges)

        return {
            "nudges": nudges,
            "count": len(nudges),
            "timestamp": datetime.now().isoformat(),
        }

    def _check_unused_drawers(self, pool) -> dict | None:
        """检测长时间未使用的抽屉"""
        row = pool.fetchone(
            "SELECT id, name, updated_at FROM drawers "
            "WHERE updated_at < datetime('now','-7 days') "
            "AND id != 'default' ORDER BY updated_at LIMIT 1"
        )
        if row:
            return {
                "id": str(uuid.uuid4()),
                "type": "unused_drawer",
                "severity": "low",
                "message": f"抽屉 '{row['name']}' 已 7 天未更新",
                "suggestion": "考虑归档或清理该抽屉的空记忆",
                "target": f"drawer:{row['id']}",
            }
        return None

    def _check_memory_decay_surge(self, pool) -> dict | None:
        """检测衰减分数骤降的记忆群"""
        row = pool.fetchone(
            "SELECT COUNT(*) AS cnt FROM items "
            "WHERE archived=0 AND decay_score < 0.2 AND importance > 0.5"
        )
        if row and row["cnt"] > 20:
            return {
                "id": str(uuid.uuid4()),
                "type": "decay_surge",
                "severity": "medium",
                "message": f"{row['cnt']} 条高重要性记忆衰减分数过低",
                "suggestion": "手动触发衰减重新计算或增加触摸频率",
                "target": "decay_system",
            }
        return None

    def _check_fts_staleness(self, pool) -> dict | None:
        """检测 FTS5 索引与主表的同步状态"""
        try:
            fts_cnt = pool.fetchone("SELECT COUNT(*) AS cnt FROM items_fts")
            items_cnt = pool.fetchone(
                "SELECT COUNT(*) AS cnt FROM items WHERE archived=0"
            )
            if fts_cnt and items_cnt:
                gap = items_cnt["cnt"] - fts_cnt["cnt"]
                if gap > 10:
                    return {
                        "id": str(uuid.uuid4()),
                        "type": "fts_stale",
                        "severity": "high",
                        "message": f"FTS 索引落后 {gap} 条记录",
                        "suggestion": "运行 FTS5 索引重建以恢复搜索准确性",
                        "target": "fts_index",
                    }
        except Exception:
            pass
        return None

    def _check_orphan_edges(self, pool) -> dict | None:
        """检测悬挂的图边"""
        row = pool.fetchone(
            "SELECT COUNT(*) AS cnt FROM edges e "
            "LEFT JOIN items i1 ON e.source_id = i1.id "
            "LEFT JOIN items i2 ON e.target_id = i2.id "
            "WHERE i1.id IS NULL OR i2.id IS NULL"
        )
        if row and row["cnt"] > 5:
            return {
                "id": str(uuid.uuid4()),
                "type": "orphan_edges",
                "severity": "low",
                "message": f"发现 {row['cnt']} 条悬挂图边（源/目标记忆已删除）",
                "suggestion": "运行图清理以移除无效边",
                "target": "graph_system",
            }
        return None

    def _check_cold_engine(self, pool) -> dict | None:
        """检测长时间未运行的引擎"""
        from fuxi.engines.base import get_engine_registry

        cold_engines = []
        for engine in get_engine_registry().list_all():
            e = get_engine_registry().get(engine["name"])
            if e and e._state.last_run > 0:
                since_last = datetime.now().timestamp() - e._state.last_run
                if since_last > 3600 and e.name not in ("cognitive_loop",):
                    cold_engines.append(e.name)

        if cold_engines:
            return {
                "id": str(uuid.uuid4()),
                "type": "cold_engine",
                "severity": "medium",
                "message": f"引擎 {', '.join(cold_engines)} 超过1小时未运行",
                "suggestion": "检查引擎调度器是否正常",
                "target": "engine_scheduler",
            }
        return None

    def _check_confidence_drop(self, pool) -> dict | None:
        """检测自适应参数置信度下降"""
        row = pool.fetchone(
            "SELECT state_json FROM engine_states WHERE engine_name='adaptive'"
        )
        if row:
            try:
                data = json.loads(row["state_json"])
                if data.get("confidence", 1.0) < 0.3:
                    return {
                        "id": str(uuid.uuid4()),
                        "type": "confidence_drop",
                        "severity": "high",
                        "message": f"自适应参数置信度已降至 {data['confidence']:.2f}",
                        "suggestion": "考虑重置自适应参数到默认值",
                        "target": "adaptive_system",
                    }
            except Exception:
                pass
        return None

    def _persist_nudges(self, nudges: list):
        from fuxi.store.write_queue import get_write_queue
        wq = get_write_queue()
        for nudge in nudges:
            wq.enqueue(
                "INSERT INTO event_log (event_type, source, event_data, created_at) "
                "VALUES (?,?,?,?)",
                ("nudge", "engine:nudge",
                 json.dumps(nudge, ensure_ascii=False),
                 datetime.now().isoformat())
            )

"""伏羲 v1.0 — ImmuneEngine 自愈巡检"""
import json
import logging
from datetime import datetime

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.immune")


@register_engine("immune", experimental=False)
class ImmuneEngine(CognitiveEngine):
    """自愈巡检 — 检测数据异常并自动修复"""
    name = "immune"
    priority = 7
    interval = 600  # 10分钟

    def _get_subscriptions(self):
        return {"wm.item_evicted": self._on_eviction}

    def _on_eviction(self, event):
        """WM 驱逐事件处理：将驱逐项写入长期记忆"""
        try:
            data = event.data
            item_id = data.get("id", "?")
            content = f"[WM驱逐] ID={item_id}, activation={data.get('activation', '?')}, reason={data.get('reason', '?')}"
            from fuxi.memory.ingestion import remember
            remember(
                raw_text=content,
                drawer_id="longterm",
                importance=0.2,
                source="immune",
                confidence=0.6,
                created_by="immune",
                tags=["wm_eviction", "working_memory", "auto"],
            )
            logger.debug(f"Eviction logged: {item_id}")
        except Exception as e:
            logger.debug(f"Eviction handler error: {e}")

    def run(self) -> dict:
        pool = get_pool()
        issues = []
        fixes = []

        # 检查1: 孤立边（指向不存在的记忆）
        orphan_edges = pool.fetchall(
            "SELECT e.id, e.source_id, e.target_id FROM edges e "
            "LEFT JOIN items s ON e.source_id = s.id "
            "LEFT JOIN items t ON e.target_id = t.id "
            "WHERE s.id IS NULL OR t.id IS NULL"
        )
        if orphan_edges:
            ids = [e["id"] for e in orphan_edges]
            with pool.connection() as c:
                placeholders = ",".join("?" * len(ids))
                c.execute(f"DELETE FROM edges WHERE id IN ({placeholders})", ids)
            issues.append(f"orphan_edges: {len(ids)}")
            fixes.append(f"removed {len(ids)} orphan edges")

        # 检查2: 空抽屉（无记忆但计数>0）
        empty_drawers = pool.fetchall(
            "SELECT d.id, d.item_count FROM drawers d "
            "LEFT JOIN (SELECT drawer_id, COUNT(*) as actual FROM items WHERE archived=0 GROUP BY drawer_id) i "
            "ON d.id = i.drawer_id WHERE (i.actual IS NULL OR i.actual = 0) AND d.item_count > 0"
        )
        if empty_drawers:
            with pool.connection() as c:
                for d in empty_drawers:
                    c.execute("UPDATE drawers SET item_count=0 WHERE id=?", (d["id"],))
            issues.append(f"empty_drawers: {len(empty_drawers)}")
            fixes.append(f"reset counts for {len(empty_drawers)} drawers")

        # 检查3: 损坏的embedding（无效JSON）
        bad_embeds = pool.fetchall(
            "SELECT id, embedding FROM items WHERE embedding IS NOT NULL AND embedding != ''"
        )
        corrupt = 0
        for r in bad_embeds:
            try:
                json.loads(r["embedding"])
            except json.JSONDecodeError:
                corrupt += 1
        if corrupt > 0:
            issues.append(f"corrupt_embeds: {corrupt}")

        # 检查4a: FTS5 孤儿索引（已物理删除的记忆残留）
        fts_orphans = pool.fetchall(
            "SELECT f.rowid FROM items_fts f "
            "LEFT JOIN items i ON f.rowid = i.rowid "
            "WHERE i.rowid IS NULL"
        )
        if fts_orphans:
            orphan_rowids = [r["rowid"] for r in fts_orphans]
            with pool.connection() as c:
                placeholders = ",".join("?" * len(orphan_rowids))
                c.execute(f"DELETE FROM items_fts WHERE rowid IN ({placeholders})", orphan_rowids)
            issues.append(f"fts_orphans: {len(orphan_rowids)}")
            fixes.append(f"cleaned {len(orphan_rowids)} FTS5 orphan entries")

        # 检查4b: FTS5 已归档记忆残留（软删除后 FTS 未清理）
        fts_archived = pool.fetchall(
            "SELECT f.rowid FROM items_fts f "
            "JOIN items i ON f.rowid = i.rowid "
            "WHERE i.archived = 1"
        )
        if fts_archived:
            archived_rowids = [r["rowid"] for r in fts_archived]
            with pool.connection() as c:
                placeholders = ",".join("?" * len(archived_rowids))
                c.execute(f"DELETE FROM items_fts WHERE rowid IN ({placeholders})", archived_rowids)
            issues.append(f"fts_archived_residual: {len(archived_rowids)}")
            fixes.append(f"cleaned {len(archived_rowids)} archived entries from FTS5")

        # 检查5: FTS5 缺失索引（有记忆但无全文索引）
        fts_missing = pool.fetchall(
            "SELECT i.rowid FROM items i "
            "LEFT JOIN items_fts f ON i.rowid = f.rowid "
            "WHERE i.archived = 0 AND f.rowid IS NULL"
        )
        if fts_missing:
            missing_rowids = [r["rowid"] for r in fts_missing]
            with pool.connection() as c:
                for rowid in missing_rowids:
                    c.execute(
                        "INSERT INTO items_fts (rowid, raw_text, facts, tags) "
                        "SELECT rowid, raw_text, facts, tags FROM items WHERE rowid = ?",
                        (rowid,)
                    )
            issues.append(f"fts_missing: {len(missing_rowids)}")
            fixes.append(f"rebuilt {len(missing_rowids)} missing FTS5 entries")

        # 检查6: 连接池状态
        pool_stats = {
            "size": pool._pool.qsize() if hasattr(pool, '_pool') else 'unknown',
        }

        # 检查7: 清理过期 event_log（保留30天）
        try:
            from fuxi.memory.decay import cleanup_event_log
            log_result = cleanup_event_log(retain_days=30, dry_run=False)
            if log_result.get("deleted", 0) > 0:
                fixes.append(f"event_log_cleanup: removed {log_result['deleted']} entries")
        except Exception as e:
            logger.debug(f"event_log cleanup skipped: {e}")

        state = {
            "status": "healthy" if not issues else "issues_found",
            "issues": issues,
            "fixes": fixes,
            "pool": pool_stats,
            "timestamp": datetime.now().isoformat(),
        }

        # 持久化
        with pool.connection() as c:
            c.execute(
                "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
                "VALUES (?,?,?)",
                ("immune", json.dumps(state, ensure_ascii=False), datetime.now().isoformat())
            )

        self._state.metadata["last_patrol"] = state
        return state

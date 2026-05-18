"""伏羲 v1.0 — LifecycleManagerEngine 生命周期管理引擎"""
import logging
from datetime import datetime, timedelta

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.lifecycle_manager")


@register_engine("lifecycle_manager", experimental=True)
class LifecycleManagerEngine(CognitiveEngine):
    """生命周期管理引擎 — 状态机管理记忆生命周期

    状态转换链:
    active -> fading -> archived -> summarized -> deleted

    - active: 正常使用中
    - fading: 长期未访问，开始衰减
    - archived: 归档存储，降低优先级
    - summarized: 压缩摘要，释放存储
    - deleted: 软删除，等待彻底清理
    """
    name = "lifecycle_manager"
    priority = 4
    interval = 600  # 每10分钟检查一次
    experimental = True

    # 状态转移阈值
    FADING_THRESHOLD_DAYS = 30      # 30天未访问 -> fading
    ARCHIVE_THRESHOLD_DAYS = 90     # 90天未访问 -> archived
    SUMMARIZE_THRESHOLD_DAYS = 180  # 180天 -> summarized
    DELETE_THRESHOLD_DAYS = 365     # 365天 -> deleted

    def run(self) -> dict:
        pool = get_pool()
        transitions = []

        # Step 1: active -> fading
        fading = self._transition(pool, "active", "fading", self.FADING_THRESHOLD_DAYS)
        transitions.append({"from": "active", "to": "fading", "count": fading})

        # Step 2: fading -> archived
        archived = self._transition(pool, "fading", "archived", self.ARCHIVE_THRESHOLD_DAYS)
        transitions.append({"from": "fading", "to": "archived", "count": archived})

        # Step 3: archived -> summarized
        summarized = self._transition(pool, "archived", "summarized", self.SUMMARIZE_THRESHOLD_DAYS)
        transitions.append({"from": "fading", "to": "summarized", "count": summarized})

        # Step 4: summarized -> deleted (soft delete)
        deleted = self._transition(pool, "summarized", "deleted", self.DELETE_THRESHOLD_DAYS)
        transitions.append({"from": "summarized", "to": "deleted", "count": deleted})

        # Step 5: 彻底删除 old deleted 记录（超过2倍的删除阈值）
        purged = self._purge_deleted(pool)

        # Step 6: 重置访问后的状态回升
        revived = self._revive_accessed(pool)

        return {
            "status": "completed",
            "transitions": transitions,
            "purged": purged,
            "revived": revived,
            "timestamp": datetime.now().isoformat(),
        }

    def _transition(self, pool, from_state: str, to_state: str, days_threshold: int) -> int:
        """执行状态转移"""
        threshold_date = (datetime.now() - timedelta(days=days_threshold)).isoformat()
        rows = pool.fetchall(
            "SELECT id FROM items "
            "WHERE lifecycle_state=? AND updated_at < ? AND archived=0 "
            "ORDER BY updated_at ASC LIMIT 100",
            (from_state, threshold_date)
        )
        if not rows:
            return 0

        ids = [r["id"] for r in rows]
        count = 0
        with pool.connection() as c:
            for item_id in ids:
                c.execute(
                    "UPDATE items SET lifecycle_state=?, updated_at=? WHERE id=?",
                    (to_state, datetime.now().isoformat(), item_id)
                )
                count += 1

        logger.info(f"[lifecycle] {from_state}->{to_state}: {count} items")
        return count

    def _purge_deleted(self, pool) -> int:
        """彻底删除超过阈值的已删除记录"""
        threshold_date = (datetime.now() - timedelta(days=self.DELETE_THRESHOLD_DAYS * 2)).isoformat()
        rows = pool.fetchall(
            "SELECT id FROM items WHERE lifecycle_state='deleted' AND updated_at < ? LIMIT 100",
            (threshold_date,)
        )
        if not rows:
            return 0

        ids = [r["id"] for r in rows]
        count = 0
        with pool.connection() as c:
            for item_id in ids:
                c.execute("DELETE FROM items WHERE id=?", (item_id,))
                count += 1

        logger.warning(f"[lifecycle] purged {count} permanently deleted items")
        return count

    def _revive_accessed(self, pool) -> int:
        """访问后的状态回升（fading/archived -> active）"""
        recent_threshold = (datetime.now() - timedelta(days=7)).isoformat()
        rows = pool.fetchall(
            "SELECT id FROM items "
            "WHERE lifecycle_state IN ('fading', 'archived') "
            "AND accessed_at > ? AND archived=0 "
            "LIMIT 50",
            (recent_threshold,)
        )
        if not rows:
            return 0

        ids = [r["id"] for r in rows]
        count = 0
        with pool.connection() as c:
            for item_id in ids:
                c.execute(
                    "UPDATE items SET lifecycle_state='active', updated_at=? WHERE id=?",
                    (datetime.now().isoformat(), item_id)
                )
                count += 1

        logger.info(f"[lifecycle] revived {count} items to active")
        return count

    def force_state(self, item_id: int, target_state: str) -> dict:
        """强制将某记录置于指定状态"""
        valid_states = ["active", "fading", "archived", "summarized", "deleted"]
        if target_state not in valid_states:
            return {"error": f"Invalid state: {target_state}"}

        pool = get_pool()
        with pool.connection() as c:
            c.execute(
                "UPDATE items SET lifecycle_state=?, updated_at=? WHERE id=?",
                (target_state, datetime.now().isoformat(), item_id)
            )
        return {"status": "ok", "item_id": item_id, "new_state": target_state}

    def _get_subscriptions(self):
        return {
            "lifecycle.force_state": self._on_force_state,
        }

    def _on_force_state(self, event):
        self._state.metadata.setdefault("_pending_events", []).append({
            "type": "lifecycle.force_state",
            "data": event.data,
        })
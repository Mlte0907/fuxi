"""伏羲 v1.0 — Decay Engine 记忆衰减引擎

基于艾宾浩斯遗忘曲线，定时衰减记忆的 decay_score，
低于底限的记忆自动归档。
"""
import logging

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.memory.decay import cleanup_event_log, decay_all, purge_below_floor

logger = logging.getLogger("fuxi.engine.decay")


@register_engine("decay", experimental=False)
class DecayEngine(CognitiveEngine):
    """记忆衰减引擎

    每12小时运行一次：
    1. 对所有非归档记忆计算新的 decay_score（基于艾宾浩斯曲线）
    2. 清理低于底限的记忆（归档而非删除）
    3. 清理过期的 event_log 条目
    """
    name = "decay"
    priority = 3
    interval = 43200  # 12小时
    tier = "essential"

    def _get_subscriptions(self):
        return {}

    def run(self) -> dict:
        # 1. 批量衰减
        decay_stats = decay_all(dry_run=False)

        # 2. 归档低于底限的记忆
        purge_stats = purge_below_floor(dry_run=False)

        # 3. 清理30天前的 event log
        event_stats = cleanup_event_log(retain_days=30, dry_run=False)

        total = decay_stats.get("total", 0)
        decayed = decay_stats.get("decayed", 0)
        purged = purge_stats.get("purged", 0)

        logger.info(
            f"DecayEngine: {decayed}/{total} decayed, "
            f"{purged} purged below floor, "
            f"{event_stats.get('deleted', 0)} event log entries cleaned"
        )

        return {
            "status": "ok",
            "decay": decay_stats,
            "purge": purge_stats,
            "event_cleanup": event_stats,
        }

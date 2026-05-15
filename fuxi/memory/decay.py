"""伏羲 v1.0 — 艾宾浩斯衰减 + 批量优化"""
import logging
from datetime import datetime

from fuxi.config import config
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.memory.decay")


def decay_all(dry_run: bool = False) -> dict:
    """批量衰减所有非归档记忆，返回统计"""
    pool = get_pool()
    now = datetime.now()

    # 获取所有活跃记忆
    rows = pool.fetchall(
        "SELECT id, importance, decay_score, updated_at "
        "FROM items WHERE archived = 0"
    )

    updates = []
    stats = {"total": len(rows), "decayed": 0, "strengthened": 0,
             "unchanged": 0, "purge_candidates": 0}

    for r in rows:
        new_score, action = _calculate_decay(
            r["decay_score"], r["importance"],
            r["updated_at"], now
        )

        # 检查是否低于底限（候选清理）
        if new_score < config.decay_floor:
            stats["purge_candidates"] += 1

        # 只更新变化显著的
        if abs(new_score - r["decay_score"]) > 0.001:
            updates.append((new_score, now.isoformat(), r["id"]))
            if new_score > r["decay_score"]:
                stats["strengthened"] += 1
            else:
                stats["decayed"] += 1
        else:
            stats["unchanged"] += 1

    # 批量写入
    if updates and not dry_run:
        with pool.connection() as c:
            c.executemany(
                "UPDATE items SET decay_score = ?, updated_at = ? WHERE id = ?",
                updates
            )

    if dry_run:
        logger.info(f"Decay dry-run: {stats}")
    else:
        logger.info(f"Decay: {stats['decayed']} down, {stats['strengthened']} up, "
                    f"{stats['purge_candidates']} below floor")

    return stats


def _calculate_decay(current_score: float, importance: float,
                     updated_at: str, now: datetime) -> tuple:
    """计算单个记忆的新衰减分数"""
    try:
        updated_dt = datetime.fromisoformat(updated_at)
    except (ValueError, TypeError):
        return current_score, "unchanged"

    idle_days = (now - updated_dt).days

    # 基础衰减：艾宾浩斯曲线
    base_decay = config.decay_base ** (idle_days / 7)  # 每周衰减

    # 重要性修正：高重要性记忆衰减更慢（单一修正，避免双重叠加）
    importance_factor = 1.0 - (importance * 0.4)

    # 夜间衰减因子（04:00-06:00 是梦境整理时间，衰减加速）
    hour = now.hour
    night_factor = config.night_decay_factor if 4 <= hour <= 6 else 1.0

    # 长短期增益
    if idle_days < 1:
        # 最近访问过：短期增益
        touch_factor = config.touch_boost_short
    elif idle_days > 30:
        # 很久没访问：长期保护（核心记忆不轻易遗忘）
        touch_factor = config.touch_boost_long
    else:
        touch_factor = 1.0

    new_score = current_score * base_decay * importance_factor * night_factor * touch_factor
    new_score = max(config.decay_floor, min(1.0, new_score))

    if new_score > current_score:
        action = "strengthened"
    elif new_score < current_score:
        action = "decayed"
    else:
        action = "unchanged"

    return round(new_score, 6), action


def get_purge_candidates() -> list:
    """返回即将被清理的记忆 ID 列表（用于回滚快照）"""
    pool = get_pool()
    rows = pool.fetchall(
        "SELECT id FROM items WHERE decay_score < ? AND archived = 0",
        (config.decay_floor,)
    )
    return [r["id"] for r in rows]


def purge_below_floor(dry_run: bool = True) -> dict:
    """清理衰减分低于底限的记忆（归档而非删除）"""
    pool = get_pool()
    rows = pool.fetchall(
        "SELECT id FROM items WHERE decay_score < ? AND archived = 0",
        (config.decay_floor,)
    )

    ids = [r["id"] for r in rows]

    if ids and not dry_run:
        now = datetime.now().isoformat()
        with pool.connection() as c:
            placeholders = ",".join("?" * len(ids))
            c.execute(
                f"UPDATE items SET archived = 1, updated_at = ? WHERE id IN ({placeholders})",
                (now, *ids)
            )

    logger.info(f"Purge: {len(ids)} candidates, dry_run={dry_run}")
    return {"purged": len(ids), "dry_run": dry_run, "ids": ids}


def cleanup_event_log(retain_days: int = 30, dry_run: bool = True) -> dict:
    """清理过期事件日志，防止 event_log 表无限增长"""
    pool = get_pool()
    row = pool.fetchone(
        "SELECT COUNT(*) AS cnt FROM event_log WHERE created_at < datetime('now', ?)",
        (f"-{retain_days} days",)
    )
    count = row["cnt"] if row else 0
    if count > 0 and not dry_run:
        pool.execute(
            "DELETE FROM event_log WHERE created_at < datetime('now', ?)",
            (f"-{retain_days} days",)
        )
    logger.info(f"Event log cleanup: {count} entries older than {retain_days}d, dry_run={dry_run}")
    return {"deleted": count if not dry_run else 0, "candidates": count, "dry_run": dry_run}

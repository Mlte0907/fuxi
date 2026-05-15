"""伏羲 v1.0 — 深度健康检查"""
import logging
import time
from typing import Any

from fuxi.memory.embedding import get_embedding_service
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.observability.health")

_start_time = time.time()


def quick_health_check() -> dict:
    """快速健康检查（<10ms）"""
    return {
        "status": "ok",
        "version": "1.0.0",
        "uptime_seconds": round(time.time() - _start_time),
        "timestamp": time.time()
    }


def deep_health_check() -> dict:
    """深度健康检查（含DB/嵌入/各引擎）"""
    checks: dict[str, Any] = {}

    # DB检查
    try:
        pool = get_pool()
        row = pool.fetchone("SELECT 1 AS ok")
        checks["database"] = "ok" if row and row["ok"] == 1 else "fail"
    except Exception as e:
        checks["database"] = f"fail: {e}"

    # 嵌入服务
    try:
        es = get_embedding_service()
        stats = es.stats
        test_vec = es.embed("health check")
        checks["embedding"] = {
            "status": "ok" if test_vec and len(test_vec) > 0 else "empty",
            **stats
        }
    except Exception as e:
        checks["embedding"] = f"fail: {e}"

    # 内存统计
    try:
        pool = get_pool()
        items = pool.fetchone("SELECT COUNT(*) AS cnt FROM items WHERE archived=0")
        drawers = pool.fetchone("SELECT COUNT(*) AS cnt FROM drawers")
        edges = pool.fetchone("SELECT COUNT(*) AS cnt FROM edges")
        checks["stats"] = {
            "status": "ok",
            "items": items["cnt"] if items else 0,
            "drawers": drawers["cnt"] if drawers else 0,
            "edges": edges["cnt"] if edges else 0,
        }
    except Exception as e:
        checks["stats"] = f"fail: {e}"

    all_ok = all(
        v == "ok" or (isinstance(v, dict) and v.get("status") == "ok")
        for v in checks.values()
    )

    return {
        "status": "ok" if all_ok else "degraded",
        "uptime_seconds": round(time.time() - _start_time),
        "checks": checks,
        "timestamp": time.time()
    }

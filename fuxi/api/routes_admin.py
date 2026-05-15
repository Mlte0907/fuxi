"""伏羲 v1.0 — /api/v2/admin 路由"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from fuxi.config import config
from fuxi.memory.embedding import get_embedding_service
from fuxi.models import ApiResponse
from fuxi.store.backup import backup_db, list_backups, restore_db
from fuxi.store.migrations import get_schema_version

logger = logging.getLogger("fuxi.api.admin")
router = APIRouter(tags=["admin"])


@router.get("/admin/stats")
async def get_stats():
    from fuxi.engines.base import get_engine_registry
    from fuxi.kernel.event_bus import get_event_bus
    from fuxi.store.connection import get_pool
    pool = get_pool()
    items = pool.fetchone("SELECT COUNT(*) AS cnt FROM items WHERE archived=0")
    drawers = pool.fetchone("SELECT COUNT(*) AS cnt FROM drawers")
    edges = pool.fetchone("SELECT COUNT(*) AS cnt FROM edges")
    agents = pool.fetchone("SELECT COUNT(*) AS cnt FROM agent_views")
    es = get_embedding_service()

    engines = get_engine_registry().list_all()
    loop = get_engine_registry().get("cognitive_loop")
    event_bus = get_event_bus()
    from fuxi.kernel.working_memory import get_working_memory
    wm = get_working_memory()

    # 差分隐私统计
    from fuxi.privacy.differential import DPStatistics
    dp = DPStatistics(epsilon=0.5)

    items_dp = dp.dp_count(items["cnt"] if items else 0, "items_count")
    edges_dp = dp.dp_count(edges["cnt"] if edges else 0, "edges_count")

    return ApiResponse.ok({
        "items": items["cnt"] if items else 0,
        "items_dp": items_dp,
        "drawers": drawers["cnt"] if drawers else 0,
        "edges": edges["cnt"] if edges else 0,
        "edges_dp": edges_dp,
        "agents": agents["cnt"] if agents else 0,
        "embedding": es.stats,
        "schema_version": get_schema_version(),
        "engines": {
            "total": len(engines),
            "running": sum(1 for e in engines if e["running"]),
            "scheduler": loop._state.metadata.get("last_loop", {}).get("attention", {}) if loop else None,
        },
        "event_bus": event_bus.stats,
        "working_memory": wm.stats,
        "config": {
            "port": config.port,
            "wm_capacity": config.wm_capacity,
            "embed_dim": config.embed_dim,
            "decay_base": config.decay_base,
        }
    })


@router.post("/admin/backup")
async def create_backup(force: bool = False):
    result = backup_db(force=force)
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["error"])
    return ApiResponse.ok(result)


@router.get("/admin/backups")
async def list_backup_files():
    return ApiResponse.ok(list_backups())


@router.post("/admin/restore/{filename}")
async def restore_backup(filename: str):
    path = config.backup_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    result = restore_db(str(path))
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["error"])
    return ApiResponse.ok(result)


@router.post("/admin/acl/grant")
async def grant_permission(agent_id: str, permissions: str = "read",
                           domains: Optional[str] = None, role: Optional[str] = None):
    from fuxi.auth.acl import get_acl
    acl = get_acl()
    perm_list = [p.strip() for p in permissions.split(",")]
    domain_list = [d.strip() for d in (domains or "").split(",") if d.strip()]
    acl.grant(agent_id, perm_list, agent_domains=domain_list, role=role)
    return ApiResponse.ok({"status": "ok", "agent_id": agent_id})


# ── 经验银行 ──

@router.get("/admin/experiences")
async def list_experiences(task_type: Optional[str] = None, limit: int = 50, offset: int = 0):
    from fuxi.store.connection import get_pool
    pool = get_pool()
    if task_type:
        rows = pool.fetchall(
            "SELECT * FROM experience_bank WHERE task_type=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (task_type, limit, offset)
        )
    else:
        rows = pool.fetchall(
            "SELECT * FROM experience_bank ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
    return ApiResponse.ok({"experiences": [dict(r) for r in rows], "count": len(rows)})


@router.post("/admin/experiences")
async def create_experience(exp: dict):
    import uuid

    from fuxi.store.connection import get_pool
    pool = get_pool()
    exp_id = str(uuid.uuid4())
    pool.execute(
        """INSERT INTO experience_bank
        (id, task_type, input_desc, reasoning_summary, conclusion, outcome,
         agent_id, skill_name, trigger_keywords, quality_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (exp_id, exp.get("task_type", ""), exp.get("input_desc", ""),
         exp.get("reasoning_summary", ""), exp.get("conclusion", ""),
         exp.get("outcome", "unknown"), exp.get("agent_id", ""),
         exp.get("skill_name", ""),
         __import__("json").dumps(exp.get("trigger_keywords", [])),
         exp.get("quality_score", 0.5))
    )
    return ApiResponse.ok({"id": exp_id, "status": "ok"})


@router.patch("/admin/experiences/{exp_id}")
async def update_experience(exp_id: str, updates: dict):
    from fuxi.store.connection import get_pool
    pool = get_pool()
    row = pool.fetchone("SELECT id FROM experience_bank WHERE id=?", (exp_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Experience not found")
    allowed = ("review_status", "reviewed_by", "review_note",
              "skill_name", "skill_file_path", "quality_score")
    for key in allowed:
        if key in updates:
            val = updates[key]
            if key == "review_status" and val not in ("pending", "approved", "rejected"):
                raise HTTPException(status_code=400, detail=f"Invalid review_status: {val}")
            pool.execute(f"UPDATE experience_bank SET {key}=? WHERE id=?", (val, exp_id))
    return ApiResponse.ok({"id": exp_id, "status": "ok"})


@router.get("/admin/experiences/{exp_id}")
async def get_experience(exp_id: str):
    from fuxi.store.connection import get_pool
    pool = get_pool()
    row = pool.fetchone("SELECT * FROM experience_bank WHERE id=?", (exp_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Experience not found")
    return ApiResponse.ok(dict(row))

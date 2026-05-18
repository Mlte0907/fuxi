"""伏羲 v1.0 — /api/v2/memories 路由"""
import json
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus
from fuxi.memory.decay import decay_all, purge_below_floor
from fuxi.memory.embedding import get_embedding_service
from fuxi.memory.ingestion import remember
from fuxi.memory.retrieval import _row_to_dict, clear_recall_cache, recall, recall_by_ids, recall_context
from fuxi.memory.search import get_search_stats, search
from fuxi.models import ApiResponse
from fuxi.store.connection import get_pool
from fuxi.store.repository import ItemRepository

logger = logging.getLogger("fuxi.api.memories")
router = APIRouter(tags=["memories"])


# 允许读取的 drawer 映射（agent_id -> 可读 drawer 列表，None 表示无限制）
_DRAWER_READ_PERMISSIONS = {
    "main": None,  # main 可读所有
    "xuanwu": None,
    "qinglong": ["default", "qinglong_view", "longterm"],
    "baihu": ["default", "baihu_tasks", "longterm"],
    "zhuque": ["default", "zhuque_reports", "longterm"],
    "fuxi": None,
    "anonymous": ["default"],  # 未认证只能读 default
}


def _check_drawer_read_permission(agent_id: str, drawer_id: str) -> bool:
    """检查 agent 是否有权读取指定 drawer"""
    if agent_id in _DRAWER_READ_PERMISSIONS and _DRAWER_READ_PERMISSIONS[agent_id] is None:
        return True  # 无限制可读
    allowed = _DRAWER_READ_PERMISSIONS.get(agent_id, ["default"])
    return drawer_id in allowed or drawer_id == "default"


class RememberRequest(BaseModel):
    text: Optional[str] = Field(None, min_length=1, max_length=50000)
    raw_text: Optional[str] = Field(None, min_length=1, max_length=50000)
    drawer_id: str = "default"
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: List[str] = []
    source: str = "direct"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_by: str = "system"
    facts: str = ""
    collaborators: List[str] = []
    emotion_valence: float = Field(default=0.0, ge=-1.0, le=1.0)

    @property
    def effective_text(self) -> str:
        t = self.text or self.raw_text
        if not t:
            raise ValueError("text or raw_text is required")
        return t


class UpdateMemoryRequest(BaseModel):
    text: Optional[str] = Field(None, min_length=1, max_length=50000)
    facts: Optional[str] = None
    importance: Optional[float] = Field(None, ge=0.0, le=1.0)
    tags: Optional[List[str]] = None
    drawer_id: Optional[str] = None
    emotion_valence: Optional[float] = Field(None, ge=-1.0, le=1.0)
    collaborators: Optional[List[str]] = None


@router.post("/memories")
async def create_memory(req: RememberRequest, request: Request):
    # Drawer 级别权限：只有 main/xuanwu 可以写入 longterm 抽屉
    agent_id = request.headers.get("X-Agent-ID", "")
    if req.drawer_id == "longterm" and agent_id not in ("main", "xuanwu"):
        raise HTTPException(
            status_code=403,
            detail=f"Agent '{agent_id}' cannot write to longterm drawer"
        )
    try:
        item_id = remember(
            raw_text=req.effective_text, drawer_id=req.drawer_id,
            importance=req.importance, tags=req.tags,
            source=req.source, confidence=req.confidence,
            created_by=req.created_by, facts=req.facts,
            collaborators=req.collaborators,
            emotion_valence=req.emotion_valence
        )
        get_event_bus().publish(Event(
            type="memory.created",
            data={"id": item_id, "drawer_id": req.drawer_id, "importance": req.importance, "source": req.source},
            priority=EventPriority.NORMAL,
            source="api:memory",
        ))
        return ApiResponse.ok({"id": item_id, "status": "ok"})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Remember failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/memories")
async def list_memories(
    query: Optional[str] = None, drawer_id: Optional[str] = None, limit: int = 10,
    offset: int = 0, agent_id: Optional[str] = None, min_importance: float = 0.0,
    sort_by: str = "relevance", request: Request = None
):
    # Drawer 级别权限：检查 agent 是否有权访问该 drawer
    calling_agent = request.headers.get("X-Agent-ID", agent_id or "anonymous") if request else agent_id or "anonymous"
    if drawer_id and not _check_drawer_read_permission(calling_agent, drawer_id):
        raise HTTPException(
            status_code=403,
            detail=f"Agent '{calling_agent}' cannot read from drawer '{drawer_id}'"
        )
    return ApiResponse.ok(recall(query=query, drawer_id=drawer_id, limit=limit,
                                offset=offset, agent_id=agent_id,
                                min_importance=min_importance, sort_by=sort_by))


@router.get("/memories/search")
@router.post("/memories/search")
async def search_memories(
    q: str = Query(..., min_length=1), drawer_id: Optional[str] = None,
    limit: int = 20, offset: int = 0, agent_id: Optional[str] = None,
    tags: Optional[str] = None, min_score: float = 0.0, request: Request = None
):
    calling_agent = request.headers.get("X-Agent-ID", agent_id or "anonymous") if request else agent_id or "anonymous"
    if drawer_id and not _check_drawer_read_permission(calling_agent, drawer_id):
        raise HTTPException(
            status_code=403,
            detail=f"Agent '{calling_agent}' cannot search in drawer '{drawer_id}'"
        )
    tag_list = tags.split(",") if tags else None
    # Publish search signal for BehaviorCollector (BUG-002 fix)
    get_event_bus().publish(Event(
        type="search.query",
        data={"query": q, "drawer_id": drawer_id},
        priority=EventPriority.LOW,
        source="api:memory",
    ))
    return ApiResponse.ok(search(query=q, drawer_id=drawer_id, limit=limit,
                                offset=offset, agent_id=agent_id,
                                tags=tag_list, min_score=min_score))


@router.get("/memories/context")
async def get_context(drawer_id: Optional[str] = None, budget: Optional[int] = None):
    return ApiResponse.ok(recall_context(drawer_id=drawer_id, budget=budget))

@router.get("/memories/{item_id}")
async def get_memory(item_id: str):
    """获取单条记忆详情"""
    rows = recall_by_ids([item_id])
    if not rows:
        raise HTTPException(status_code=404, detail="Memory not found")
    return ApiResponse.ok(_row_to_dict(rows[0]))


@router.post("/memories/decay")
async def trigger_decay(dry_run: bool = False):
    return ApiResponse.ok(decay_all(dry_run=dry_run))


@router.post("/memories/purge")
async def trigger_purge(dry_run: bool = True):
    return ApiResponse.ok(purge_below_floor(dry_run=dry_run))


@router.get("/memories/search/stats")
async def search_stats():
    return ApiResponse.ok(get_search_stats())


@router.delete("/memories/cache")
async def clear_cache():
    clear_recall_cache()
    return ApiResponse.ok({"status": "cache_cleared"})

@router.delete("/memories/{item_id}")
async def delete_memory(item_id: str):
    """软删除单条记忆（设置 archived=1）"""
    repo = ItemRepository()
    existing = repo.get(item_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Memory not found")
    repo.delete(item_id, soft=True)
    # 同时删除相关边和关联数据（FTS5 由 items_fts_archive 触发器自动清理）
    pool = get_pool()
    pool.execute("DELETE FROM edges WHERE source_id=? OR target_id=?", (item_id, item_id))
    pool.execute("DELETE FROM agent_views WHERE item_id=?", (item_id,))
    pool.execute("DELETE FROM shared_memories WHERE item_id=?", (item_id,))
    return ApiResponse.ok({"status": "deleted", "id": item_id})


@router.put("/memories/{item_id}")
async def update_memory(item_id: str, req: UpdateMemoryRequest):
    """更新记忆 — 支持部分字段更新，自动写入版本快照"""

    repo = ItemRepository()
    existing = repo.get(item_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Memory not found")

    # 保存版本快照
    try:
        pool = get_pool()
        pool.execute(
            "INSERT INTO version_snapshots (item_id, version, raw_text, facts, importance, tags, updated_at) "
            "VALUES (?, COALESCE((SELECT MAX(version) FROM version_snapshots WHERE item_id=?), 0) + 1, ?, ?, ?, ?, ?)",
            (item_id, item_id,
             existing.get("raw_text", ""),
             existing.get("facts", ""),
             existing.get("importance", 0.5),
             json.dumps(existing.get("tags", [])) if isinstance(existing.get("tags"), list) else str(existing.get("tags", "")),
             datetime.now().isoformat())
        )
    except Exception as e:
        logger.warning(f"Version snapshot failed (non-fatal): {e}")

    # 构建更新字段
    update_fields = {}
    for field in ("text", "facts", "importance", "tags", "drawer_id",
                  "emotion_valence", "collaborators"):
        val = getattr(req, field, None)
        if val is not None:
            if field == "text":
                update_fields["raw_text"] = val
            else:
                update_fields[field] = val

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    # 如果文本变化，重新生成嵌入向量
    if "raw_text" in update_fields:
        try:
            embed_svc = get_embedding_service()
            vec = embed_svc.embed(update_fields["raw_text"])
            if vec:
                update_fields["embedding"] = json.dumps(vec)
        except Exception as e:
            logger.warning(f"Re-embed on update failed (non-fatal): {e}")

    update_fields["updated_at"] = datetime.now().isoformat()
    update_fields["version"] = (existing.get("version", 1) or 1) + 1
    success = repo.update(item_id, **update_fields)
    if not success:
        raise HTTPException(status_code=500, detail="Update failed")

    # 返回更新后的记忆
    updated = repo.get(item_id)
    return ApiResponse.ok(_row_to_dict(updated))


# ── 批量导入/导出 ──

class BatchImportRequest(BaseModel):
    items: List[dict] = Field(..., min_length=1, max_length=1000)


@router.post("/memories/batch_import")
async def batch_import(req: BatchImportRequest, request: Request):
    pool = get_pool()
    imported = []
    skipped = 0
    errors = []
    with pool.connection() as conn:
        for i, item in enumerate(req.items):
            if not item.get("text"):
                skipped += 1
                continue
            try:
                item_id = remember(
                    raw_text=item["text"],
                    drawer_id=item.get("drawer_id", "default"),
                    importance=item.get("importance", 0.5),
                    tags=item.get("tags", []),
                    source=item.get("source", "direct"),
                    confidence=item.get("confidence", 1.0),
                    created_by=item.get("created_by", "system"),
                    facts=item.get("facts", ""),
                    collaborators=item.get("collaborators", []),
                    emotion_valence=item.get("emotion_valence", 0.0),
                    conn=conn,
                )
                imported.append({"index": i, "id": item_id})
            except Exception as e:
                errors.append({"index": i, "error": str(e)})
        if errors:
            raise HTTPException(status_code=400, detail={"imported": len(imported), "errors": errors})
    return ApiResponse.ok({
        "imported": len(imported),
        "skipped": skipped,
        "errors": errors,
        "items": imported,
    })


@router.get("/memories/export")
async def export_memories(
    drawer_id: Optional[str] = None,
    format: str = "json",
    limit: int = 10000,
    request: Request = None
):
    calling_agent = request.headers.get("X-Agent-ID", "anonymous") if request else "anonymous"
    if drawer_id and not _check_drawer_read_permission(calling_agent, drawer_id):
        raise HTTPException(
            status_code=403,
            detail=f"Agent '{calling_agent}' cannot export from drawer '{drawer_id}'"
        )
    pool = get_pool()
    if drawer_id:
        rows = pool.fetchall(
            "SELECT * FROM items WHERE archived=0 AND drawer_id=? ORDER BY created_at DESC LIMIT ?",
            (drawer_id, limit)
        )
    else:
        rows = pool.fetchall(
            "SELECT * FROM items WHERE archived=0 ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
    results = [dict(r) for r in rows]
    if format == "csv":
        import csv
        import io
        buf = io.StringIO()
        if results:
            writer = csv.DictWriter(buf, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        return ApiResponse.ok({"csv": buf.getvalue(), "count": len(results)})
    return ApiResponse.ok({"memories": results, "count": len(results)})


# ── 事件日志查询 ──

@router.get("/memories/events")
async def query_events(
    event_type: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    from fuxi.store.connection import get_pool
    pool = get_pool()
    where = []
    params: list = []
    if event_type:
        where.append("event_type=?")
        params.append(event_type)
    if source:
        where.append("source=?")
        params.append(source)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    params.extend([limit, offset])
    rows = pool.fetchall(
        f"SELECT * FROM event_log {clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        tuple(params),
    )
    return ApiResponse.ok({"events": [dict(r) for r in rows], "count": len(rows)})


class JudgeRequest(BaseModel):
    task_type: str = ""
    task_description: str = ""
    output_summary: str = ""
    agent_id: str = ""
    auto_apply: bool = False
    raw_text: str = ""
    drawer_override: Optional[str] = None


@router.post("/memory/judge")
async def judge_memory_value(req: JudgeRequest):
    """LLM 判断任务产出是否值得写入长期记忆

    返回 A/B/C 分类及理由。若 auto_apply=True 则自动写入对应抽屉。
    """
    from fuxi.memory.judge import get_memory_judge

    judge = get_memory_judge()
    result = judge.evaluate(
        task_type=req.task_type,
        task_description=req.task_description,
        output_summary=req.output_summary,
        agent_id=req.agent_id,
    )

    response = {
        "verdict": result.verdict.value,
        "reasoning": result.reasoning,
        "confidence": result.confidence,
        "suggested_tags": result.suggested_tags,
        "suggested_importance": result.suggested_importance,
    }

    if req.auto_apply and req.raw_text:
        applied = judge.apply_verdict(
            result,
            raw_text=req.raw_text,
            agent_id=req.agent_id,
            drawer_override=req.drawer_override,
        )
        response["applied"] = applied

    return ApiResponse.ok(response)


@router.get("/memory/judge/history")
async def get_judge_history(limit: int = Query(20, ge=1, le=100)):
    """获取记忆判断历史"""
    from fuxi.memory.judge import get_memory_judge
    judge = get_memory_judge()
    history = judge.history
    return ApiResponse.ok({
        "history": history[-limit:],
        "count": len(history),
    })

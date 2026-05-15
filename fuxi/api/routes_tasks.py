"""伏羲 v1.0 — /api/v2/tasks 任务跟踪路由"""
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from fuxi.models import ApiResponse
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.api.tasks")
router = APIRouter(prefix="/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    assignee: str = "main"
    parent_id: Optional[str] = None
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    status: str = "PENDING"
    result_summary: str = ""


class UpdateTaskRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    assignee: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[float] = Field(None, ge=0.0, le=1.0)
    result_summary: Optional[str] = None


@router.post("")
async def create_task(req: CreateTaskRequest):
    task_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    pool = get_pool()
    pool.execute(
        "INSERT INTO task_tracking (task_id, parent_id, title, assignee, status, progress, result_summary, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (task_id, req.parent_id, req.title, req.assignee, req.status, req.progress, req.result_summary, now, now)
    )
    return ApiResponse.ok({"task_id": task_id, "status": req.status})


@router.get("")
async def list_tasks(
    assignee: Optional[str] = None,
    status: Optional[str] = None,
    parent_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    pool = get_pool()
    clauses = []
    params: list = []
    if assignee:
        clauses.append("assignee=?")
        params.append(assignee)
    if status:
        clauses.append("status=?")
        params.append(status)
    if parent_id:
        clauses.append("parent_id=?")
        params.append(parent_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.extend([limit, offset])
    rows = pool.fetchall(
        f"SELECT * FROM task_tracking {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
        tuple(params)
    )
    return ApiResponse.ok({"tasks": [dict(r) for r in rows], "count": len(rows)})


@router.get("/{task_id}")
async def get_task(task_id: str):
    pool = get_pool()
    row = pool.fetchone("SELECT * FROM task_tracking WHERE task_id=?", (task_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return ApiResponse.ok(dict(row))


@router.get("/children/{parent_id}")
async def get_subtasks(parent_id: str):
    pool = get_pool()
    rows = pool.fetchall(
        "SELECT * FROM task_tracking WHERE parent_id=? ORDER BY created_at ASC",
        (parent_id,)
    )
    return ApiResponse.ok({"tasks": [dict(r) for r in rows], "count": len(rows)})


@router.patch("/{task_id}")
async def update_task(task_id: str, req: UpdateTaskRequest):
    pool = get_pool()
    existing = pool.fetchone("SELECT * FROM task_tracking WHERE task_id=?", (task_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    updates = {}
    for field in ("title", "assignee", "status", "progress", "result_summary"):
        val = getattr(req, field, None)
        if val is not None:
            updates[field] = val

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates["updated_at"] = datetime.now().isoformat()
    sets = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [task_id]

    pool.execute(f"UPDATE task_tracking SET {sets} WHERE task_id=?", values)
    updated = pool.fetchone("SELECT * FROM task_tracking WHERE task_id=?", (task_id,))
    return ApiResponse.ok(dict(updated))


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    pool = get_pool()
    row = pool.fetchone("SELECT * FROM task_tracking WHERE task_id=?", (task_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    pool.execute("DELETE FROM task_tracking WHERE task_id=?", (task_id,))
    return ApiResponse.ok({"status": "deleted", "task_id": task_id})


@router.get("/stats/summary")
async def task_summary():
    pool = get_pool()
    by_status = {}
    for status in ("PENDING", "RUNNING", "DONE", "FAILED", "BLOCKED"):
        row = pool.fetchone(
            "SELECT COUNT(*) AS cnt FROM task_tracking WHERE status=?", (status,)
        )
        by_status[status] = row["cnt"] if row else 0
    total = sum(by_status.values())
    return ApiResponse.ok({"total": total, "by_status": by_status})

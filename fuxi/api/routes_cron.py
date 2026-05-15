"""伏羲 v1.0 — /api/v2/cron 路由（Cron 调度 API）"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from fuxi.cron.parser import parse_nl_to_cron, validate_cron
from fuxi.cron.scheduler import get_cron_scheduler
from fuxi.models import ApiResponse

logger = logging.getLogger("fuxi.api.cron")
router = APIRouter(tags=["cron"])


class AddCronTaskRequest(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    cron_expression: str = ""
    nl_schedule: str = ""
    agent_id: str = ""
    instruction: str = ""
    description: str = ""


class UpdateCronTaskRequest(BaseModel):
    name: str = None
    cron_expression: str = None
    agent_id: str = None
    instruction: str = None
    description: str = None
    enabled: bool = None


@router.get("/cron/tasks")
async def list_cron_tasks(enabled_only: bool = True):
    scheduler = get_cron_scheduler()
    tasks = scheduler.list_tasks(enabled_only=enabled_only)
    return ApiResponse.ok({"tasks": tasks, "count": len(tasks)})


@router.post("/cron/tasks")
async def add_cron_task(req: AddCronTaskRequest):
    scheduler = get_cron_scheduler()
    try:
        if req.nl_schedule:
            scheduler.add_from_nl(
                task_id=req.task_id, name=req.name, nl_schedule=req.nl_schedule,
                agent_id=req.agent_id, instruction=req.instruction,
                description=req.description
            )
        elif req.cron_expression:
            scheduler.add_task(
                task_id=req.task_id, name=req.name, cron_expression=req.cron_expression,
                agent_id=req.agent_id, instruction=req.instruction,
                description=req.description
            )
        else:
            raise HTTPException(status_code=400, detail="cron_expression or nl_schedule required")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ApiResponse.ok({"task_id": req.task_id, "status": "created"})


@router.patch("/cron/tasks/{task_id}")
async def update_cron_task(task_id: str, req: UpdateCronTaskRequest):
    scheduler = get_cron_scheduler()
    updates = {}
    if req.name is not None:
        updates["name"] = req.name
    if req.cron_expression is not None:
        updates["cron_expression"] = req.cron_expression
    if req.agent_id is not None:
        updates["agent_id"] = req.agent_id
    if req.instruction is not None:
        updates["instruction"] = req.instruction
    if req.description is not None:
        updates["description"] = req.description
    if req.enabled is not None:
        updates["enabled"] = 1 if req.enabled else 0
    success = scheduler.update_task(task_id, **updates)
    if not success:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return ApiResponse.ok({"task_id": task_id, "status": "updated"})


@router.delete("/cron/tasks/{task_id}")
async def delete_cron_task(task_id: str):
    scheduler = get_cron_scheduler()
    success = scheduler.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return ApiResponse.ok({"task_id": task_id, "status": "deleted"})


@router.post("/cron/parse")
async def parse_schedule(text: str):
    """解析自然语言调度表达式"""
    expr = parse_nl_to_cron(text)
    if not expr:
        raise HTTPException(status_code=400, detail=f"Cannot parse: {text}")
    return ApiResponse.ok({"text": text, "cron_expression": expr, "valid": validate_cron(expr)})

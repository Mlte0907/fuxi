"""伏羲 v1.0 — /api/v2/collaboration 路由"""
import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from fuxi.agent.collaboration import CollaborationBus
from fuxi.models import ApiResponse

logger = logging.getLogger("fuxi.api.collaboration")
router = APIRouter(tags=["collaboration"])
bus = CollaborationBus()


class BroadcastRequest(BaseModel):
    from_agent: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=50000)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class PipelineRequest(BaseModel):
    chain: List[str] = Field(..., min_length=1, max_length=20)
    message: str = Field(..., min_length=1, max_length=50000)
    importance: float = Field(default=0.7, ge=0.0, le=1.0)


class NegotiateRequest(BaseModel):
    agents: List[str] = Field(..., min_length=2, max_length=20)
    topic: str = Field(..., min_length=1, max_length=5000)


@router.post("/collaboration/broadcast")
async def broadcast_message(req: BroadcastRequest):
    try:
        result = bus.broadcast(req.from_agent, req.message, req.importance)
        return ApiResponse.ok(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/collaboration/pipeline")
async def pipeline_execute(req: PipelineRequest):
    try:
        result = bus.pipeline(req.chain, req.message, req.importance)
        return ApiResponse.ok(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/collaboration/negotiate")
async def negotiate_topic(req: NegotiateRequest):
    try:
        result = bus.negotiate(req.agents, req.topic)
        return ApiResponse.ok(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

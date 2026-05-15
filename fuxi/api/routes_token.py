"""伏羲 v1.0 — /api/v2/token Token 消耗追踪端点"""
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from fuxi.models import ApiResponse

logger = logging.getLogger("fuxi.api.token")
router = APIRouter(tags=["token"])

_token_counts: dict = defaultdict(lambda: {
    "input_tokens": 0, "output_tokens": 0, "cache_read": 0, "cache_write": 0, "requests": 0
})
_lock = threading.Lock()
_window_seconds = 3600 * 24
_window_start = time.time()


class TokenRecord(BaseModel):
    agent_id: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    requests: int = 1


@router.post("/token/budget")
async def record_token_budget(record: TokenRecord):
    key = f"{record.agent_id}:{record.model}"
    with _lock:
        _token_counts[key]["input_tokens"] += record.input_tokens
        _token_counts[key]["output_tokens"] += record.output_tokens
        _token_counts[key]["cache_read"] += record.cache_read
        _token_counts[key]["cache_write"] += record.cache_write
        _token_counts[key]["requests"] += record.requests
    return ApiResponse.ok({"status": "recorded"})


@router.get("/token/budget")
async def get_token_budget(agent_id: Optional[str] = None, model: Optional[str] = None):
    with _lock:
        data = dict(_token_counts)
    results = []
    for key, stats in data.items():
        a_id, m = key.split(":", 1)
        if agent_id and a_id != agent_id:
            continue
        if model and m != model:
            continue
        total = stats["input_tokens"] + stats["output_tokens"]
        results.append({
            "agent_id": a_id, "model": m,
            "input_tokens": stats["input_tokens"], "output_tokens": stats["output_tokens"],
            "cache_read": stats["cache_read"], "cache_write": stats["cache_write"],
            "total_tokens": total, "requests": stats["requests"],
            "avg_tokens_per_request": round(total / max(stats["requests"], 1)),
        })
    return ApiResponse.ok({
        "window_seconds": _window_seconds,
        "window_start": datetime.fromtimestamp(_window_start).isoformat(),
        "records": sorted(results, key=lambda x: x["total_tokens"], reverse=True)
    })


@router.delete("/token/budget")
async def clear_token_budget():
    with _lock:
        _token_counts.clear()
    return ApiResponse.ok({"status": "cleared"})

"""伏羲 v1.0 — /api/v2/profile 路由（用户档案 API）"""
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fuxi.models import ApiResponse
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.api.profile")
router = APIRouter(tags=["profile"])


class UpdateProfileRequest(BaseModel):
    preferences: Optional[dict] = None
    habits: Optional[list] = None
    taboos: Optional[list] = None


@router.get("/profile")
async def get_profile(user_id: str = "default"):
    pool = get_pool()
    row = pool.fetchone(
        "SELECT * FROM user_profile WHERE profile_id = ? OR user_id = ? ORDER BY profile_id = ? DESC LIMIT 1",
        (user_id, user_id, user_id)
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Profile not found: {user_id}")
    d = dict(row)
    for field in ("preferences", "habits", "taboos"):
        try:
            d[field] = json.loads(d[field]) if isinstance(d[field], str) else d[field]
        except (json.JSONDecodeError, TypeError):
            d[field] = {} if field == "preferences" else []
    return ApiResponse.ok(d)


@router.put("/profile")
async def update_profile(req: UpdateProfileRequest, user_id: str = "default"):
    pool = get_pool()
    now = datetime.now().isoformat()
    updates = {}
    if req.preferences is not None:
        updates["preferences"] = json.dumps(req.preferences, ensure_ascii=False)
    if req.habits is not None:
        updates["habits"] = json.dumps(req.habits, ensure_ascii=False)
    if req.taboos is not None:
        updates["taboos"] = json.dumps(req.taboos, ensure_ascii=False)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updated_at"] = now

    cols = list(updates.keys())
    vals = list(updates.values())
    sets = ", ".join(f"{k}=?" for k in updates)
    with pool.connection() as c:
        c.execute(
            f"INSERT INTO user_profile (profile_id, user_id, {', '.join(cols)}) "
            f"VALUES (?, ?, {', '.join('?' for _ in cols)}) "
            f"ON CONFLICT(profile_id) DO UPDATE SET {sets}",
            [user_id, user_id] + vals
        )
    return ApiResponse.ok({"profile_id": user_id, "status": "updated"})


@router.get("/profile/habits")
async def get_habits(user_id: str = "default"):
    profile = await get_profile(user_id)
    return ApiResponse.ok({"habits": profile.data.get("habits", []), "taboos": profile.data.get("taboos", [])})

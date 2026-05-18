from fastapi import APIRouter, Query
from fuxi.models import ApiResponse
from datetime import datetime

router = APIRouter(tags=["test_isolated"])

@router.get("/isolated/test")
async def isolated_test(q: str = Query(...)):
    return ApiResponse.ok({"q": q, "unique_marker": "ISOLATED_TEST_12345"})

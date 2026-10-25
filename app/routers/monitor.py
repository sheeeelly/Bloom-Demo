from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.services import monitor_service

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


@router.get("/seed")
def monitor_seed(category: str = Query("AT"), week: str = Query("")) -> dict[str, Any]:
    return monitor_service.build_monitor(category, week or None)

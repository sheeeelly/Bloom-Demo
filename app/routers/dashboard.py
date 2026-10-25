from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.services import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def get_dashboard(category: str = Query("AT")) -> dict[str, Any]:
    return dashboard_service.build_dashboard(category)

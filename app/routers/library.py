from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.services import library_service

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("/tree")
def library_tree() -> dict[str, Any]:
    return library_service.build_tree()


@router.get("/items")
def library_items(set: str = Query("local:all")) -> dict[str, Any]:
    return library_service.list_items(set)

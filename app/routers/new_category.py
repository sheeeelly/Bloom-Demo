"""
/api/new-category — 新品类开类目薄壳：表单落本地 JSON，不接爬虫/生成。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import config

router = APIRouter(prefix="/api/new-category", tags=["new-category"])

STORE_PATH = Path(config.BASE_DIR) / "data" / "new_category_submissions.json"


class NewCategoryRequest(BaseModel):
    category_name: str = Field(..., min_length=1)
    competitor_site_url: str = Field(..., min_length=1)
    notes: str = ""
    most_popular_hint: str = Field(
        default="Most Popular / Best Sellers",
        description="冷启动锚点提示",
    )


def _load() -> list[dict[str, Any]]:
    if not STORE_PATH.exists():
        return []
    with STORE_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return list(data.get("submissions") or [])


def _save(rows: list[dict[str, Any]]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STORE_PATH.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
                "submissions": rows,
            },
            fh,
            ensure_ascii=False,
            indent=2,
        )
        fh.write("\n")


@router.get("")
def list_submissions() -> dict[str, Any]:
    rows = _load()
    return {"count": len(rows), "submissions": rows}


@router.post("")
def create_submission(payload: NewCategoryRequest) -> dict[str, Any]:
    name = payload.category_name.strip()
    url = payload.competitor_site_url.strip()
    if not name or not url:
        raise HTTPException(status_code=400, detail="品类名与主竞品站 URL 必填")
    row = {
        "id": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        "category_name": name,
        "competitor_site_url": url,
        "most_popular_hint": payload.most_popular_hint.strip() or "Most Popular",
        "notes": payload.notes.strip(),
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "status": "shell_recorded",
        "message": "已记录开类目假设（Demo 壳，未启动爬虫/生成）",
    }
    rows = _load()
    rows.insert(0, row)
    _save(rows[:100])
    return {"ok": True, "submission": row}

"""
/api/selection — 选品页面数据接口
  - GET /api/selection                 默认=AT 上一版种子五商品
  - GET /api/selection/categories      品类下拉
  - GET /api/selection?category=AT     AT=seed_products.json；其它=inputs.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from app.services import gallery_service

router = APIRouter(prefix="/api/selection", tags=["selection"])


@router.get("/categories")
def list_categories() -> dict[str, Any]:
    """爆款合成页品类下拉。"""
    return {"categories": gallery_service.list_category_options()}


@router.get("")
def get_selection(
    category: str | None = Query(default=None, description="品类 id：AT 用爬取种子，其它用 inputs.json"),
) -> dict[str, Any]:
    """返回目标竞品 URL + 商品列表。"""
    cat = (category or "AT").strip() or "AT"
    try:
        data = gallery_service.build_selection_for_category(cat)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"种子数据文件 JSON 格式错误：{exc}") from exc
    except ValidationError as exc:
        raise HTTPException(status_code=500, detail=f"种子数据不符合 SelectionResponse：{exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not data.get("updated_at"):
        data["updated_at"] = datetime.now(timezone.utc).astimezone().isoformat()
    return data

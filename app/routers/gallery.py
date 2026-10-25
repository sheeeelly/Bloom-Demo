"""/api/gallery — 裙装品类预渲染效果页。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import gallery_service

router = APIRouter(prefix="/api/gallery", tags=["gallery"])


class GalleryPrerunItemRequest(BaseModel):
    category_id: str
    item_id: str
    az_product_url: str = ""
    az_product_image_urls: list[str] = Field(default_factory=list)
    competitor_product_id: str = ""
    competitor_product_title: str = ""
    competitor_product_image_url: str = ""
    competitor_detail_images: list[str] = Field(default_factory=list)
    competitor_source_url: str = ""
    competitor_source_site: str = ""
    # 若已有合成结果，可直接登记（脚本预跑完成后调用）
    result_image_urls: list[str] = Field(default_factory=list)
    synthesis_task_id: str = ""
    status: str = "ready"  # ready | failed | pending
    error_message: str = ""
    mode: str = ""


@router.get("")
def get_gallery() -> dict[str, Any]:
    return gallery_service.load_manifest()


@router.get("/inputs")
def get_inputs() -> dict[str, Any]:
    return gallery_service.load_inputs()


@router.post("/items")
def register_item(payload: GalleryPrerunItemRequest) -> dict[str, Any]:
    """登记一条预渲染结果（好坏都保留）。通常由 scripts/prerun_gallery.py 调用。"""
    category_id = payload.category_id.strip()
    item_id = payload.item_id.strip()
    if not category_id or not item_id:
        raise HTTPException(status_code=400, detail="category_id / item_id 必填")

    local_results: list[str] = []
    if payload.result_image_urls:
        try:
            local_results = gallery_service.materialize_result_images(
                category_id=category_id,
                item_id=item_id,
                image_urls=payload.result_image_urls,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"落盘失败: {exc}") from exc

    item = {
        "id": item_id,
        "az_product_url": payload.az_product_url,
        "az_input_images": list(payload.az_product_image_urls or [])[:4],
        "competitor_product_id": payload.competitor_product_id,
        "competitor_product_title": payload.competitor_product_title,
        "competitor_product_image_url": payload.competitor_product_image_url,
        "competitor_detail_images": list(payload.competitor_detail_images or [])[:4],
        "competitor_source_url": payload.competitor_source_url,
        "competitor_source_site": payload.competitor_source_site,
        "result_images": local_results or list(payload.result_image_urls or [])[:4],
        "synthesis_task_id": payload.synthesis_task_id,
        "status": payload.status,
        "error_message": payload.error_message,
        "mode": payload.mode,
    }
    try:
        manifest = gallery_service.upsert_gallery_item(category_id, item)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "item": item, "manifest": manifest}

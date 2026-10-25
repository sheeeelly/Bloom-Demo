"""
/api/gap-fusion — 爆款合成（方案四）· 竞品周报爆点 × AZ 周热销爆点

  - GET  /api/gap-fusion/seed
  - GET  /api/gap-fusion/az-hot
  - POST /api/gap-fusion/product-images
  - POST /api/gap-fusion/select-competitor
  - POST /api/gap-fusion/select-az
  - POST /api/gap-fusion/mutex-hotspots
  - POST /api/gap-fusion/analyze-design-points
  - POST /api/gap-fusion/confirm-design-points
  - POST /api/gap-fusion/preview-prompt
  - POST /api/gap-fusion
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import config
from app.schemas.gap_fusion import (
    GapFusionAnalyzeDesignPointsRequest,
    GapFusionConfirmDesignPointsRequest,
    GapFusionMutexRequest,
    GapFusionPreviewRequest,
    GapFusionRequest,
    GapFusionSelectRequest,
)
from app.schemas.synthesis import SynthesisRequest, SynthesisResult
from app.services import (
    az_hot_service,
    crawler_weekly_adapter,
    dress_attr_catalog,
    gap_fusion_prompt,
    hotspot_mutex,
    product_image_store,
    synthesis_service,
    v13_design_points,
)

router = APIRouter(prefix="/api/gap-fusion", tags=["gap-fusion"])


class GapFusionSelectAzRequest(BaseModel):
    az_id: str = Field(..., description="AZ 热卖商品 ID")
    competitor_id: str | None = None
    category: str = "AT"
    trend_values: list[str] = Field(default_factory=list)
    az_trend_values: list[str] = Field(default_factory=list)
    pinned_product: dict[str, Any] | None = None
    pinned_competitor: dict[str, Any] | None = None


class GapFusionSelectCompetitorBody(GapFusionSelectRequest):
    category: str = "AT"
    trend_values: list[str] = Field(default_factory=list)
    az_trend_values: list[str] = Field(default_factory=list)
    pinned_product: dict[str, Any] | None = None
    skip_az_default: bool = False


class ProductImagesBody(BaseModel):
    product_url: str = ""
    product_id: str = ""
    title: str = ""
    images: list[str] = Field(default_factory=list)


@router.get("/seed")
def get_seed(
    category: str = Query("AT"),
    week: str | None = Query(None),
) -> dict[str, Any]:
    seed = gap_fusion_prompt.load_gap_seed(category=category, week=week)
    v13_ui = Path(config.COMFY_V13_UI_WORKFLOW_PATH)
    runtime = Path(config.COMFY_GAP_FUSION_WORKFLOW_TEMPLATE_PATH)
    trends = gap_fusion_prompt.trend_items(seed)
    az_live = az_hot_service.fetch_az_hot_products(category if category != "全部" else "AT", limit=8)
    az_products = az_hot_service.filter_products_by_category(
        list(
            az_live.get("products")
            or seed.get("az_reference_candidates")
            or []
        ),
        category if category != "全部" else "AT",
    )
    az_trends = gap_fusion_prompt.build_az_trend_hotspots(az_products)
    return {
        "seed": {
            **seed,
            "trend_hotspots": trends,
            "common_gap_attributes": trends,
            "az_trend_hotspots": az_trends,
            "az_reference_candidates": az_products,
        },
        "dimensions": dress_attr_catalog.get_analysis_dimensions_payload(),
        "sources": {
            "crawler": seed.get("source") or {"available": crawler_weekly_adapter.available()},
            "az_hot": az_live.get("meta") or {},
            "data_source": seed.get("data_source"),
        },
        "workflow": {
            "v13_ui_path": str(v13_ui),
            "v13_ui_installed": v13_ui.is_file(),
            "runtime_api_path": str(runtime),
            "runtime_api_installed": runtime.is_file(),
            "note": (
                "爆点+爆点：板A=竞品周报；板B=AZ周热销累加（速度加权，加速度unknown）。"
                "同维互斥后写入工作流 Prompt。"
            ),
        },
    }


@router.get("/az-hot")
def get_az_hot(category: str = Query("AT")) -> dict[str, Any]:
    return az_hot_service.fetch_az_hot_products(category, limit=8)


@router.post("/product-images")
def upsert_product_images(body: ProductImagesBody) -> dict[str, Any]:
    try:
        row = product_image_store.upsert_images(
            product_url=body.product_url,
            product_id=body.product_id,
            images=body.images,
            title=body.title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "product": row}


@router.post("/select-competitor")
def select_competitor(body: GapFusionSelectCompetitorBody) -> dict[str, Any]:
    seed = gap_fusion_prompt.load_gap_seed(category=body.category or "AT")
    try:
        return gap_fusion_prompt.auto_select_for_competitor(
            seed,
            competitor_id=body.competitor_id,
            az_id=body.az_id,
            category=body.category,
            trend_values=body.trend_values or None,
            az_trend_values=body.az_trend_values or None,
            pinned_product=body.pinned_product,
            skip_az_default=body.skip_az_default,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/select-az")
def select_az(body: GapFusionSelectAzRequest) -> dict[str, Any]:
    seed = gap_fusion_prompt.load_gap_seed(category=body.category or "AT")
    try:
        return gap_fusion_prompt.auto_select_for_az(
            seed,
            az_id=body.az_id,
            competitor_id=body.competitor_id,
            category=body.category,
            trend_values=body.trend_values or None,
            az_trend_values=body.az_trend_values or None,
            pinned_product=body.pinned_product,
            pinned_competitor=body.pinned_competitor,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/mutex-hotspots")
def mutex_hotspots(body: GapFusionMutexRequest) -> dict[str, Any]:
    """卡内手勾后：同维互斥（后勾优先）。"""
    return gap_fusion_prompt.apply_manual_mutex(
        body.competitor_points,
        body.az_points,
        last_side=body.last_side,
    )


@router.post("/analyze-design-points")
def analyze_design_points(body: GapFusionAnalyzeDesignPointsRequest) -> dict[str, Any]:
    """竞品+本品视觉分析；auto_select=true 时按爆点语义相似度后台自动勾选。"""
    if not body.competitor_image_urls and not body.competitor_hotspots:
        raise HTTPException(status_code=400, detail="请提供竞品图片或属性以便分析设计点")
    try:
        result = v13_design_points.analyze_pair(
            competitor_image_urls=body.competitor_image_urls,
            product_image_urls=body.product_image_urls,
            competitor_title=body.competitor_title,
            product_title=body.product_title,
            competitor_hotspots=body.competitor_hotspots,
            product_hotspots=body.product_hotspots,
        )
        if body.auto_select:
            match_comp = body.match_competitor_hotspots or body.competitor_hotspots
            match_prod = body.match_product_hotspots or body.product_hotspots
            result = v13_design_points.prepare_auto_selection(
                result,
                competitor_hotspots=match_comp,
                product_hotspots=match_prod,
            )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"设计点分析失败：{exc}") from exc


@router.post("/confirm-design-points")
def confirm_design_points(body: GapFusionConfirmDesignPointsRequest) -> dict[str, Any]:
    """对齐 V13 第3步：确认/跳过设计点选择（含同维互斥）。"""
    selected_ids = list(body.selected_point_ids)
    notices: list[str] = []
    if not body.skip:
        selected_ids, notices = hotspot_mutex.apply_design_point_mutex(
            body.points,
            selected_ids,
            last_point_id=body.last_point_id,
        )
    payload = {
        "points": body.points,
        "selected_point_ids": selected_ids,
        "competitor_summary": body.competitor_summary,
        "product_summary": body.product_summary,
    }
    try:
        result = v13_design_points.validate_selection(payload, skip=body.skip)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["mutex_notices"] = notices
    return result


@router.post("/preview-prompt")
def preview_prompt(body: GapFusionPreviewRequest) -> dict[str, str]:
    prompt = gap_fusion_prompt.build_gap_fusion_prompt(
        gap_tags=body.gap_tags,
        az_gap_tags=body.az_gap_tags,
        competitor_points=body.competitor_points,
        az_points=body.az_points,
        week_label=body.week_label,
        extra_note=body.extra_note,
        competitor_title=body.competitor_title,
        az_title=body.az_title,
        selected_design_points=body.selected_design_points,
        skip_design_selection=body.skip_design_selection,
    )
    return {"prompt": prompt}


@router.post("", response_model=SynthesisResult, status_code=202)
def create_gap_fusion(body: GapFusionRequest) -> SynthesisResult:
    if not body.competitor_product_image_url.strip():
        raise HTTPException(status_code=400, detail="请提供竞品主图 URL")
    if not body.az_product_url.strip():
        raise HTTPException(status_code=400, detail="请提供 AZ 热卖商品 URL")

    prompt = gap_fusion_prompt.build_gap_fusion_prompt(
        gap_tags=body.gap_tags,
        az_gap_tags=body.az_gap_tags,
        competitor_points=body.competitor_points,
        az_points=body.az_points,
        week_label=body.week_label,
        extra_note=body.extra_note,
        competitor_title=body.competitor_product_title,
        az_title=body.az_title,
        selected_design_points=body.selected_design_points,
        skip_design_selection=body.skip_design_selection,
    )

    detail_images = list(body.competitor_detail_images or [])
    if body.competitor_product_image_url and body.competitor_product_image_url not in detail_images:
        detail_images = [body.competitor_product_image_url, *detail_images]
    # 合并本地多图库
    stored = product_image_store.get_images(
        product_url=body.competitor_source_url or "",
        product_id=body.competitor_product_id or "",
        fallback=detail_images,
    )
    if stored:
        detail_images = stored

    selected = list(body.selected_design_points or [])
    add_keywords = [
        str(p.get("keyword") or "")
        for p in selected
        if p.get("source") == "competitor" and p.get("keyword")
    ]
    keep_keywords = [
        str(p.get("keyword") or "")
        for p in selected
        if p.get("source") == "product" and p.get("keyword")
    ]

    payload = SynthesisRequest(
        az_product_url=body.az_product_url,
        az_product_image_urls=list(body.az_product_image_urls or [])[:8],
        competitor_product_id=body.competitor_product_id or "gap-demo-competitor",
        competitor_product_title=body.competitor_product_title
        or body.az_title
        or "爆款合成",
        competitor_product_image_url=detail_images[0] if detail_images else body.competitor_product_image_url,
        competitor_detail_images=detail_images[:8],
        competitor_source_url=body.competitor_source_url,
        competitor_source_site=body.competitor_source_site or "weekly_gap_scheme4",
        intervention_selections={
            "external_hotspots": ", ".join(body.gap_tags),
            "internal_hotspots": ", ".join(body.az_gap_tags),
            "add": ", ".join(add_keywords or body.competitor_points),
            "anchor": ", ".join(keep_keywords or body.az_points),
            "selected_design_point_ids": ", ".join(
                str(p.get("id") or "") for p in selected if p.get("id")
            ),
            "skip_design_selection": "1" if body.skip_design_selection else "0",
        },
        intervention_elements=["external_hotspots", "internal_hotspots", "add", "anchor"],
        intervention_note=body.extra_note,
        intervention_prompt=prompt,
    )
    return synthesis_service.create_synthesis(payload)

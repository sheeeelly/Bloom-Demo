"""方案四 · Gap × AZ 热卖 请求模型（爆点+爆点）。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class GapFusionPreviewRequest(BaseModel):
    gap_tags: list[str] = Field(default_factory=list, description="板 A 竞品周报爆点 label")
    az_gap_tags: list[str] = Field(default_factory=list, description="板 B AZ 周热销爆点 label")
    competitor_points: list[str] = Field(default_factory=list)
    az_points: list[str] = Field(default_factory=list)
    week_label: str = "2026-W27/W30"
    extra_note: str = ""
    competitor_title: str = ""
    az_title: str = ""
    selected_design_points: list[dict[str, Any]] = Field(
        default_factory=list,
        description="V13 已确认设计点（含 keyword/source/description）",
    )
    skip_design_selection: bool = False


class GapFusionSelectRequest(BaseModel):
    competitor_id: str = Field(..., description="周报竞品商品 ID")
    az_id: str | None = Field(default=None, description="AZ 参考款 ID，空则用默认")


class GapFusionAnalyzeDesignPointsRequest(BaseModel):
    competitor_image_urls: list[str] = Field(default_factory=list)
    product_image_urls: list[str] = Field(default_factory=list)
    competitor_title: str = ""
    product_title: str = ""
    competitor_hotspots: list[dict[str, Any]] = Field(default_factory=list)
    product_hotspots: list[dict[str, Any]] = Field(default_factory=list)
    auto_select: bool = Field(
        default=False,
        description="true：按爆点语义相似度后台自动勾选设计点（对用户隐藏 UI）",
    )
    match_competitor_hotspots: list[dict[str, Any]] = Field(
        default_factory=list,
        description="用于语义对齐的竞品侧已勾爆点（含 dim/label）",
    )
    match_product_hotspots: list[dict[str, Any]] = Field(
        default_factory=list,
        description="用于语义对齐的 AZ 侧已勾爆点（含 dim/label）",
    )


class GapFusionConfirmDesignPointsRequest(BaseModel):
    points: list[dict[str, Any]] = Field(default_factory=list)
    selected_point_ids: list[str] = Field(default_factory=list)
    competitor_summary: str = ""
    product_summary: str = ""
    skip: bool = False
    last_point_id: str | None = None


class GapFusionMutexRequest(BaseModel):
    competitor_points: list[dict[str, Any]] = Field(default_factory=list)
    az_points: list[dict[str, Any]] = Field(default_factory=list)
    last_side: Literal["competitor", "az"] = "az"


class GapFusionRequest(BaseModel):
    gap_tags: list[str] = Field(default_factory=list, description="板 A 竞品周报爆点")
    az_gap_tags: list[str] = Field(default_factory=list, description="板 B AZ 周热销爆点")
    competitor_points: list[str] = Field(
        default_factory=list, description="竞品侧 External hotspots（互斥后）"
    )
    az_points: list[str] = Field(
        default_factory=list, description="AZ 侧 Internal hotspots（互斥后）"
    )
    selected_design_points: list[dict[str, Any]] = Field(
        default_factory=list,
        description="V13 可视化选中的设计点（竞品/本品 keyword）",
    )
    skip_design_selection: bool = False
    week_label: str = "2026-W27/W30"
    extra_note: str = ""

    competitor_product_id: str = "gap-demo-competitor"
    competitor_product_title: str = "Competitor · Gap Source"
    competitor_product_image_url: str = Field(..., description="竞品主图直链")
    competitor_detail_images: list[str] = Field(default_factory=list)
    competitor_source_url: str = ""
    competitor_source_site: str = ""

    az_product_url: str = Field(..., description="AZ 热卖详情页")
    az_product_image_urls: list[str] = Field(default_factory=list)
    az_title: str = ""

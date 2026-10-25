"""相似款参考卡 · 数据合同。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


OverlapRisk = Literal["high", "medium", "low", "unknown"]


class QueryAttribute(BaseModel):
    key: str
    label: str
    value: str
    source: str = Field(
        default="",
        description="属性来源：synthesis_report（合成/设计报告中的新款属性）",
    )


class GeneratedAttributesResponse(BaseModel):
    """结果页「生成款基本属性」：仅解析报告，不调用 az-copilot。"""

    task_id: str
    status: Literal["ready", "empty", "error"] = "ready"
    hint: str = ""
    attributes: list[QueryAttribute] = Field(default_factory=list)
    error_message: str | None = None


class SimilarPeerCard(BaseModel):
    goods_id: str = ""
    product_id: str = ""
    name: str = ""
    url: str = ""
    image_url: str = ""
    price: float | int | str | None = None
    category_name: str = ""
    color: str = ""
    attributes: dict[str, list[str]] = Field(default_factory=dict)
    matched_attributes: list[str] = Field(default_factory=list)
    overlap_score: float = Field(0.0, description="0–1，属性重叠比例")
    overlap_risk: OverlapRisk = "unknown"
    overlap_label: str = ""
    excluded: bool = False
    source: Literal["az_copilot", "demo_fallback"] = "az_copilot"


class SimilarPeersResponse(BaseModel):
    task_id: str
    status: Literal["ready", "empty", "degraded", "error"] = "ready"
    source: Literal["az_copilot", "demo_fallback"] = "az_copilot"
    query_text: str = ""
    query_attributes: list[QueryAttribute] = Field(default_factory=list)
    hint: str = ""
    answer_preview: str = ""
    elapsed_ms: int = 0
    peers: list[SimilarPeerCard] = Field(default_factory=list)
    excluded_goods_ids: list[str] = Field(default_factory=list)
    error_message: str | None = None


class ExcludePeerRequest(BaseModel):
    goods_id: str = Field(..., description="要排除/取消排除的 AZ goods_id")
    excluded: bool = True


class ExcludePeerResponse(BaseModel):
    task_id: str
    goods_id: str
    excluded: bool
    excluded_goods_ids: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)

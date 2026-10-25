"""
选品数据模型定义。

字段参照 competitor_project_optimized 爬虫项目对 babyboofashion.com 的实际采集结果设计
（见 baselines/atelier/babyboo_baseline.json），后续接入更多站点数据后可按需增减字段，
不影响 /api/selection 的响应结构。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Product(BaseModel):
    id: str = Field(..., description="商品唯一标识，对应爬虫数据的 product_skc_key")
    title: str = Field(..., description="商品标题")
    image_url: str = Field(..., description="商品主图地址")
    price: float = Field(..., description="商品价格（现价）")
    currency: str = Field(default="USD", description="价格币种")
    source_site: str = Field(..., description="竞品站点名称，如 Babyboo Fashion")
    source_url: str = Field(..., description="商品详情页原始链接")
    rank: int | None = Field(default=None, description="在目标竞品页面排序方式下的排名，暂无数据时为空")
    fabric: str | None = Field(default=None, description="面料，暂无数据时为空")
    length: str | None = Field(default=None, description="裙长，如 Maxi / Midi")
    neckline: str | None = Field(default=None, description="领型")
    silhouette: str | None = Field(default=None, description="廓形 / 版型")
    aesthetic_tag: str | None = Field(default=None, description="设计标签（竞品采集）")
    color_name: str | None = Field(default=None, description="颜色名")
    crawled_at: str | None = Field(default=None, description="采集时间（ISO 格式），暂无数据时为空")
    detail_images: list[str] | None = Field(
        default=None,
        description="商品详情页图片列表（来自 Shopify 商品 JSON 的 images 字段），暂无数据时为空",
    )


class SelectionResponse(BaseModel):
    target_url: str = Field(..., description="目标竞品（列表页）URL")
    products: list[Product] = Field(..., description="该竞品下的商品列表")
    updated_at: str = Field(..., description="本批数据的更新时间（ISO 格式）")

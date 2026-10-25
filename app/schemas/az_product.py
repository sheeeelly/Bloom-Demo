"""AZ 商品图查询相关数据模型（对应 /api/az-product-images 接口）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AzProductImage(BaseModel):
    url: str = Field(..., description="图片完整地址")
    color: str = Field(default="", description="颜色")
    direction: int = Field(default=0, description="方向：1正面 2侧面 3背面 4口袋 5细节，其余为0")
    direction_label: str = Field(default="other", description="方向分组：front/side/back/other，用于前端分组展示")
    direction_text: str = Field(default="其他", description="方向中文标签")
    img_id: str = Field(default="", description="图片 ID")
    img_type: str = Field(default="", description="图片类型")
    sequence: int = Field(default=0, description="同颜色下的排序序号")
    idx: int = Field(default=0, description="遍历序号")
    is_plus: bool = Field(default=False, description="是否为大码图")


class AzProductImagesResponse(BaseModel):
    ok: bool = Field(..., description="是否查询成功")
    error: str | None = Field(default=None, description="失败原因，ok=false 时展示给用户")

    goods_id: str = Field(default="", description="商品数字 ID")
    goods_style_id: str = Field(default="", description="款式 ID")
    goods_name: str = Field(default="", description="商品名（URL slug）")
    shown_goods_name: str = Field(default="", description="商品展示名称")
    color_key: str = Field(default="", description="默认/当前颜色")
    img_type: str = Field(default="", description="图片类型")

    image_count: int = Field(default=0, description="图片总数")
    images: list[AzProductImage] = Field(default_factory=list, description="图片列表")

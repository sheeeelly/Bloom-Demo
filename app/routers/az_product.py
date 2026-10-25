"""
/api/az-product-images — 查询 AZ 商品图库（不下载图片）

前端在「AZ 爆款商品 URL」输入框后点击「确认」时调用，
用于在合成之前预览该商品的完整图片列表。
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.az_product import AzProductImagesResponse
from app.services import az_product_client

router = APIRouter(prefix="/api", tags=["az-product"])


@router.get("/az-product-images", response_model=AzProductImagesResponse)
def get_az_product_images(
    url: str = Query(..., min_length=1, max_length=2000, description="AZ 商品详情页 URL 或纯数字商品 ID"),
) -> AzProductImagesResponse:
    payload = az_product_client.fetch_az_product_images(url)
    return AzProductImagesResponse(**payload)

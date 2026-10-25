"""
AZ 商品图查询客户端。

移植自《商品图下载-技术交接文档》中 `fetch_first_screen_by_goods_id.py` 的核心逻辑，
调用 Azazie 商城 `first-screen` 接口获取商品图库元数据（仅查询，不下载图片）。

用法：
  - 输入完整商品详情页 URL → `fetch_product_link_image_data(url)`
  - 输入纯数字商品 ID       → `fetch_goods_image_data(goods_id)`
  - 不确定输入类型         → `fetch_az_product_images(raw_input)`（自动判断）
"""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

logger = logging.getLogger(__name__)

FIRST_SCREEN_URL = "https://mall-product.azazie.com/1.0/product/first-screen"

DEFAULT_QUERY: dict[str, str] = {
    "activityVerison": "b",
    "sodGalleryVersion": "b",
    "colorSortVersion": "a",
    "fabricVersion": "b",
    "reviewVersion": "b",
    "get_power_for_final_sale": "1",
    "viewVersion": "b",
    "supportstocksales": "1",
    "supportshipsnow": "1",
}

DEFAULT_HEADERS: dict[str, str] = {
    "x-countrycode": "US",
    "x-languagecode": "en",
    "x-app": "pc",
    "x-project": "azazie",
    "accept": "application/json, text/plain, */*",
    "origin": "https://www.azazie.com",
    "referer": "https://www.azazie.com/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}

REQUEST_TIMEOUT_SECONDS = 15

# direction 字段含义：1=正面 2=侧面 3=背面 4=口袋 5=细节，其余归为「其他」
_DIRECTION_LABELS: dict[int, dict[str, str]] = {
    1: {"text": "正面", "group": "front"},
    2: {"text": "侧面", "group": "side"},
    3: {"text": "背面", "group": "back"},
    4: {"text": "口袋", "group": "other"},
    5: {"text": "细节", "group": "other"},
}
_DEFAULT_DIRECTION = {"text": "其他", "group": "other"}

_GOODS_ID_RE = re.compile(r"^\d{5,20}$")
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_COLOR_NORMALIZE_RE = re.compile(r"[\s\-_]+")


class AzProductFetchError(RuntimeError):
    """调用 Azazie first-screen 接口失败（网络异常、风控拦截、响应格式异常等）。"""


def _empty_result(error: str) -> dict[str, Any]:
    return {"ok": False, "error": error, "images": [], "image_count": 0}


def parse_product_link(url: str) -> dict[str, str]:
    """解析 Azazie 商品详情页 URL，提取 first-screen 接口所需的业务参数。

    支持格式：
      https://www.azazie.com/products/{goods_name}/{goods_style_id}?color=xxx&size=s
      https://www.azazie.com/gb/products/{goods_name}/{goods_style_id}?q=1234567
    """
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]

    country = ""
    offset = 0
    if path_parts and len(path_parts[0]) == 2 and path_parts[0].isalpha():
        country = path_parts[0].upper()
        offset = 1

    if offset >= len(path_parts) or path_parts[offset].lower() != "products":
        raise ValueError("无法识别的 Azazie 商品链接：缺少 /products/ 路径")

    goods_name = path_parts[offset + 1] if offset + 1 < len(path_parts) else ""
    goods_style_id = path_parts[offset + 2] if offset + 2 < len(path_parts) else ""
    if not goods_name:
        raise ValueError("无法从链接中解析出商品名称")

    qs = parse_qs(parsed.query or "")
    color = (qs.get("color") or [""])[0]
    size = (qs.get("size") or [""])[0]
    goods_id = (qs.get("q") or qs.get("goods_id") or [""])[0]

    return {
        "url": url,
        "goods_name": goods_name,
        "goods_style_id": goods_style_id,
        "goods_id": goods_id,
        "color": color,
        "dress_type": "dress",
        "size": size,
        "country": country or "US",
    }


def _request_first_screen_json(params: dict[str, str], headers: dict[str, str]) -> dict[str, Any]:
    try:
        resp = requests.get(
            FIRST_SCREEN_URL,
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise AzProductFetchError(f"请求 Azazie 商品接口失败：{exc}") from exc

    if resp.status_code == 403 or "Just a moment" in resp.text[:500]:
        raise AzProductFetchError("商品接口被风控拦截（403），请稍后重试")
    if resp.status_code != 200:
        raise AzProductFetchError(f"商品接口返回异常状态码：{resp.status_code}")

    try:
        return resp.json()
    except ValueError as exc:
        raise AzProductFetchError("商品接口返回内容无法解析为 JSON（可能被风控拦截）") from exc


def preferred_gallery_prefix(image_info: dict[str, Any]) -> str:
    """按清晰度优先级选取 CDN 前缀：browserPrefix(/h/) > browserPrefix(/o800/) >
    browserPrefix 原值 > originalPrefix > originalMPrefix。"""
    browser_prefix = image_info.get("browserPrefix") or ""
    normalized = browser_prefix.rstrip("/")
    if normalized.endswith("/upimg/h"):
        return browser_prefix
    if normalized.endswith("/upimg/o800"):
        return browser_prefix
    if browser_prefix:
        return browser_prefix
    return image_info.get("originalPrefix") or image_info.get("originalMPrefix") or ""


def collect_gallery_urls(data: dict[str, Any]) -> list[dict[str, Any]]:
    """遍历 imageInfo.goodsGallery（按颜色分组），输出结构化图片列表。"""
    image_info = data.get("imageInfo") or {}
    prefix = preferred_gallery_prefix(image_info)
    gallery = image_info.get("goodsGallery") or {}

    images: list[dict[str, Any]] = []
    for color, color_data in gallery.items():
        color_images = (color_data or {}).get("images") or []
        for idx, img in enumerate(color_images, start=1):
            direction = img.get("direction") or 0
            direction_meta = _DIRECTION_LABELS.get(direction, _DEFAULT_DIRECTION)
            img_url = img.get("imgUrl") or ""
            full_url = f"{prefix}{img_url}" if img_url and prefix else img_url
            images.append(
                {
                    "url": full_url,
                    "color": color,
                    "direction": direction,
                    "direction_label": direction_meta["group"],
                    "direction_text": direction_meta["text"],
                    "img_id": str(img.get("imgId") or ""),
                    "img_type": img.get("imgType") or "",
                    "sequence": img.get("sequence") or idx,
                    "idx": idx,
                    "is_plus": bool(img.get("isPlus")),
                }
            )
    return images


def _normalize_color(color: str) -> str:
    return _COLOR_NORMALIZE_RE.sub("", color or "").lower()


def _filter_images_by_color(images: list[dict[str, Any]], color_key: str) -> list[dict[str, Any]]:
    """只保留与 color_key 一致的图片。

    first-screen 接口在请求的颜色不是商品默认色时，goodsGallery 会同时返回
    「请求颜色」与「defaultColor」两组图片（实测：?color=lilac 请求会连带返回
    default 的 agave 图库），如果不过滤会把两个颜色的图片混在一起展示。
    """
    if not color_key or not images:
        return images

    target = _normalize_color(color_key)
    filtered = [img for img in images if _normalize_color(img.get("color", "")) == target]

    # 兜底：若归一化后一张都匹配不上（接口异常等极端情况），宁可展示全部也不要空列表
    if not filtered:
        logger.warning("color filter matched 0 images, fallback to unfiltered list, color_key=%s", color_key)
        return images
    return filtered


def _extract_payload(payload: dict[str, Any], link_info: dict[str, str] | None = None) -> dict[str, Any]:
    if payload.get("code") not in (0, None):
        return _empty_result(payload.get("msg") or "商品接口返回失败")

    data = payload.get("data") or {}
    base_info = data.get("baseInfo") or {}
    link_info = link_info or {}
    images = collect_gallery_urls(data)
    color_key = base_info.get("colorReal") or base_info.get("defaultColor") or link_info.get("color") or ""
    images = _filter_images_by_color(images, color_key)

    return {
        "ok": True,
        "error": None,
        "goods_id": str(base_info.get("goodsId") or link_info.get("goods_id") or ""),
        "goods_style_id": str(base_info.get("goodsStyleId") or link_info.get("goods_style_id") or ""),
        "goods_name": base_info.get("goodsName") or link_info.get("goods_name") or "",
        "shown_goods_name": base_info.get("shownGoodsName") or "",
        "color_key": color_key,
        "img_type": base_info.get("imgType") or "",
        "image_count": len(images),
        "images": images,
    }


def fetch_product_link_image_data(url: str) -> dict[str, Any]:
    """输入完整商品详情页 URL，解析并查询图库数据。"""
    try:
        link_info = parse_product_link(url)
    except ValueError as exc:
        return _empty_result(str(exc))

    params = dict(DEFAULT_QUERY)
    params["goods_name"] = link_info["goods_name"]
    if link_info["goods_style_id"]:
        params["goods_style_id"] = link_info["goods_style_id"]
    if link_info["goods_id"]:
        params["goods_id"] = link_info["goods_id"]
    if link_info["color"]:
        params["color"] = link_info["color"]
    if link_info["size"]:
        params["size"] = link_info["size"]
    params["dress_type"] = link_info["dress_type"]

    headers = dict(DEFAULT_HEADERS)
    headers["x-countrycode"] = link_info["country"]

    try:
        payload = _request_first_screen_json(params, headers)
    except AzProductFetchError as exc:
        logger.warning("fetch_product_link_image_data failed url=%s err=%s", url, exc)
        return _empty_result(str(exc))

    return _extract_payload(payload, link_info)


def fetch_goods_image_data(goods_id: str) -> dict[str, Any]:
    """输入纯数字商品 ID，查询图库数据。"""
    params = dict(DEFAULT_QUERY)
    params["goods_id"] = goods_id
    headers = dict(DEFAULT_HEADERS)

    try:
        payload = _request_first_screen_json(params, headers)
    except AzProductFetchError as exc:
        logger.warning("fetch_goods_image_data failed goods_id=%s err=%s", goods_id, exc)
        return _empty_result(str(exc))

    return _extract_payload(payload)


def fetch_az_product_images(raw_input: str) -> dict[str, Any]:
    """入口函数：自动判断输入是商品链接还是纯数字 ID，并查询图库数据。"""
    text = (raw_input or "").strip()
    if not text:
        return _empty_result("请输入 AZ 商品详情页 URL")
    if len(text) > 2000:
        return _empty_result("URL 长度超出限制")

    if _URL_RE.match(text):
        return fetch_product_link_image_data(text)
    if _GOODS_ID_RE.match(text):
        return fetch_goods_image_data(text)
    return _empty_result("无法识别输入内容，请输入完整的 Azazie 商品详情页 URL")

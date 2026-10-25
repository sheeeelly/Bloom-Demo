"""
商品多图本地库（简易 JSON）。

爬虫 baseline 通常只有 main_image_url（1 张）。
V13 分析希望 3–8 张：优先读本库；不足时保留商品 URL，供人工补图。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import config


def store_path() -> Path:
    return Path(getattr(config, "PRODUCT_IMAGE_STORE_PATH", "")) or (
        Path(config.BASE_DIR) / "data" / "product_image_store.json"
    )


def _load() -> dict[str, Any]:
    path = store_path()
    if not path.is_file():
        return {"version": 1, "products": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "products": {}}
    if not isinstance(data, dict):
        return {"version": 1, "products": {}}
    data.setdefault("products", {})
    return data


def _save(data: dict[str, Any]) -> None:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _key(product_url: str = "", product_id: str = "") -> str:
    pid = (product_id or "").strip()
    if pid:
        return f"id:{pid}"
    url = (product_url or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().removeprefix("www.")
    path = re.sub(r"/+$", "", parsed.path or "")
    return f"url:{host}{path}"


def get_images(
    *,
    product_url: str = "",
    product_id: str = "",
    fallback: list[str] | None = None,
) -> list[str]:
    data = _load()
    key = _key(product_url, product_id)
    row = (data.get("products") or {}).get(key) or {}
    images = [str(x).strip() for x in (row.get("images") or []) if str(x).strip()]
    if images:
        return images[:8]
    fb = [str(x).strip() for x in (fallback or []) if str(x).strip()]
    return fb[:8]


def upsert_images(
    *,
    product_url: str = "",
    product_id: str = "",
    images: list[str],
    title: str = "",
) -> dict[str, Any]:
    key = _key(product_url, product_id)
    if not key:
        raise ValueError("product_url or product_id required")
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in images:
        url = str(raw or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        cleaned.append(url)
        if len(cleaned) >= 8:
            break
    data = _load()
    products = data.setdefault("products", {})
    prev = products.get(key) or {}
    products[key] = {
        "product_url": product_url or prev.get("product_url") or "",
        "product_id": product_id or prev.get("product_id") or "",
        "title": title or prev.get("title") or "",
        "images": cleaned,
    }
    _save(data)
    return products[key]


def ensure_main_image(
    *,
    product_url: str,
    product_id: str,
    main_image_url: str,
    title: str = "",
) -> list[str]:
    """若库中无图，用主图占位写入，便于后续人工补齐到 3–8 张。"""
    existing = get_images(product_url=product_url, product_id=product_id)
    if existing:
        return existing
    main = (main_image_url or "").strip()
    if not main:
        return []
    row = upsert_images(
        product_url=product_url,
        product_id=product_id,
        images=[main],
        title=title,
    )
    return list(row.get("images") or [])

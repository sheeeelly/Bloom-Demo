"""品类效果页：读/写预渲染 gallery manifest。"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import config

logger = logging.getLogger(__name__)

GALLERY_DIR = Path(config.BASE_DIR) / "data" / "gallery"
MANIFEST_PATH = GALLERY_DIR / "manifest.json"
INPUTS_PATH = GALLERY_DIR / "inputs.json"
STATIC_GALLERY_DIR = Path(config.BASE_DIR) / "app" / "static" / "gallery"

DEFAULT_CATEGORIES = [
    {"id": "AT", "label": "Atelier / Formal"},
    {"id": "BD", "label": "Bridesmaid / BD"},
    {"id": "Prom", "label": "Prom"},
    {"id": "MOB", "label": "Mother of the Bride"},
    {"id": "Wedding", "label": "Wedding"},
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def ensure_dirs() -> None:
    GALLERY_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_GALLERY_DIR.mkdir(parents=True, exist_ok=True)
    for cat in DEFAULT_CATEGORIES:
        (STATIC_GALLERY_DIR / cat["id"]).mkdir(parents=True, exist_ok=True)


def load_manifest() -> dict[str, Any]:
    ensure_dirs()
    if not MANIFEST_PATH.exists():
        return {
            "updated_at": "",
            "disclaimer": "预渲染结果如实展示（含好坏），供老板判断该裙装品类是否值得接入。",
            "categories": [{**c, "items": []} for c in DEFAULT_CATEGORIES],
        }
    with MANIFEST_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    # 保证六大类都在
    by_id = {c.get("id"): c for c in data.get("categories") or []}
    categories = []
    for cat in DEFAULT_CATEGORIES:
        existing = by_id.get(cat["id"]) or {**cat, "items": []}
        if "label" not in existing:
            existing["label"] = cat["label"]
        if "items" not in existing:
            existing["items"] = []
        categories.append(existing)
    data["categories"] = categories
    return data


def save_manifest(data: dict[str, Any]) -> None:
    ensure_dirs()
    data["updated_at"] = _now_iso()
    with MANIFEST_PATH.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def load_inputs() -> dict[str, Any]:
    ensure_dirs()
    path = INPUTS_PATH if INPUTS_PATH.exists() else GALLERY_DIR / "inputs.example.json"
    if not path.exists():
        return {"categories": []}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def fetch_bytes(url: str, timeout: float = 60.0) -> bytes | None:
    if not url:
        return None
    try:
        req = Request(url, headers={"User-Agent": "az-bloom-gallery/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (URLError, TimeoutError, OSError) as exc:
        logger.warning("fetch failed url=%s err=%s", url[:120], exc)
        return None


def materialize_result_images(
    *,
    category_id: str,
    item_id: str,
    image_urls: list[str],
    max_images: int = 4,
) -> list[str]:
    """把合成结果图落到 static/gallery/{category}/{item_id}_n.jpg，返回可访问的 /static 路径。"""
    ensure_dirs()
    cat_dir = STATIC_GALLERY_DIR / category_id
    cat_dir.mkdir(parents=True, exist_ok=True)
    local_paths: list[str] = []
    for index, url in enumerate(image_urls[:max_images], start=1):
        content = fetch_bytes(url)
        if not content:
            # 无法下载时仍记录原 URL，前端可直链展示
            local_paths.append(url)
            continue
        filename = f"{item_id}_{index:02d}.jpg"
        dest = cat_dir / filename
        dest.write_bytes(content)
        local_paths.append(f"/static/gallery/{category_id}/{filename}")
    return local_paths


def upsert_gallery_item(category_id: str, item: dict[str, Any]) -> dict[str, Any]:
    manifest = load_manifest()
    for cat in manifest["categories"]:
        if cat["id"] != category_id:
            continue
        items = cat.setdefault("items", [])
        replaced = False
        for i, old in enumerate(items):
            if old.get("id") == item.get("id"):
                items[i] = item
                replaced = True
                break
        if not replaced:
            items.append(item)
        save_manifest(manifest)
        return manifest
    raise ValueError(f"unknown category: {category_id}")


def clear_category_static(category_id: str) -> None:
    path = STATIC_GALLERY_DIR / category_id
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _at_default_az_from_inputs() -> tuple[str, list[str]]:
    """AT 共用上一版默认 AZ（Liorah）；优先读 inputs.json 里 AT 首条预填。"""
    inputs = load_inputs()
    for c in inputs.get("categories") or []:
        if c.get("id") != "AT":
            continue
        items = list(c.get("items") or [])
        if not items:
            break
        first = items[0]
        return (
            str(first.get("az_product_url") or "").strip(),
            list(first.get("az_product_image_urls") or [])[:8],
        )
    return ("", [])


def _seed_product_count() -> int:
    """AT 上一版种子商品数（data/seed_products.json）。"""
    try:
        from app.services.product_repository import SeedFileProductRepository

        return len(SeedFileProductRepository().get_selection().products)
    except Exception:
        return 0


def build_at_selection_from_seed() -> dict[str, Any]:
    """
    AT 品类：沿用上一版爬取种子（五商品完整字段），
    AZ 侧共用默认爆款预填（不随竞品卡切换）。
    """
    from app.services.product_repository import SeedFileProductRepository

    selection = SeedFileProductRepository().get_selection()
    payload = selection.model_dump()
    az_url, az_images = _at_default_az_from_inputs()
    for p in payload.get("products") or []:
        p.setdefault("az_product_url", "")
        p.setdefault("az_product_image_urls", [])
    payload["category_id"] = "AT"
    payload["category_label"] = next(
        (c["label"] for c in DEFAULT_CATEGORIES if c["id"] == "AT"),
        "Atelier / Formal",
    )
    payload["data_source"] = "seed_products"
    payload["default_az_product_url"] = az_url
    payload["default_az_product_image_urls"] = az_images
    return payload


def list_category_options() -> list[dict[str, Any]]:
    """爆款合成页下拉：AT 用种子数，其它品类用 inputs.json 条目数。"""
    inputs = load_inputs()
    options: list[dict[str, Any]] = []
    by_id = {c.get("id"): c for c in (inputs.get("categories") or []) if c.get("id")}
    seed_count = _seed_product_count()
    for cat in DEFAULT_CATEGORIES:
        raw = by_id.get(cat["id"]) or {}
        items = list(raw.get("items") or [])
        if cat["id"] == "AT":
            count = seed_count or len(items)
        else:
            count = len(items)
        options.append(
            {
                "id": cat["id"],
                "label": raw.get("label") or cat["label"],
                "item_count": count,
            }
        )
    return options


def build_selection_for_category(category_id: str) -> dict[str, Any]:
    """
    将某一品类转成选品页结构。
    AT → seed_products.json（五商品完整信息）；其它 → inputs.json。
    """
    cat_id = (category_id or "").strip()
    if not cat_id:
        raise ValueError("category_id 必填")

    if cat_id == "AT":
        return build_at_selection_from_seed()

    inputs = load_inputs()
    raw = None
    for c in inputs.get("categories") or []:
        if c.get("id") == cat_id:
            raw = c
            break
    if raw is None:
        # 允许 DEFAULT 中有、但 inputs 尚未填的品类
        meta = next((c for c in DEFAULT_CATEGORIES if c["id"] == cat_id), None)
        if not meta:
            raise ValueError(f"unknown category: {cat_id}")
        raw = {**meta, "items": []}

    label = raw.get("label") or cat_id
    items = list(raw.get("items") or [])
    products: list[dict[str, Any]] = []
    list_url = ""
    for index, item in enumerate(items, start=1):
        detail = list(item.get("competitor_detail_images") or [])
        main = (item.get("competitor_product_image_url") or "").strip()
        if not main and detail:
            main = detail[0]
        if not list_url:
            list_url = (item.get("competitor_list_url") or "").strip()
        products.append(
            {
                "id": str(item.get("id") or f"{cat_id}-{index}"),
                "title": str(item.get("competitor_product_title") or item.get("id") or f"{cat_id}-{index}"),
                "image_url": main or "",
                "price": 0.0,
                "currency": "USD",
                "source_site": str(item.get("competitor_source_site") or ""),
                "source_url": str(item.get("competitor_source_url") or ""),
                "rank": index,
                "fabric": None,
                "length": None,
                "neckline": None,
                "silhouette": None,
                "aesthetic_tag": None,
                "color_name": None,
                "crawled_at": None,
                "detail_images": detail or ([main] if main else []),
                "az_product_url": str(item.get("az_product_url") or ""),
                "az_product_image_urls": list(item.get("az_product_image_urls") or [])[:8],
            }
        )

    return {
        "category_id": cat_id,
        "category_label": label,
        "target_url": list_url,
        "updated_at": "",
        "data_source": "gallery_inputs",
        "default_az_product_url": "",
        "default_az_product_image_urls": [],
        "products": products,
    }

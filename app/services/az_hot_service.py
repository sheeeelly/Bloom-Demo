"""
AZ 热卖款：优先 AZ Copilot Zendesk Workflow（trending/product_search）。

已实证可用字段：name/url/image_url(单张)/price/sales_volume/silhouette/neckline/fabric/...
多图 3–8：Copilot 当前只回 1 张主图 → 写入 product_image_store，不足则保留商品 URL。

品类硬隔离：选 AT 只保留 Atelier；禁止 BD/伴娘等洗进 AT 池。
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import config
from app.services import az_copilot_client, dress_attr_catalog, product_image_store

logger = logging.getLogger(__name__)

_CATEGORY_PROMPT = {
    "AT": (
        "Show me best selling Azazie Atelier / formal dresses ONLY. "
        "Each product MUST be from Azazie Atelier line (URL or title contains atelier). "
        "Do NOT include bridesmaid, mother of the bride, prom, or wedding gowns. "
        "Prefer high sales volume. Return top 8 products with images and attributes."
    ),
    "BD": (
        "Show me best selling Azazie bridesmaid dresses ONLY. "
        "Do NOT include Atelier formal, MOB, prom, or wedding. "
        "Prefer high sales volume. Return top 8 products with images and attributes."
    ),
    "MOB": (
        "Show me best selling Azazie mother of the bride dresses ONLY. "
        "Return top 8 with images and attributes."
    ),
    "Prom": (
        "Show me best selling Azazie prom / homecoming dresses ONLY. "
        "Do NOT include Atelier formal or bridesmaid. Return top 8 with images and attributes."
    ),
    "Wedding": (
        "Show me best selling Azazie wedding / bridal dresses ONLY. "
        "Return top 8 with images and attributes."
    ),
}

# 品类命中：标题/URL 关键词（小写）
_CATEGORY_INCLUDE: dict[str, tuple[str, ...]] = {
    "AT": ("atelier",),
    "BD": ("bridesmaid",),
    "MOB": ("mother of the bride", "mother-of-the-bride", "mob dress", "mob-"),
    "Prom": ("prom", "homecoming"),
    "Wedding": ("wedding", "bridal"),
}

_CATEGORY_EXCLUDE: dict[str, tuple[str, ...]] = {
    "AT": ("bridesmaid", "mother of the bride", "homecoming", "prom and"),
    "BD": ("atelier", "mother of the bride", "prom and", "wedding dress"),
    "MOB": ("bridesmaid", "atelier", "prom and"),
    "Prom": ("bridesmaid", "atelier formal", "mother of the bride"),
    "Wedding": ("bridesmaid", "prom and homecoming"),
}

_KNOWN_CATEGORIES = ("AT", "BD", "MOB", "Prom", "Wedding", "全部")


def normalize_category(category: str | None) -> str:
    """统一品类键：保留 Prom/Wedding 大小写，禁止把 AT 误写成 at。"""
    raw = (category or "AT").strip() or "AT"
    for key in _KNOWN_CATEGORIES:
        if key.lower() == raw.lower():
            return key
    return raw


def _product_blob(card: dict[str, Any]) -> str:
    parts = [
        str(card.get("title") or card.get("name") or ""),
        str(card.get("product_url") or card.get("url") or ""),
        str(card.get("category_name") or ""),
        str(card.get("cat_name") or ""),
        " ".join(str(x) for x in (card.get("category_ids") or [])),
    ]
    return " ".join(parts).lower()


def matches_category_line(card: dict[str, Any], category: str) -> bool:
    """按品类硬过滤：AT 必须能识别为 Atelier。"""
    cat = normalize_category(category)
    if cat == "全部":
        return True
    blob = _product_blob(card)
    for bad in _CATEGORY_EXCLUDE.get(cat, ()):
        if bad in blob:
            return False
    includes = _CATEGORY_INCLUDE.get(cat, ())
    if not includes:
        return True
    if any(tok in blob for tok in includes):
        return True
    # 已显式打上正确 category_line 且无冲突关键词时放行（种子兜底）
    line = normalize_category(str(card.get("category_line") or ""))
    if line == cat and cat != "AT":
        return True
    # AT：没有 atelier 信号一律拒绝（防伴娘裙洗线）
    if cat == "AT":
        return False
    return line == cat


def filter_products_by_category(
    products: list[dict[str, Any]],
    category: str,
) -> list[dict[str, Any]]:
    cat = normalize_category(category)
    return [p for p in products if matches_category_line(p, cat)]


def _salvage_matching_from_all_caches(category: str, limit: int = 8) -> list[dict[str, Any]]:
    """跨品类缓存捞同口径款（例如 Wedding 桶里误放的 Atelier）。"""
    path = cache_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    pool: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in data.values():
        for card in list((row or {}).get("products") or []):
            pid = str(card.get("id") or card.get("product_url") or card.get("url") or "")
            if not pid or pid in seen:
                continue
            if not matches_category_line(card, category):
                continue
            seen.add(pid)
            fixed = {**card, "category_line": normalize_category(category)}
            pool.append(fixed)
            if len(pool) >= limit:
                return pool
    return pool


def cache_path() -> Path:
    return Path(config.BASE_DIR) / "data" / "az_hot_cache.json"


def _hotspots_from_card(card: dict[str, Any]) -> list[dict[str, Any]]:
    return dress_attr_catalog.hotspots_from_product(
        {
            **(card or {}),
            "dress_length": (card or {}).get("dress_length") or (card or {}).get("dressLength"),
            "color_family": (card or {}).get("color_family") or (card or {}).get("colorFamily"),
        }
    )


def _to_product(card: dict[str, Any], rank: int, category: str) -> dict[str, Any]:
    pid = str(card.get("product_id") or card.get("goods_id") or f"az-{rank}")
    url = str(card.get("url") or "")
    main = str(card.get("image_url") or "")
    images = product_image_store.ensure_main_image(
        product_url=url,
        product_id=pid,
        main_image_url=main,
        title=str(card.get("name") or ""),
    )
    if not images and main:
        images = [main]
    attrs = []
    for key in ("silhouette", "neckline", "fabric", "dress_length"):
        vals = card.get(key) or []
        if isinstance(vals, list) and vals:
            attrs.append(str(vals[0]))
        elif vals:
            attrs.append(str(vals))
    points = _hotspots_from_card(card)
    return {
        "id": pid,
        "title": card.get("name") or pid,
        "image_url": images[0] if images else main,
        "detail_images": images,
        "image_count": len(images),
        "image_policy": (
            "gallery_3_to_8" if len(images) >= 3 else "copilot_main_image_only_need_manual_gallery"
        ),
        "product_url": url,
        "url": url,
        "sales_volume": card.get("sales_volume") or 0,
        "rank": rank,
        "category_line": category,
        "status": "rising" if rank <= 3 else "new",
        "price": card.get("price"),
        "attrs_display": attrs[:4] or [
            str((p.get("label") or p.get("value") or ""))
            for p in points
            if p.get("label") or p.get("value")
        ][:4],
        "hotspot_points": points,
        "source": "az_copilot_zendesk",
        "default_selected": rank == 1,
    }


def _enrich_product_hotspots(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in products or []:
        card = dict(raw)
        card["hotspot_points"] = dress_attr_catalog.merge_hotspots(
            dress_attr_catalog.hotspots_from_product(card),
            card.get("hotspot_points") or [],
        )
        out.append(card)
    return out


def _cache_ttl_sec() -> float:
    return float(getattr(config, "GAP_FUSION_AZ_HOT_CACHE_TTL", 3600) or 3600)


def _save_cache(category: str, products: list[dict[str, Any]]) -> None:
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    data[category] = {
        "products": products,
        "fetched_at": time.time(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_cache_entry(category: str) -> tuple[list[dict[str, Any]], float]:
    """返回 (products, fetched_at_epoch)。无 fetched_at 时用文件 mtime。"""
    path = cache_path()
    if not path.is_file():
        return [], 0.0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], 0.0
    row = data.get(category) or {}
    products = list(row.get("products") or [])
    if not products:
        return [], 0.0
    fetched_at = row.get("fetched_at")
    try:
        ts = float(fetched_at) if fetched_at is not None else path.stat().st_mtime
    except (TypeError, ValueError, OSError):
        ts = path.stat().st_mtime
    return products, ts


def _load_cache(category: str) -> list[dict[str, Any]]:
    products, _ = _load_cache_entry(category)
    return products


def fetch_az_hot_products(
    category: str = "AT",
    *,
    limit: int = 8,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """优先读本地 TTL 缓存；过期或 force_refresh 才打 Copilot（单次约 7–8s）。"""
    cat = normalize_category(category)
    if cat == "全部":
        cat = "AT"
    use_copilot = bool(getattr(config, "GAP_FUSION_USE_COPILOT_HOT", True))
    meta: dict[str, Any] = {
        "category": cat,
        "source": "unavailable",
        "copilot_configured": az_copilot_client.is_configured(),
        "multi_image_auto": False,
        "cache_ttl_sec": _cache_ttl_sec(),
        "note": (
            f"品类={cat}"
            + ("（仅 Atelier）" if cat == "AT" else "")
            + "；Copilot 卡片通常仅 1 张主图；3–8 张详图走 product_image_store。"
        ),
    }
    products: list[dict[str, Any]] = []
    cached, fetched_at = _load_cache_entry(cat)
    cached = filter_products_by_category(cached, cat)
    now = time.time()
    age = (now - fetched_at) if fetched_at else None
    ttl = _cache_ttl_sec()

    if not force_refresh and cached and age is not None and age < ttl:
        meta["source"] = "az_hot_cache"
        meta["cache_age_sec"] = int(age)
        return {"category": cat, "products": _enrich_product_hotspots(cached[:limit]), "meta": meta}

    if use_copilot and az_copilot_client.is_configured():
        prompt = _CATEGORY_PROMPT.get(cat) or _CATEGORY_PROMPT["AT"]
        try:
            result = az_copilot_client.call_zendesk_chat(
                prompt,
                conversation_id=f"bloom_gap_hot_{cat.lower()}",
                timeout=float(getattr(config, "AZ_COPILOT_TIMEOUT", 90)),
            )
            if result.error:
                meta["error"] = result.error
            raw = list(result.products or [])[: max(limit * 2, 8)]
            mapped = [_to_product(card, i + 1, cat) for i, card in enumerate(raw)]
            products = filter_products_by_category(mapped, cat)[:limit]
            dropped = len(mapped) - len(products)
            if dropped:
                meta["filtered_out"] = dropped
                logger.info("AZ 热卖品类过滤 category=%s dropped=%s kept=%s", cat, dropped, len(products))
            if products:
                meta["source"] = "az_copilot_zendesk"
                meta["tools_called"] = result.tools_called
                _save_cache(cat, products)
            elif mapped:
                meta["warning"] = f"Copilot 返回 {len(mapped)} 款均不符合品类 {cat}，已丢弃"
        except Exception as exc:  # noqa: BLE001
            logger.warning("az hot copilot failed: %s", exc)
            meta["error"] = str(exc)

    if not products:
        if cached:
            products = cached[:limit]
            meta["source"] = "az_hot_cache_stale" if age is not None and age >= ttl else "az_hot_cache"
            if age is not None:
                meta["cache_age_sec"] = int(age)
        else:
            salvaged = _salvage_matching_from_all_caches(cat, limit=limit)
            if salvaged:
                products = salvaged
                meta["source"] = "az_hot_cache_salvage"
            else:
                meta["source"] = "empty"

    # 写回净化后的缓存，避免脏伴娘裙继续污染 AT
    if products and cat == "AT":
        _save_cache(cat, products)
    if products:
        from app.services import sales_week_store

        sales_week_store.append_snapshot(cat, products)

    return {"category": cat, "products": products, "meta": meta}

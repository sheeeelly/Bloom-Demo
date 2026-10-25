"""货盘监控：统一网格。站点筛选含竞品 + Azazie；市场放基础筛选；筛选全部多选、无互斥。"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from app.services import az_hot_service, crawler_weekly_adapter, dress_attr_catalog, sales_week_store

_AZAZIE = "Azazie"

# 站点服务市场（对齐选品工作台 Demo；爬虫 SKC 本身无 US/UK/AU 字段）
SITE_MARKETS: dict[str, list[str]] = {
    "Oh Polly": ["UK", "US", "AU"],
    "House of CB": ["UK", "US"],
    "Club L London": ["UK", "US", "AU"],
    "Babyboo Fashion": ["AU", "US"],
    "Hello Molly": ["AU", "US"],
    "Birdy Grey": ["US", "UK", "AU"],
    "Six Stories": ["UK"],
    "Azazie": ["US", "UK", "AU"],
}

_STATUS_LABEL = {
    "new": "上新",
    "rising": "上升",
    "falling": "下降",
    "delisted": "下架",
    "active": "在售",
    "hot": "热销",
}

_DESIGN_KEYS = ("fabric", "silhouette", "neckline", "length", "color", "pattern", "sleeve")

_LENGTH_HINTS = (
    ("Mini", ("mini", "skater")),
    ("Midi", ("midi", "tea length", "knee")),
    ("Maxi", ("maxi", "floor-length", "floor length", "full length")),
)
_SILHOUETTE_HINTS = (
    ("Mermaid", ("mermaid", "trumpet")),
    ("A-Line", ("a-line", "a line", "aline")),
    ("Column", ("column", "straight")),
    ("Sheath", ("sheath",)),
    ("Bodycon", ("bodycon", "body con")),
    ("Fit and Flare", ("fit and flare", "fit & flare", "skater")),
    ("Ball Gown", ("ball gown", "ballgown")),
)
_SLEEVE_HINTS = (
    ("Long Sleeve", ("long sleeve", "long-sleeve")),
    ("Short Sleeve", ("short sleeve", "short-sleeve")),
    ("Sleeveless", ("sleeveless", "no sleeve")),
    ("Spaghetti Straps", ("spaghetti", "strap")),
    ("Cap Sleeve", ("cap sleeve",)),
)
_PATTERN_HINTS = (
    ("Floral", ("floral", "flower", "lily print", "print")),
    ("Sequin", ("sequin",)),
    ("Lace", ("lace",)),
    ("Stripe", ("stripe", "striped")),
    ("Solid", ("solid",)),
)

_PER_SITE_FILL = 16
_MAX_PRODUCTS = 800
_BASELINE_CACHE: dict[str, tuple[float, dict[str, dict[str, Any]]]] = {}


def _parse_categories(category: str | None) -> list[str]:
    parts = [az_hot_service.normalize_category(x) for x in (category or "AT").split(",") if x.strip()]
    cats = [c for c in parts if c in ("AT", "BD")]
    return cats or ["AT"]


def _norm_url(raw: str) -> str:
    text = (raw or "").strip().split("?")[0].split("#")[0].rstrip("/").lower()
    try:
        parsed = urlparse(text)
        return f"{parsed.netloc}{parsed.path}".rstrip("/")
    except ValueError:
        return text


def _discount_label(price: Any, compare_at: Any, discount_type: str = "") -> str:
    dtype = str(discount_type or "").strip()
    if dtype in {"无折扣", "无", "none", "-"}:
        return ""
    try:
        sale = float(price) if price not in (None, "") else None
        orig = float(compare_at) if compare_at not in (None, "") else None
    except (TypeError, ValueError):
        sale, orig = None, None
    if sale and orig and orig > sale:
        off = int(round((1 - sale / orig) * 100))
        if 5 <= off <= 70:
            return f"{off}% OFF"
    if dtype in {"打折", "折扣", "sale"}:
        return "打折"
    return ""


def _status_label(card: dict[str, Any]) -> str:
    if card.get("pool") == "own" and card.get("sales_volume") and card.get("badge") == "热销":
        return "热销"
    key = str(card.get("status") or "active")
    if card.get("lifecycle") == "Delisted" or key in {"delisted", "Delisted"}:
        return "下架"
    if key in {"new", "上新"} or card.get("new_type"):
        if key in {"rising", "falling"}:
            return _STATUS_LABEL.get(key, "上新")
        return "上新"
    return _STATUS_LABEL.get(key, "在售")


def _hint_match(blob: str, pairs: tuple[tuple[str, tuple[str, ...]], ...]) -> str:
    for value, hints in pairs:
        if any(h in blob for h in hints):
            return value
    return ""


def _catalog_value(dim: str, raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    matched = dress_attr_catalog.match_option(dim, text)
    if matched and matched.get("value"):
        return str(matched.get("value"))
    return text


def _clean_attr(raw: Any, dim: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    parts = [p.strip() for p in re.split(r"[/,，;]+", text) if p.strip()]
    skip = {"adjustable strap", "adjustable straps", "strap", "straps"}
    for part in reversed(parts):
        if part.lower() in skip:
            continue
        matched = dress_attr_catalog.match_option(dim, part)
        if matched and matched.get("value"):
            return str(matched.get("value"))
    return _catalog_value(dim, parts[-1]) if parts else ""


def _design_from(card: dict[str, Any], base: dict[str, Any] | None = None) -> dict[str, str]:
    md = (base or {}).get("metadata") or card.get("metadata") or {}
    title = str(card.get("title") or "")
    color = str(card.get("color") or md.get("color_name") or "")
    detail = str((base or {}).get("detail_text") or md.get("detail_text") or "")
    blob = f"{title} {color} {detail} {card.get('attrs_display') or []}".lower()
    fabric = _clean_attr(
        (base or {}).get("fabric_name") or md.get("fabric_name") or card.get("fabric") or "",
        "fabric",
    ) or _catalog_value(
        "fabric",
        _hint_match(
            blob,
            (
                ("Satin", ("satin",)),
                ("Crepe", ("crepe",)),
                ("Chiffon", ("chiffon",)),
                ("Mesh", ("mesh",)),
                ("Lace", ("lace",)),
                ("Sequin", ("sequin",)),
                ("Tulle", ("tulle",)),
                ("Jersey", ("jersey",)),
            ),
        ),
    )
    neckline = _clean_attr(
        (base or {}).get("neckline") or md.get("neckline") or card.get("neckline") or "",
        "neckline",
    )
    length = _clean_attr(
        (base or {}).get("length") or md.get("length") or card.get("length") or "",
        "dressLength",
    ) or _hint_match(blob, _LENGTH_HINTS)
    silhouette = card.get("silhouette") or _hint_match(blob, _SILHOUETTE_HINTS)
    sleeve = _clean_attr(card.get("sleeve") or "", "sleeve") or _hint_match(blob, _SLEEVE_HINTS)
    pattern = card.get("pattern") or _hint_match(blob, _PATTERN_HINTS)
    if "floral" in color.lower() and not pattern:
        pattern = "Floral"
    color_short = re.split(r"[#/]", color)[0].strip() if color else ""
    color_short = re.sub(r"^(SP|sp)\s+", "", color_short).strip()
    return {
        "fabric": str(fabric or "").strip(),
        "silhouette": str(silhouette or "").strip(),
        "neckline": str(neckline or "").strip(),
        "length": str(length or "").strip(),
        "color": color_short or color,
        "pattern": str(pattern or "").strip(),
        "sleeve": str(sleeve or "").strip(),
    }


def _markets_for(site: str) -> list[str]:
    return list(SITE_MARKETS.get(site) or [])


def _slim_card(card: dict[str, Any], *, category: str, base: dict[str, Any] | None = None) -> dict[str, Any]:
    site = crawler_weekly_adapter.canonicalize_site(str(card.get("site") or ""), category)
    pool = "own" if site == _AZAZIE or str(card.get("pool") or "") == "own" else "competitor"
    try:
        price = float(card.get("price")) if card.get("price") not in (None, "") else None
    except (TypeError, ValueError):
        price = (base or {}).get("price")
    try:
        compare_card = float(card.get("compare_at")) if card.get("compare_at") not in (None, "") else None
    except (TypeError, ValueError):
        compare_card = None
    compare_at = compare_card if compare_card and price and compare_card > price else (base or {}).get("compare_at")
    try:
        compare_at = float(compare_at) if compare_at not in (None, "") else None
    except (TypeError, ValueError):
        compare_at = None
    if compare_at and price and compare_at <= price:
        compare_at = None
    discount_type = str((base or {}).get("discount_type") or card.get("discount_type") or "")
    ships = card.get("ships_now")
    if ships is None and base is not None:
        ships = bool(base.get("ships_now"))
    status = str(card.get("status") or (base or {}).get("status") or "active")
    if pool == "own" and card.get("sales_volume") and not card.get("new_type"):
        badge = "热销"
        status_label = "热销"
    else:
        badge = _status_label({**card, "status": status, "pool": pool})
        status_label = badge
        if pool == "competitor" and badge == "热销":
            badge = "在售"
            status_label = "在售"
    design = _design_from(card, base)
    rank = card.get("rank")
    if rank in (None, "") and base:
        rank = base.get("rank")
    try:
        rank_i = int(rank) if rank not in (None, "") else None
    except (TypeError, ValueError):
        rank_i = None
    md = (base or {}).get("metadata") or card.get("metadata") or {}
    attr_src = {
        **card,
        **design,
        "metadata": md,
        "detail_text": card.get("detail_text") or (base or {}).get("detail_text") or md.get("detail_text") or "",
        "fabric_name": card.get("fabric_name") or (base or {}).get("fabric_name") or md.get("fabric_name"),
        "aesthetic_tag": card.get("aesthetic_tag") or (base or {}).get("aesthetic_tag") or md.get("aesthetic_tag"),
        "color_name": card.get("color_name") or card.get("color") or md.get("color_name"),
        "length": card.get("length") or (base or {}).get("length") or md.get("length") or design.get("length"),
        "neckline": card.get("neckline") or (base or {}).get("neckline") or md.get("neckline") or design.get("neckline"),
        "silhouette": card.get("silhouette") or (base or {}).get("silhouette") or md.get("silhouette") or design.get("silhouette"),
        "sleeve": card.get("sleeve") or (base or {}).get("sleeve") or md.get("sleeve") or design.get("sleeve"),
        "waistline": card.get("waistline") or (base or {}).get("waistline") or md.get("waistline"),
        "title": card.get("title") or (base or {}).get("title") or "",
    }
    hotspots = dress_attr_catalog.hotspots_from_product(attr_src)
    dim_fields = dress_attr_catalog.dim_fields_from_hotspots(hotspots)
    out = {
        "id": card.get("id") or (base or {}).get("id"),
        "week": card.get("week") or (base or {}).get("week") or "",
        "site": site,
        "pool": pool,
        "category_line": card.get("category_line") or category,
        "title": card.get("title") or (base or {}).get("title") or "",
        "image_url": card.get("image_url") or card.get("main_image_url") or (base or {}).get("main_image_url") or "",
        "product_url": card.get("product_url") or card.get("url") or (base or {}).get("product_url") or "",
        "status": status,
        "status_label": status_label,
        "badge": badge,
        "discount_label": _discount_label(price, compare_at, discount_type),
        "price": price,
        "compare_at": compare_at,
        "rank": rank_i,
        "rank_delta": card.get("rank_delta") if card.get("rank_delta") not in (None, "") else (base or {}).get("rank_delta"),
        "ships_now": bool(ships),
        "markets": _markets_for(site),
        "sales_volume": card.get("sales_volume"),
        "hot_rank": card.get("hot_rank"),
        "trend_label": card.get("trend_label"),
        "lifecycle": card.get("lifecycle") or ("Delisted" if status == "delisted" else ""),
        "detail_text": attr_src["detail_text"],
        "hotspot_points": hotspots,
        "attrs_display": [
            p.get("label") or p.get("value") for p in hotspots if p.get("label") or p.get("value")
        ][:4],
        **design,
        **{k: v for k, v in dim_fields.items() if v},
    }
    return out


def _facet_options(products: list[dict[str, Any]]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {k: [] for k in _DESIGN_KEYS}
    seen: dict[str, set[str]] = {k: set() for k in _DESIGN_KEYS}
    for p in products:
        for key in _DESIGN_KEYS:
            val = str(p.get(key) or "").strip()
            if not val:
                continue
            low = val.lower()
            if low in seen[key]:
                continue
            seen[key].add(low)
            buckets[key].append(val)
    for key, vals in buckets.items():
        vals.sort(key=lambda x: x.lower())
    return buckets


def _index_baseline(category: str) -> dict[str, dict[str, Any]]:
    folder = crawler_weekly_adapter._baselines_dir(category)
    stamp = folder.stat().st_mtime if folder.is_dir() else 0.0
    hit = _BASELINE_CACHE.get(category)
    if hit and hit[0] == stamp:
        return hit[1]
    idx: dict[str, dict[str, Any]] = {}
    for item in crawler_weekly_adapter._iter_baseline_products(category, include_azazie=True):
        url = _norm_url(str(item.get("product_url") or ""))
        if url:
            idx[url] = item
    _BASELINE_CACHE[category] = (stamp, idx)
    return idx


def _card_from_baseline(item: dict[str, Any], category: str) -> dict[str, Any]:
    raw = {
        **item,
        "image_url": item.get("main_image_url") or "",
        "new_type": "",
    }
    return _slim_card(raw, category=category, base=item)


def _build_for_category(cat: str, week: str | None) -> dict[str, Any]:
    arrivals_feed = crawler_weekly_adapter.load_new_arrivals_feed(cat) or {}
    arrival_rows = [p for p in (arrivals_feed.get("products") or []) if isinstance(p, dict)]
    weeks = list(crawler_weekly_adapter.list_weeks(cat))
    feed_week = str(arrivals_feed.get("week") or "")
    if feed_week and feed_week not in weeks:
        weeks = [feed_week, *weeks]
    use_week = week or feed_week or (weeks[0] if weeks else "")
    baseline_idx = _index_baseline(cat)
    products: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(card: dict[str, Any]) -> None:
        key = _norm_url(str(card.get("product_url") or "")) or str(card.get("id") or "")
        if not key or key in seen:
            return
        seen.add(key)
        products.append(card)

    for row in arrival_rows:
        url = _norm_url(str(row.get("product_url") or row.get("source_url") or ""))
        _add(_slim_card(row, category=cat, base=baseline_idx.get(url)))

    by_site: dict[str, int] = {}
    for p in products:
        by_site[str(p.get("site") or "")] = by_site.get(str(p.get("site") or ""), 0) + 1

    fillers = list(baseline_idx.values())
    fillers.sort(
        key=lambda p: (
            -(float(p.get("rank_change") or 0)),
            float(p.get("rank") or 9999),
        )
    )
    for item in fillers:
        site = str(item.get("site") or "")
        if by_site.get(site, 0) >= _PER_SITE_FILL:
            continue
        card = _card_from_baseline(item, cat)
        before = len(products)
        _add(card)
        if len(products) > before:
            by_site[site] = by_site.get(site, 0) + 1

    hot = az_hot_service.fetch_az_hot_products(cat, limit=16)
    own = sales_week_store.annotate_growth(cat, list(hot.get("products") or []))
    for idx, card in enumerate(own, start=1):
        card = dict(card)
        card["site"] = _AZAZIE
        card["pool"] = "own"
        card["hot_rank"] = idx
        card["badge"] = "热销"
        card["category_line"] = cat
        url = _norm_url(str(card.get("product_url") or card.get("url") or ""))
        slim = _slim_card(card, category=cat, base=baseline_idx.get(url))
        slim["badge"] = "热销"
        slim["status_label"] = "热销"
        slim["sales_volume"] = card.get("sales_volume")
        slim["hot_rank"] = idx
        slim["trend_label"] = card.get("trend_label") or "unknown"
        matched = next((p for p in products if _norm_url(str(p.get("product_url") or "")) == url), None)
        if matched:
            matched.update(
                {
                    "sales_volume": slim.get("sales_volume"),
                    "hot_rank": idx,
                    "trend_label": slim.get("trend_label"),
                    "badge": "热销",
                    "status_label": "热销",
                }
            )
        else:
            _add(slim)

    warnings: list[str] = []
    if cat == "BD" and any(p.get("site") == _AZAZIE and "Default" in str(p.get("id") or "") for p in products):
        warnings.append("BD Azazie 上新含 :::Default 键口径，勿当真实上新爆炸")
    if not arrival_rows:
        warnings.append("本周上新 feed 为空时回退 baseline 涨榜/在售；竞品禁止标热销")

    sites = crawler_weekly_adapter.monitor_sites(cat)
    return {
        "category": cat,
        "week": use_week or feed_week,
        "weeks": weeks,
        "sites": sites,
        "products": products[:_MAX_PRODUCTS],
        "warnings": warnings,
        "kpis": {
            "new": sum(1 for p in products if p.get("status_label") == "上新"),
            "own": sum(1 for p in products if p.get("pool") == "own"),
        },
        "source": arrivals_feed.get("_feed_path"),
        "az_hot_source": (hot.get("meta") or {}).get("source"),
    }


def build_monitor(category: str = "AT", week: str | None = None) -> dict[str, Any]:
    cats = _parse_categories(category)
    bundles = [_build_for_category(cat, week) for cat in cats]
    products: list[dict[str, Any]] = []
    seen: set[str] = set()
    weeks: list[str] = []
    sites: list[str] = []
    warnings: list[str] = []
    for bundle in bundles:
        for p in bundle.get("products") or []:
            key = _norm_url(str(p.get("product_url") or "")) or str(p.get("id") or "")
            if key in seen:
                continue
            seen.add(key)
            products.append(p)
        for w in bundle.get("weeks") or []:
            if w and w not in weeks:
                weeks.append(w)
        for s in bundle.get("sites") or []:
            if s not in sites:
                sites.append(s)
        warnings.extend(bundle.get("warnings") or [])
    if len(products) > _MAX_PRODUCTS:
        products = products[:_MAX_PRODUCTS]
        warnings.append(f"货盘已截断至 {_MAX_PRODUCTS} 款，请加筛选缩小范围")

    own = [p for p in products if p.get("pool") == "own"]
    competitor = [p for p in products if p.get("pool") != "own"]
    week_used = week or (bundles[0].get("week") if bundles else "") or (weeks[0] if weeks else "")
    return {
        "category": ",".join(cats),
        "categories": cats,
        "week": week_used,
        "weeks": weeks,
        "sites": sites,
        "markets": ["US", "UK", "AU"],
        "statuses": ["上新", "上升", "下降", "下架", "在售", "热销"],
        "ships_now_options": ["是", "否"],
        "filter_options": _facet_options(products),
        "source_line": "atelier" if cats == ["AT"] else ("bd" if cats == ["BD"] else "mixed"),
        "rank_semantics_note": "竞品=列表序/上新，禁止称热销；Azazie 热销仅来自 salesVolume",
        "products": products,
        "competitor_products": competitor,
        "own_products": own,
        "data_warnings": warnings,
        "kpis": {
            "total": len(products),
            "new": sum(1 for p in products if p.get("status_label") == "上新"),
            "own": len(own),
        },
        "sources": {
            "new_arrivals_path": bundles[0].get("source") if bundles else None,
            "az_hot": bundles[0].get("az_hot_source") if bundles else None,
        },
    }

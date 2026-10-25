"""
方案四 · 竞品周报爆点 × AZ 周热销爆点（爆点+爆点）→ V13 干预 Prompt。
爆点维度：silhouette / neckline / waistline / fabric / dressLength / colorFamily / features / sleeve
同维互斥见 hotspot_mutex。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import config
from app.services import az_hot_service, crawler_weekly_adapter, dress_attr_catalog, hotspot_mutex


def gaps_path() -> Path:
    return Path(config.BASE_DIR) / "data" / "weekly_gaps" / "w27_w30_demo.json"


def similar_index_path() -> Path:
    return Path(config.BASE_DIR) / "data" / "similar_local_index.json"


def load_gap_seed(category: str = "AT", week: str | None = None) -> dict[str, Any]:
    """优先爬虫周报+baseline；失败回退 demo 种子。"""
    cat = az_hot_service.normalize_category(category)
    if cat == "全部":
        cat = "AT"

    crawled = None
    try:
        crawled = crawler_weekly_adapter.build_seed_from_crawler(
            category=cat,
            week=week,
            limit=48,
        )
    except Exception:  # noqa: BLE001
        crawled = None

    path = gaps_path()
    demo: dict[str, Any] = {}
    if path.is_file():
        try:
            demo = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            demo = {}

    az_candidates: list[dict[str, Any]] = []
    try:
        live = az_hot_service.fetch_az_hot_products(cat, limit=8)
        az_candidates = list(live.get("products") or [])
    except Exception:  # noqa: BLE001
        az_candidates = []
    if not az_candidates and demo.get("az_reference_candidates"):
        # demo 兜底也按品类过滤，避免 AT 页混入 BD 样例
        az_candidates = az_hot_service.filter_products_by_category(
            list(demo.get("az_reference_candidates") or []),
            cat,
        )

    if crawled and (crawled.get("competitor_products") or crawled.get("trend_hotspots")):
        seed = {
            **demo,
            **crawled,
            "az_reference_candidates": az_candidates,
            "data_source": "crawler_weekly",
            "category_line": cat,
        }
        return seed

    if demo:
        out = dict(demo)
        out["data_source"] = "demo_seed"
        out["az_reference_candidates"] = az_candidates or az_hot_service.filter_products_by_category(
            list(demo.get("az_reference_candidates") or []),
            cat,
        )
        out["category_line"] = cat
        return out
    return {
        "trend_hotspots": [],
        "common_gap_attributes": [],
        "competitor_products": [],
        "az_reference_candidates": az_candidates,
        "data_source": "empty",
        "category_line": cat,
    }


def trend_items(seed: dict[str, Any]) -> list[dict[str, Any]]:
    items = seed.get("trend_hotspots") or seed.get("common_gap_attributes") or []
    out: list[dict[str, Any]] = []
    for item in items:
        dim = str(item.get("dim") or "features")
        value = str(item.get("value") or item.get("key") or "").strip()
        label = str(item.get("label") or value).strip()
        if not value:
            continue
        matched = dress_attr_catalog.match_option(dim, value) or dress_attr_catalog.match_option(
            dim, label
        )
        if matched:
            value = str(matched.get("value") or value)
            label = str(matched.get("label") or label)
        count = item.get("count")
        try:
            count_n = int(count) if count is not None else 0
        except (TypeError, ValueError):
            count_n = 0
        out.append(
            {
                "dim": dim,
                "value": value,
                "label": label,
                "count": count_n or item.get("count"),
                "score": item.get("score", count_n),
                "default_checked": item.get(
                    "default_checked",
                    bool(count_n >= 50) if count_n else item.get("default_checked", True),
                ),
                "key": value,
                "board": "competitor",
            }
        )
    return out


def build_az_trend_hotspots(
    products: list[dict[str, Any]],
    *,
    top_n: int = 8,
) -> list[dict[str, Any]]:
    """
    板 B：品类 TopN AZ 热销属性频次累加 × 速度代理（sales_volume × 1/rank）。
    acceleration 无周快照时固定 unknown。
    """
    pool = list(products or [])[: max(1, top_n)]
    # key = (dim, value)
    acc: dict[tuple[str, str], dict[str, Any]] = {}
    for idx, product in enumerate(pool, start=1):
        rank = int(product.get("rank") or idx) or idx
        try:
            sales = float(product.get("sales_volume") or 0)
        except (TypeError, ValueError):
            sales = 0.0
        weight = max(sales, 1.0) * (1.0 / rank)
        for point in product.get("hotspot_points") or product.get("anchor_points") or []:
            dim = str(point.get("dim") or "features").strip() or "features"
            value = str(point.get("value") or point.get("key") or "").strip()
            label = str(point.get("label") or value).strip()
            if not value:
                continue
            matched = dress_attr_catalog.match_option(dim, value) or dress_attr_catalog.match_option(
                dim, label
            )
            if matched:
                value = str(matched.get("value") or value)
                label = str(matched.get("label") or label)
            key = (dim, value)
            row = acc.get(key)
            if not row:
                row = {
                    "dim": dim,
                    "value": value,
                    "label": label,
                    "key": value,
                    "count": 0,
                    "score": 0.0,
                    "velocity_proxy": 0.0,
                    "acceleration": "unknown",
                    "board": "az",
                    "default_checked": False,
                }
                acc[key] = row
            row["count"] = int(row["count"]) + 1
            row["score"] = float(row["score"]) + weight
            row["velocity_proxy"] = float(row["velocity_proxy"]) + weight

    items = sorted(acc.values(), key=lambda x: (-float(x["score"]), -int(x["count"]), x["label"]))
    # 默认勾选：score 前 6 或 score >= 中位偏上
    if items:
        threshold = float(items[min(5, len(items) - 1)]["score"])
        for i, item in enumerate(items):
            item["score"] = round(float(item["score"]), 2)
            item["velocity_proxy"] = round(float(item["velocity_proxy"]), 2)
            item["default_checked"] = i < 6 or float(item["score"]) >= threshold
    return items


def _norm(text: str) -> str:
    return " ".join(str(text or "").strip().lower().replace("_", " ").replace("-", " ").split())


def point_token(point: dict[str, Any]) -> str:
    value = str(point.get("value") or point.get("key") or "").strip()
    label = str(point.get("label") or value).strip()
    dim = str(point.get("dim") or "").strip()
    if dim and value:
        return f"{dim}={value}"
    return label or value


def point_display(point: dict[str, Any]) -> str:
    dim = str(point.get("dim") or "").strip()
    label = str(point.get("label") or point.get("value") or point.get("key") or "").strip()
    if dim and label:
        return f"{dim}:{label}"
    return label


def intersects_trend(point: dict[str, Any], trend_set: set[str]) -> bool:
    candidates = {
        _norm(point.get("value") or ""),
        _norm(point.get("key") or ""),
        _norm(point.get("label") or ""),
    }
    candidates.discard("")
    if not candidates or not trend_set:
        return False
    for c in candidates:
        if c in trend_set:
            return True
        for t in trend_set:
            if c in t or t in c:
                return True
    return False


def auto_check_points(
    points: list[dict[str, Any]],
    trend_values: list[str],
    *,
    link_trends: bool = True,
) -> list[dict[str, Any]]:
    """
    link_trends=True：仅当属性与「已勾选爆点板」相交时勾选（竞品←板A，AZ←板B）。
    link_trends=False：降级按本品 default_checked（板 B 空时用）。
    """
    trend_set = {_norm(x) for x in trend_values if x}
    out: list[dict[str, Any]] = []
    for raw in points or []:
        point = dict(raw)
        dim = str(point.get("dim") or "features")
        raw_value = str(point.get("value") or point.get("key") or point.get("label") or "")
        matched = dress_attr_catalog.match_option(dim, raw_value)
        if matched:
            point["value"] = matched.get("value")
            point["label"] = matched.get("label") or point.get("label") or matched.get("value")
        point["dim"] = dim
        if link_trends:
            point["checked"] = bool(trend_set and intersects_trend(point, trend_set))
        else:
            point["checked"] = bool(point.get("default_checked", True))
        out.append(point)
    return out


def _labels_for_values(trends: list[dict[str, Any]], values: list[str]) -> list[str]:
    value_set = {_norm(x) for x in values if x} | {str(x) for x in values if x}
    labels: list[str] = []
    for t in trends:
        v = str(t.get("value") or "")
        if _norm(v) in {_norm(x) for x in values if x} or v in value_set:
            labels.append(str(t.get("label") or t.get("value") or ""))
    return [x for x in labels if x]


def _default_trend_values(trends: list[dict[str, Any]]) -> list[str]:
    return [
        str(t.get("value") or t.get("key") or "")
        for t in trends
        if t.get("default_checked", True) and (t.get("value") or t.get("key"))
    ]


def find_competitor(
    seed: dict[str, Any],
    product_id: str,
    pinned: dict[str, Any] | None = None,
    category: str = "AT",
) -> dict[str, Any] | None:
    pid = str(product_id or "")
    if not pid:
        return None
    if pinned and str(pinned.get("id") or "") == pid:
        return _coerce_competitor_card(pinned)
    for key in ("competitor_products", "new_arrivals", "products"):
        for item in seed.get(key) or []:
            if str(item.get("id") or "") == pid:
                return _coerce_competitor_card(item)
    try:
        from app.services import monitor_service

        for cat in (category, "AT", "BD"):
            if not cat or cat == "全部":
                continue
            for item in (monitor_service.build_monitor(cat).get("products") or []):
                if str(item.get("id") or "") == pid:
                    return _coerce_competitor_card(item)
    except Exception:
        pass
    return None


def _coerce_competitor_card(raw: dict[str, Any]) -> dict[str, Any]:
    """货盘/爬虫卡 → 爆款合成卡：按 8 维补 hotspot_points，供勾选要保留的属性。"""
    card = dict(raw or {})
    extracted = dress_attr_catalog.hotspots_from_product(card)
    card["hotspot_points"] = dress_attr_catalog.merge_hotspots(
        extracted,
        card.get("hotspot_points") or card.get("anchor_points") or [],
    )
    dims = dress_attr_catalog.dim_fields_from_hotspots(card["hotspot_points"])
    for key, value in dims.items():
        if value and not card.get(key):
            card[key] = value
    if not card.get("attrs_display"):
        card["attrs_display"] = [
            p.get("label") or p.get("value")
            for p in card["hotspot_points"]
            if p.get("label") or p.get("value")
        ][:4]
    if not card.get("image_url"):
        card["image_url"] = card.get("main_image_url") or ""
    if not card.get("source_url"):
        card["source_url"] = card.get("product_url") or card.get("url") or ""
    return card


def _coerce_az_card(raw: dict[str, Any]) -> dict[str, Any]:
    card = _coerce_competitor_card(raw)
    if not card.get("product_url"):
        card["product_url"] = card.get("url") or card.get("source_url") or ""
    if not card.get("url"):
        card["url"] = card.get("product_url") or ""
    return card


def find_az_reference(
    seed: dict[str, Any],
    az_id: str,
    pinned: dict[str, Any] | None = None,
    category: str = "AT",
) -> dict[str, Any] | None:
    pid = str(az_id or "")
    if not pid:
        return None
    if pinned and str(pinned.get("id") or "") == pid:
        return _coerce_az_card(pinned)
    for item in list_az_hot_products(seed, category=category):
        if str(item.get("id") or "") == pid:
            return _coerce_az_card(item)
    try:
        from app.services import monitor_service

        for cat in (category, "AT", "BD"):
            if not cat or cat == "全部":
                continue
            for item in monitor_service.build_monitor(cat).get("products") or []:
                if str(item.get("id") or "") != pid:
                    continue
                if item.get("pool") == "own" or item.get("site") == "Azazie":
                    return _coerce_az_card(item)
    except Exception:
        pass
    return None


def _hotspots_from_peer(peer: dict[str, Any]) -> list[dict[str, Any]]:
    return dress_attr_catalog.hotspots_from_product(peer)


def list_az_hot_products(seed: dict[str, Any], category: str = "AT") -> list[dict[str, Any]]:
    """品类热销榜：优先 AZ TTL 缓存 / Copilot；失败回退种子 / 本地 similar 索引。"""
    cat = (category or "AT").strip() or "AT"
    try:
        # fetch 内部缓存优先；首屏连打 seed+select 时不应每次都打 Copilot
        live = az_hot_service.fetch_az_hot_products(cat, limit=8)
        if live.get("products"):
            return list(live["products"])
    except Exception:  # noqa: BLE001
        pass

    by_id: dict[str, dict[str, Any]] = {}

    for item in seed.get("az_reference_candidates") or []:
        if not az_hot_service.matches_category_line({**item, "category_line": item.get("category_line") or "AT"}, cat):
            # 种子未标品类时：AT 仍要求 atelier 信号
            if cat == "AT" or item.get("category_line"):
                continue
        line = str(item.get("category_line") or cat)
        pid = str(item.get("id") or "")
        if not pid:
            continue
        card = {
            **item,
            "id": pid,
            "title": item.get("title") or item.get("name") or pid,
            "category_line": line or cat,
            "rank": item.get("rank") or 99,
            "sales_volume": item.get("sales_volume") or 0,
            "image_url": item.get("image_url") or "",
            "product_url": item.get("product_url") or item.get("url") or "",
            "source": "seed",
            "hotspot_points": item.get("hotspot_points") or item.get("anchor_points") or [],
        }
        by_id[pid] = card

    index_path = similar_index_path()
    if index_path.is_file():
        try:
            peers = json.loads(index_path.read_text(encoding="utf-8")).get("peers") or []
        except (OSError, json.JSONDecodeError):
            peers = []
        rank_base = 10
        for idx, peer in enumerate(peers):
            cats = [str(x) for x in (peer.get("category_ids") or [])]
            cname = str(peer.get("category_name") or "")
            probe = {
                "title": peer.get("name") or "",
                "product_url": peer.get("url") or "",
                "category_name": cname,
                "category_ids": cats,
                "category_line": cat if cat != "全部" else (cats[0] if cats else cname),
            }
            if cat != "全部" and not az_hot_service.matches_category_line(probe, cat):
                if cat not in cats and cname != cat and cat not in cname:
                    continue
                if cat == "AT":
                    continue
            pid = f"az-local-{peer.get('goods_id') or peer.get('product_id') or idx}"
            if pid in by_id:
                continue
            by_id[pid] = {
                "id": pid,
                "title": peer.get("name") or pid,
                "image_url": peer.get("image_url") or "",
                "product_url": peer.get("url") or "",
                "sales_volume": peer.get("sales_volume") or max(2000 - idx * 120, 100),
                "rank": rank_base + idx,
                "category_line": cat if cat != "全部" else (cats[0] if cats else cname),
                "status": "rising" if idx < 3 else "new",
                "price": peer.get("price"),
                "attrs_display": [
                    *(peer.get("silhouette") or [])[:1],
                    *(peer.get("neckline") or [])[:1],
                    *(peer.get("fabric") or [])[:1],
                    *(peer.get("dress_length") or [])[:1],
                ],
                "hotspot_points": _hotspots_from_peer(peer),
                "source": "algolia_pangu_local_index",
                "default_selected": False,
            }

    cards = list(by_id.values())
    cards = az_hot_service.filter_products_by_category(cards, cat)
    cards.sort(key=lambda x: (int(x.get("rank") or 999), -int(x.get("sales_volume") or 0)))
    for i, card in enumerate(cards, start=1):
        card["rank"] = i
    return cards


def _select_pair(
    seed: dict[str, Any],
    *,
    competitor: dict[str, Any] | None,
    az: dict[str, Any] | None,
    az_list: list[dict[str, Any]],
    trend_values: list[str] | None,
    az_trend_values: list[str] | None,
    mutex_prefer: Literal["az", "competitor", "last"] = "az",
    last_side: Literal["competitor", "az"] | None = None,
) -> dict[str, Any]:
    trends = trend_items(seed)
    az_trends = build_az_trend_hotspots(az_list)
    if trend_values is None:
        trend_values = _default_trend_values(trends)
    if az_trend_values is None:
        az_trend_values = _default_trend_values(az_trends)

    comp_points: list[dict[str, Any]] = []
    if competitor:
        comp_points = auto_check_points(
            list(competitor.get("hotspot_points") or []),
            trend_values,
            link_trends=True,
        )

    az_points: list[dict[str, Any]] = []
    if az:
        # 板 B 有数据则联动；否则降级单款 default_checked
        link_az = bool(az_trends and az_trend_values)
        az_points = auto_check_points(
            list(az.get("hotspot_points") or az.get("anchor_points") or []),
            az_trend_values if link_az else [],
            link_trends=link_az,
        )

    prefer: Literal["az", "competitor", "last"] = mutex_prefer
    if last_side:
        prefer = "last"
    comp_points, az_points, mutex_notices = hotspot_mutex.apply_dim_mutex(
        comp_points,
        az_points,
        prefer=prefer,
        last_side=last_side,
    )

    checked_comp = [point_display(p) for p in comp_points if p.get("checked")]
    checked_az = [point_display(p) for p in az_points if p.get("checked")]
    trend_labels = _labels_for_values(trends, trend_values)
    az_trend_labels = _labels_for_values(az_trends, az_trend_values)

    week = (
        (competitor or {}).get("week")
        or seed.get("default_week")
        or "2026-W30"
    )
    prompt = build_gap_fusion_prompt(
        gap_tags=trend_labels,
        az_gap_tags=az_trend_labels,
        competitor_points=checked_comp,
        az_points=checked_az,
        week_label=str(week),
        competitor_title=str((competitor or {}).get("title") or ""),
        az_title=str((az or {}).get("title") or ""),
    )
    return {
        "competitor": competitor,
        "az_reference": az,
        "az_hot_products": az_list,
        "trend_hotspots": trends,
        "az_trend_hotspots": az_trends,
        "gap_tags": trend_labels,
        "gap_tag_keys": trend_values,
        "az_gap_tags": az_trend_labels,
        "az_gap_tag_keys": az_trend_values,
        "competitor_points": checked_comp,
        "hotspot_points": comp_points,
        "az_points": checked_az,
        "anchor_points": az_points,
        "mutex_notices": mutex_notices,
        "prompt": prompt,
        "week_label": week,
        "dimensions": dress_attr_catalog.ANALYSIS_DIMENSIONS,
    }


def auto_select_for_competitor(
    seed: dict[str, Any],
    *,
    competitor_id: str,
    az_id: str | None = None,
    trend_values: list[str] | None = None,
    az_trend_values: list[str] | None = None,
    category: str = "AT",
    pinned_product: dict[str, Any] | None = None,
    skip_az_default: bool = False,
) -> dict[str, Any]:
    competitor = find_competitor(seed, competitor_id, pinned=pinned_product, category=category)
    if not competitor:
        raise KeyError(f"competitor not found: {competitor_id}")

    az_list = list_az_hot_products(seed, category=category or competitor.get("category_line") or "AT")
    az = find_az_reference(seed, az_id, category=category) if az_id else None
    if not az and not skip_az_default:
        az = next((x for x in az_list if x.get("default_selected")), None) or (
            az_list[0] if az_list else {}
        )
    if skip_az_default and not az_id:
        az = None

    # 用户点选竞品卡 = 后勾竞品侧；板趋势批量联动仍由前端 mutex(last_side=az) 走 AZ 优先
    return _select_pair(
        seed,
        competitor=competitor,
        az=az or None,
        az_list=az_list,
        trend_values=trend_values,
        az_trend_values=az_trend_values,
        mutex_prefer="last",
        last_side="competitor",
    )


def auto_select_for_az(
    seed: dict[str, Any],
    *,
    az_id: str,
    competitor_id: str | None = None,
    trend_values: list[str] | None = None,
    az_trend_values: list[str] | None = None,
    category: str = "AT",
    pinned_product: dict[str, Any] | None = None,
    pinned_competitor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    az = find_az_reference(seed, az_id, pinned=pinned_product, category=category)
    if not az:
        raise KeyError(f"az product not found: {az_id}")
    competitor = (
        find_competitor(seed, competitor_id, pinned=pinned_competitor, category=category)
        if competitor_id
        else None
    )
    az_list = list_az_hot_products(seed, category=category)
    # 用户点选 AZ 卡 = 后勾 AZ 侧
    return _select_pair(
        seed,
        competitor=competitor,
        az=az,
        az_list=az_list,
        trend_values=trend_values,
        az_trend_values=az_trend_values,
        mutex_prefer="last",
        last_side="az",
    )


def apply_manual_mutex(
    competitor_points: list[dict[str, Any]],
    az_points: list[dict[str, Any]],
    *,
    last_side: Literal["competitor", "az"],
) -> dict[str, Any]:
    """前端手勾后：后勾优先。"""
    comp, az, notices = hotspot_mutex.apply_dim_mutex(
        competitor_points,
        az_points,
        prefer="last",
        last_side=last_side,
    )
    return {
        "hotspot_points": comp,
        "anchor_points": az,
        "competitor_points": [point_display(p) for p in comp if p.get("checked")],
        "az_points": [point_display(p) for p in az if p.get("checked")],
        "mutex_notices": notices,
    }


def build_gap_fusion_prompt(
    *,
    gap_tags: list[str],
    competitor_points: list[str],
    az_points: list[str],
    week_label: str = "2026-W27/W30",
    extra_note: str = "",
    competitor_title: str = "",
    az_title: str = "",
    selected_design_points: list[dict] | None = None,
    skip_design_selection: bool = False,
    az_gap_tags: list[str] | None = None,
) -> str:
    from app.services.v13_design_points import format_selected_for_prompt

    external = ", ".join(x for x in gap_tags if x) or "n/a"
    internal = ", ".join(x for x in (az_gap_tags or []) if x) or "n/a"
    selected = list(selected_design_points or [])
    add_from_v13 = [
        str(p.get("keyword") or "")
        for p in selected
        if p.get("source") == "competitor" and p.get("keyword")
    ]
    keep_from_v13 = [
        str(p.get("keyword") or "")
        for p in selected
        if p.get("source") == "product" and p.get("keyword")
    ]
    add_pts = ", ".join(add_from_v13 or [x for x in competitor_points if x]) or "n/a"
    keep_pts = ", ".join(keep_from_v13 or [x for x in az_points if x]) or "n/a"
    v13_detail = (
        "skipped"
        if skip_design_selection
        else format_selected_for_prompt(selected)
    )
    comp_line = (competitor_title or "").strip() or "selected competitor"
    az_line = (az_title or "").strip() or "AZ hot seller"
    return f"""【工作流设计 Prompt · 自动写入 · 不可手改】
stage: product_design_v13_selected_point_design
fusion_mode: hotspot_plus_hotspot
weekly_signal: {week_label} external new+popular / rising (NOT claim sales_proxy for recency sites)
v13_input_1_competitor_images: {comp_line}
v13_input_2_product_images: {az_line}

external_hotspots_board_A_checked: {external}
internal_hotspots_board_B_checked: {internal}

design_direction:
爆点+爆点：外部市场爆点与站内周热销爆点同维互斥后局部融合；本品为可量产骨架，竞品仅注入未冲突维，禁止整款复刻。

selected_design_points:
{v13_detail}

External hotspots from competitor (must be visibly present; dims must not overlap Internal):
{add_pts}

Internal hotspots from AZ hot pool/SKU (manufacturable backbone; dims must not overlap External):
{keep_pts}

Fusion quality contract:
1) Treat AZ hot seller as the wearable backbone; inject External hotspots as localized edits only.
2) Same attribute dim must appear on at most one side (mutex already applied).
3) Every External hotspot must remain clearly readable; do not dilute with extra novelty.
4) Preserve Internal hotspots for e-commerce fit language and factory repeatability.
5) Do NOT copy the full competitor combo of silhouette + neckline + waistline + hem + surface.
6) Prefer one clear silhouette decision and one clear dressLength; avoid hybrid frankenstein seams.
7) Anatomy & drape integrity: no warped limbs, melted fabric, broken straps, floating hems, or body clipping.
8) Premium white-studio commercial finish; clean edges; high-fashion but sellable.
9) control_mode=llm_soft
10) write_mode=workflow_auto_inject
""".strip()

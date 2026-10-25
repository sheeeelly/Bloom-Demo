"""
从「爬虫」周报 + baseline 抽取：
  - 竞品网站爆点趋势（面料/领型/设计元素 gap 表）
  - 外部竞品爆款卡片（上新∩涨榜优先；主图来自 baseline.main_image_url）

能力边界（已实证）：
  - 可用：周报 gap 元素、商品名/价/排名/站点/详情 URL、主图 1 张、部分属性文本
  - 不可用：详情页 3–8 张图自动库（baseline 仅 main_image_url）
    → 回退：商品 URL + product_image_store 本地多图库（人工/后续补爬）
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import config
from app.services import dress_attr_catalog, product_image_store

_CATEGORY_DIR = {
    "AT": "atelier",
    "atelier": "atelier",
    "BD": "bd",
    "bd": "bd",
}

# 品类监控站点（与爬虫 --category 合同一致；站点筛选 UI 始终展示全量）
_SITES_AT = [
    {"key": "bb", "label": "Babyboo Fashion", "aliases": ("babyboo", "babyboo fashion")},
    {"key": "op", "label": "Oh Polly", "aliases": ("oh polly",)},
    {"key": "hocb", "label": "House of CB", "aliases": ("house of cb",)},
    {"key": "cl", "label": "Club L London", "aliases": ("club l london", "club l", "clublondon")},
]

_SITES_BD = [
    {"key": "bg", "label": "Birdy Grey", "aliases": ("birdy grey", "bird grey", "birdygrey")},
    {"key": "ss", "label": "Six Stories", "aliases": ("six stories", "sixstories")},
    {"key": "cl", "label": "Club L London", "aliases": ("club l london", "club l", "clublondon")},
    {"key": "bb", "label": "Babyboo Fashion", "aliases": ("babyboo", "babyboo fashion")},
    {"key": "hm", "label": "Hello Molly", "aliases": ("hello molly", "hellomolly")},
]

_SITE_FILES_AT = [
    ("Babyboo Fashion", "babyboo_baseline.json"),
    ("Club L London", "clublondon_baseline.json"),
    ("Club L London", "clubllondon_baseline.json"),
    ("House of CB", "houseofcb_baseline.json"),
    ("Oh Polly", "ohpolly_baseline.json"),
]

_SITE_FILES_BD = [
    ("Birdy Grey", "birdygrey_baseline.json"),
    ("Six Stories", "sixstories_baseline.json"),
    ("Club L London", "clubllondon_baseline.json"),
    ("Babyboo Fashion", "babyboo_baseline.json"),
    ("Hello Molly", "hellomolly_baseline.json"),
]

_SITE_FILES_OWN = [
    ("Azazie", "azazie_baseline.json"),
]


def category_sites(category: str = "AT") -> list[str]:
    cat = _CATEGORY_DIR.get((category or "AT").strip(), "atelier")
    catalog = _SITES_AT if cat == "atelier" else _SITES_BD
    return [s["label"] for s in catalog]


def monitor_sites(category: str = "AT") -> list[str]:
    """货盘监控站点：竞品合同站 + Azazie（自有与竞品同一筛选项，不再左右分栏）。"""
    sites = category_sites(category)
    if "Azazie" not in sites:
        sites = [*sites, "Azazie"]
    return sites


def canonicalize_site(raw: str, category: str = "AT") -> str:
    text = (raw or "").strip()
    low = text.lower()
    if low in {"azazie", "az", "azazie.com"}:
        return "Azazie"
    cat = _CATEGORY_DIR.get((category or "AT").strip(), "atelier")
    catalog = _SITES_AT if cat == "atelier" else _SITES_BD
    for site in catalog:
        if low == site["label"].lower() or any(a in low for a in site["aliases"]):
            return site["label"]
    return text or "Unknown"

_DIM_HINTS = [
    ("fabric", ("面料", "fabric", "jersey", "crepe", "satin", "velvet", "lace", "chiffon", "mesh")),
    ("neckline", ("领型", "neck", "plunge", "halter", "v-neck", "high-neck", "square", "cowl", "strapless")),
    ("dressLength", ("裙型", "length", "mini", "midi", "maxi", "tea")),
    ("sleeve", ("sleeve", "长袖", "short sleeve", "cape")),
    ("features", ("工艺", "细节", "draped", "ruched", "wrap", "split", "bodycon", "bow", "beaded", "ruffle")),
    ("silhouette", ("silhouette", "a-line", "column", "mermaid", "sheath", "bodycon")),
    ("waistline", ("waist", "empire", "corset")),
    ("colorFamily", ("颜色", "color")),
]


def crawler_root() -> Path:
    return Path(config.CRAWLER_ROOT)


def available() -> bool:
    root = crawler_root()
    return root.is_dir() and (root / "baselines").is_dir()


def list_weeks(category: str = "AT") -> list[str]:
    folder = _reports_dir(category)
    if not folder.is_dir():
        return []
    weeks: set[str] = set()
    for path in folder.glob("weekly_summary_*.md"):
        m = re.search(r"(20\d{2}-W\d{2})", path.name)
        if m:
            weeks.add(m.group(1))
    for path in folder.glob("*_Competitor_Report_*.md"):
        m = re.search(r"(20\d{2}-W\d{2})", path.name)
        if m:
            weeks.add(m.group(1))
    return sorted(weeks, reverse=True)


def _reports_dir(category: str) -> Path:
    cat = _CATEGORY_DIR.get((category or "AT").strip(), "atelier")
    return crawler_root() / "data" / "weekly_reports" / cat


def _baselines_dir(category: str) -> Path:
    cat = _CATEGORY_DIR.get((category or "AT").strip(), "atelier")
    return crawler_root() / "baselines" / cat


def _latest_report_path(category: str, week: str | None = None) -> Path | None:
    folder = _reports_dir(category)
    if not folder.is_dir():
        return None
    cat_code = "AT" if _CATEGORY_DIR.get((category or "AT").strip(), "atelier") == "atelier" else "BD"
    if week:
        for name in (
            f"{cat_code}_Competitor_Report_{week}.md",
            f"weekly_report_{week}.md",
            f"weekly_summary_{week}.md",
        ):
            path = folder / name
            if path.is_file():
                return path
    reports = sorted(folder.glob(f"{cat_code}_Competitor_Report_*.md"), reverse=True)
    if reports:
        return reports[0]
    summaries = sorted(folder.glob("weekly_summary_*.md"), reverse=True)
    return summaries[0] if summaries else None


def _guess_dim(category_cell: str, element: str) -> str:
    blob = f"{category_cell} {element}".lower()
    for dim, hints in _DIM_HINTS:
        if any(h in blob for h in hints):
            return dim
    return "features"


def parse_trend_hotspots(report_text: str) -> list[dict[str, Any]]:
    """解析「面料 / 领型 / 设计元素差异」表。"""
    rows: list[dict[str, Any]] = []
    in_table = False
    for line in report_text.splitlines():
        if "面料 / 领型 / 设计元素差异" in line or "面料 / 领型" in line:
            in_table = True
            continue
        if in_table and line.startswith("####"):
            break
        if in_table and line.startswith("|") and "---" not in line and "类别" not in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 3:
                continue
            cat_cell, element, count_s = cells[0], cells[1], cells[2]
            try:
                count = int(float(str(count_s).replace(",", "")))
            except ValueError:
                count = 0
            dim = _guess_dim(cat_cell, element)
            matched = dress_attr_catalog.match_option(dim, element)
            value = str((matched or {}).get("value") or element)
            label = str((matched or {}).get("label") or element)
            rows.append(
                {
                    "dim": dim,
                    "value": value,
                    "label": label,
                    "count": count,
                    "default_checked": count >= 50 or len(rows) < 4,
                    "key": value,
                    "source": "crawler_weekly_gap_table",
                }
            )
    # 去重保序
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda x: -int(x.get("count") or 0)):
        k = f"{row['dim']}:{row['value']}".lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(row)
    return out[:24]


def _parse_price(raw: Any) -> float | None:
    if raw is None:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", str(raw).replace(",", ""))
    return float(m.group(1)) if m else None


def _hotspots_from_metadata(md: dict[str, Any], detail: str = "") -> list[dict[str, Any]]:
    card = {
        **(md or {}),
        "metadata": md or {},
        "detail_text": detail or (md or {}).get("detail_text") or "",
        "color": (md or {}).get("color_name") or (md or {}).get("color") or "",
        "fabric": (md or {}).get("fabric_name") or (md or {}).get("fabric") or "",
        "length": (md or {}).get("length") or (md or {}).get("dressLength") or "",
        "features": (md or {}).get("aesthetic_tag") or (md or {}).get("features") or "",
    }
    return dress_attr_catalog.hotspots_from_product(card)


def parse_weekly_summary_kpis(category: str, week: str | None = None) -> dict[str, Any]:
    """解析 weekly_summary 各站指标表 + 前 3 条执行摘要。"""
    cat = _CATEGORY_DIR.get((category or "AT").strip(), "atelier")
    folder = _reports_dir(category)
    use_week = week or (list_weeks(category)[0] if list_weeks(category) else "")
    path = folder / f"weekly_summary_{use_week}.md" if use_week else None
    if path is None or not path.is_file():
        summaries = sorted(folder.glob("weekly_summary_*.md"), reverse=True)
        path = summaries[0] if summaries else None
    if path is None or not path.is_file():
        return {"week": use_week, "sites": [], "bullets": [], "path": ""}
    text = path.read_text(encoding="utf-8")
    bullets: list[str] = []
    for line in text.splitlines():
        if line.startswith("- "):
            bullets.append(line[2:].strip())
        if line.startswith("##"):
            break
        if len(bullets) >= 3:
            break
    sites: list[dict[str, Any]] = []
    in_table = False
    for line in text.splitlines():
        if "各站指标" in line:
            in_table = True
            continue
        if in_table and line.startswith("|") and "---" not in line and "网站" not in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 6:
                continue
            def _n(raw: str) -> int:
                try:
                    return int(float(str(raw).replace(",", "")))
                except ValueError:
                    return 0
            sites.append(
                {
                    "site": canonicalize_site(cells[0], category),
                    "active": _n(cells[1]),
                    "new": _n(cells[2]),
                    "delist": _n(cells[3]),
                    "rank_up": _n(cells[4]),
                    "rank_down": _n(cells[5]),
                }
            )
        if in_table and line.startswith(">") :
            break
    uncovered = 0
    if "尚未覆盖" in text or "Plum Brown" in text:
        m = re.search(r"如 \*\*(.+?)\*\*", text)
        if m:
            uncovered = len([x.strip() for x in m.group(1).split("、") if x.strip()])
    week_m = re.search(r"(20\d{2}-W\d{2})", path.name)
    resolved_week = use_week or (week_m.group(1) if week_m else "")
    return {
        "week": resolved_week,
        "sites": sites,
        "bullets": bullets[:3],
        "uncovered_colors": uncovered,
        "path": str(path),
        "source_line": cat,
    }


def _iter_baseline_products(category: str, *, include_azazie: bool = False) -> list[dict[str, Any]]:
    base_dir = _baselines_dir(category)
    site_files = list(
        _SITE_FILES_AT if _CATEGORY_DIR.get((category or "AT").strip(), "atelier") == "atelier" else _SITE_FILES_BD
    )
    if include_azazie:
        site_files.extend(_SITE_FILES_OWN)
    # 同站点多文件（Club L 双 baseline）只认 mtime 最新
    picked: dict[str, tuple[float, str, Path]] = {}
    for site_label, filename in site_files:
        path = base_dir / filename
        if not path.is_file():
            continue
        mtime = path.stat().st_mtime
        prev = picked.get(site_label)
        if prev is None or mtime >= prev[0]:
            picked[site_label] = (mtime, filename, path)
    out: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for site_label, (_mtime, filename, path) in picked.items():
        path = base_dir / filename
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        for key, item in data.items():
            if not isinstance(item, dict):
                continue
            md = item.get("metadata") or {}
            url = str(md.get("product_url") or "").strip()
            if not url.startswith("http"):
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            try:
                rank_change = float(str(md.get("rank_change") or "0").replace("+", ""))
            except ValueError:
                rank_change = 0.0
            if rank_change > 0:
                status = "rising"
            elif rank_change < 0:
                status = "falling"
            elif str(md.get("new_type") or "") in {"是", "下架后又上新", "new", "1"}:
                status = "new"
            else:
                status = "active"
            if item.get("status") == "Delisted":
                continue
            raw_site = md.get("site_name") or site_label
            site = canonicalize_site(str(raw_site), category)
            out.append(
                {
                    "id": re.sub(r"[^a-zA-Z0-9_-]+", "-", f"{site_label}-{md.get('style_spu_key') or key}")[:80],
                    "site": site,
                    "pool": "own" if site == "Azazie" or site_label == "Azazie" else "competitor",
                    "title": md.get("product_name") or md.get("style_label") or key,
                    "product_url": url,
                    "source_url": url,
                    "main_image_url": str(md.get("main_image_url") or "").strip(),
                    "color": md.get("color_name") or "",
                    "price": _parse_price(md.get("sale_price") or md.get("original_price")),
                    "compare_at": _parse_price(md.get("original_price")),
                    "rank": md.get("current_rank"),
                    "rank_delta": int(rank_change) if rank_change > 0 else None,
                    "rank_change": rank_change,
                    "week": md.get("data_week") or "",
                    "ships_now": "现货" in str(md.get("stock_type") or ""),
                    "status": status,
                    "category_line": "AT" if "atelier" in str(md.get("category") or "").lower() or category.upper() == "AT" else "BD",
                    "fabric_name": md.get("fabric_name"),
                    "neckline": md.get("neckline"),
                    "length": md.get("length"),
                    "silhouette": md.get("silhouette"),
                    "sleeve": md.get("sleeve"),
                    "waistline": md.get("waistline") or md.get("waist"),
                    "aesthetic_tag": md.get("aesthetic_tag"),
                    "color_name": md.get("color_name") or "",
                    "detail_text": md.get("detail_text") or "",
                    "discount_type": md.get("discount_type") or "",
                    "first_seen": item.get("first_seen") or "",
                    "metadata": md,
                }
            )
    return out


def _new_arrivals_feed_path(category: str) -> Path | None:
    cat = _CATEGORY_DIR.get((category or "AT").strip(), "atelier")
    candidates = [
        crawler_root() / "data" / "bloom_feeds" / cat / "latest.json",
        Path(config.BASE_DIR) / "data" / "crawler_feeds" / f"{cat}_new_arrivals.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def load_new_arrivals_feed(category: str = "AT") -> dict[str, Any] | None:
    path = _new_arrivals_feed_path(category)
    if not path:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    data["_feed_path"] = str(path)
    return data


def build_competitor_cards(
    *,
    category: str = "AT",
    week: str | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    products = _iter_baseline_products(category)
    if week:
        week_hits = [p for p in products if p.get("week") == week]
        if week_hits:
            products = week_hits
    # 优先涨榜，其次按排名靠前
    products.sort(
        key=lambda p: (
            -(float(p.get("rank_change") or 0)),
            float(p.get("rank") or 9999),
        )
    )
    # 各监控站尽量均衡抽样，避免涨榜大站占满列表导致站点筛选只剩 1 个
    per_site: dict[str, list[dict[str, Any]]] = {}
    for p in products:
        per_site.setdefault(str(p.get("site") or "Unknown"), []).append(p)
    site_order = category_sites(category)
    for label in per_site:
        if label not in site_order:
            site_order.append(label)
    picked: list[dict[str, Any]] = []
    quota = max(1, (limit + max(len(site_order), 1) - 1) // max(len(site_order), 1))
    for label in site_order:
        bucket = per_site.get(label) or []
        picked.extend(bucket[:quota])
    if len(picked) < limit:
        seen = {p["id"] for p in picked}
        for p in products:
            if p["id"] in seen:
                continue
            picked.append(p)
            if len(picked) >= limit:
                break
    picked.sort(
        key=lambda p: (
            -(float(p.get("rank_change") or 0)),
            float(p.get("rank") or 9999),
        )
    )
    cards: list[dict[str, Any]] = []
    for p in picked[: max(limit, 1)]:
        main = p.get("main_image_url") or ""
        images = product_image_store.ensure_main_image(
            product_url=p["product_url"],
            product_id=p["id"],
            main_image_url=main,
            title=p["title"],
        )
        if not images and main:
            images = [main]
        hotspots = _hotspots_from_metadata(p.get("metadata") or {}, p.get("detail_text") or "")
        attrs = [
            x
            for x in [
                p.get("color"),
                p.get("length") or (p.get("metadata") or {}).get("length"),
                p.get("neckline") or (p.get("metadata") or {}).get("neckline"),
                p.get("fabric_name") or (p.get("metadata") or {}).get("fabric_name"),
            ]
            if x
        ]
        discount = ""
        if p.get("compare_at") and p.get("price") and p["compare_at"] > p["price"]:
            off = int(round((1 - p["price"] / p["compare_at"]) * 100))
            if off > 0:
                discount = f"{off}% OFF"
        cards.append(
            {
                "id": p["id"],
                "week": p.get("week") or week or "",
                "site": p["site"],
                "category_line": p.get("category_line") or category,
                "title": p["title"],
                "image_url": (images[0] if images else main) or "",
                "detail_images": images,
                "image_count": len(images),
                "image_policy": (
                    "gallery_3_to_8"
                    if len(images) >= 3
                    else "main_image_only_need_manual_or_detail_crawl"
                ),
                "product_url": p["product_url"],
                "source_url": p["product_url"],
                "status": p.get("status") or "rising",
                "discount_label": discount,
                "price": p.get("price"),
                "compare_at": p.get("compare_at"),
                "rank": int(p["rank"]) if p.get("rank") not in (None, "") else None,
                "rank_delta": p.get("rank_delta"),
                "reviews": None,
                "ships_now": bool(p.get("ships_now")),
                "attrs_display": attrs[:4],
                "hotspot_points": hotspots,
                "gap_tag_keys": [h.get("value") for h in hotspots if h.get("value")],
                "source": "crawler_baseline",
            }
        )
    return cards


def build_seed_from_crawler(
    *,
    category: str = "AT",
    week: str | None = None,
    limit: int = 12,
) -> dict[str, Any] | None:
    if not available():
        return None
    weeks = list_weeks(category)
    use_week = week or (weeks[0] if weeks else None)
    report_path = _latest_report_path(category, use_week)
    report_text = report_path.read_text(encoding="utf-8") if report_path and report_path.is_file() else ""
    trends = parse_trend_hotspots(report_text) if report_text else []
    arrivals = load_new_arrivals_feed(category)
    arrival_cards = []
    if arrivals and isinstance(arrivals.get("products"), list):
        arrival_cards = [
            p
            for p in arrivals["products"]
            if isinstance(p, dict) and str(p.get("pool") or "competitor") != "own"
        ]
        if use_week:
            week_hits = [p for p in arrival_cards if p.get("week") == use_week]
            if week_hits:
                arrival_cards = week_hits
    cards = arrival_cards[:limit] if arrival_cards else build_competitor_cards(
        category=category, week=use_week, limit=limit
    )
    if arrival_cards and len(cards) < limit:
        extra = build_competitor_cards(category=category, week=use_week, limit=limit)
        seen = {str(c.get("id") or c.get("product_url")) for c in cards}
        for item in extra:
            key = str(item.get("id") or item.get("product_url"))
            if key in seen:
                continue
            cards.append(item)
            seen.add(key)
            if len(cards) >= limit:
                break
    # 站点筛选始终展示该品类爬虫合同全量站点（不随当前卡片抽样收缩）
    sites = category_sites(category)
    return {
        "weeks": weeks or ([use_week] if use_week else []),
        "default_week": use_week or "",
        "sites": sites,
        "trend_hotspots": trends,
        "common_gap_attributes": trends,
        "competitor_products": cards,
        "new_arrivals": arrival_cards,
        "source": {
            "crawler_root": str(crawler_root()),
            "report_path": str(report_path) if report_path else "",
            "new_arrivals_path": (arrivals or {}).get("_feed_path") or "",
            "category": category,
            "image_note": (
                "baseline 仅稳定提供 main_image_url（1 张）；"
                "3–8 张详图写入 data/product_image_store.json，或保留 product_url 人工补图。"
            ),
            "capabilities": {
                "trend_from_weekly_report": bool(trends),
                "product_cards_from_baseline": bool(cards),
                "new_arrivals_feed": bool(arrival_cards),
                "multi_image_auto_crawl": False,
                "multi_image_local_store": True,
            },
        },
    }

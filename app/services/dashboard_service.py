"""总览看板：爬虫外部机会 + 本机生成漏斗。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services import az_hot_service, crawler_weekly_adapter, result_store, sales_week_store
from app.services.crawler_weekly_adapter import parse_trend_hotspots


def _iso_week(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def funnel() -> dict[str, int]:
    generating = succeeded = failed = week_done = 0
    this_week = sales_week_store.current_week()
    by_kind = {"hot_synthesis": 0, "design": 0}
    for item in result_store.list_all():
        status = item.status.value if hasattr(item.status, "value") else str(item.status)
        kind = item.kind.value if hasattr(item.kind, "value") else str(item.kind)
        if status in {"pending", "running"}:
            generating += 1
        elif status == "succeeded":
            succeeded += 1
            by_kind[kind] = by_kind.get(kind, 0) + 1
            if _iso_week(item.created_at or "") == this_week:
                week_done += 1
        elif status == "failed":
            failed += 1
    return {
        "generating": generating,
        "succeeded": succeeded,
        "failed": failed,
        "week_done": week_done,
        "hot_succeeded": by_kind.get("hot_synthesis", 0),
        "design_succeeded": by_kind.get("design", 0),
    }


def build_dashboard(category: str = "AT") -> dict[str, Any]:
    cat = az_hot_service.normalize_category(category) if category else "AT"
    if cat == "全部":
        cat = "AT"
    kpis = crawler_weekly_adapter.parse_weekly_summary_kpis(cat)
    sites = kpis.get("sites") or []
    new_total = sum(int(s.get("new") or 0) for s in sites)
    delist_total = sum(int(s.get("delist") or 0) for s in sites)
    rank_up_total = sum(int(s.get("rank_up") or 0) for s in sites)
    report_path = crawler_weekly_adapter._latest_report_path(cat, kpis.get("week"))
    report_text = report_path.read_text(encoding="utf-8") if report_path and report_path.is_file() else ""
    gaps = parse_trend_hotspots(report_text)[:5]
    hot = az_hot_service.fetch_az_hot_products(cat, limit=8)
    own = sales_week_store.annotate_growth(cat, list(hot.get("products") or []))
    accelerating = sum(1 for p in own if p.get("trend_label") == "加速")
    trend_unknown = all(p.get("trend_label") == "unknown" for p in own) if own else True
    warnings: list[str] = []
    if any("club" in str(s.get("site") or "").lower() and int(s.get("delist") or 0) > 400 for s in sites):
        warnings.append("下架被 Club L 清盘主导，不是市场崩了")
    if not sites:
        warnings.append("周报摘要不可读，外部 KPI 为 unknown")
    return {
        "category": cat,
        "week": kpis.get("week") or "",
        "source_line": kpis.get("source_line") or "",
        "external": {
            "new_skc": new_total,
            "delist_skc": delist_total,
            "rank_up": rank_up_total,
            "uncovered_colors": kpis.get("uncovered_colors") or 0,
            "sites": sites,
            "gap_top": gaps,
            "bullets": kpis.get("bullets") or [],
            "own_hot_top": [
                {
                    "title": p.get("title"),
                    "sales_volume": p.get("sales_volume"),
                    "trend_label": p.get("trend_label"),
                    "image_url": p.get("image_url"),
                }
                for p in own[:3]
            ],
            "own_accelerating": None if trend_unknown else accelerating,
            "own_trend_note": "增速 unknown：尚未攒满两周销量快照" if trend_unknown else "",
        },
        "platform": funnel(),
        "warnings": warnings,
        "sources": {
            "weekly_summary": kpis.get("path") or "",
            "az_hot": (hot.get("meta") or {}).get("source"),
            "rank_semantics_note": "竞品只称列表序/上新；自有热销来自 salesVolume",
        },
    }

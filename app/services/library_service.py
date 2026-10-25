"""成品库：本机生成任务 + 竞品周上新灵感集 + 时尚季节包。"""
from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import quote

from app.services import crawler_weekly_adapter, nybfw_prompt, result_store, synthesis_service


def _status_bucket(status: str) -> str:
    if status in {"pending", "running"}:
        return "generating"
    if status == "succeeded":
        return "succeeded"
    if status == "failed":
        return "failed"
    return status


def _task_counts() -> dict[str, int]:
    counts = Counter()
    for item in result_store.list_all():
        status = item.status.value if hasattr(item.status, "value") else str(item.status)
        kind = item.kind.value if hasattr(item.kind, "value") else str(item.kind)
        counts["all"] += 1
        counts[_status_bucket(status)] += 1
        counts[kind] += 1
    return dict(counts)


def _arrivals_children(category: str) -> list[dict[str, Any]]:
    feed = crawler_weekly_adapter.load_new_arrivals_feed(category)
    if not feed:
        return []
    week = str(feed.get("week") or "")
    by_site = feed.get("by_site") or {}
    cat_dir = "atelier" if category.upper() in {"AT", "ATELIER"} else "bd"
    children = []
    for site, count in by_site.items():
        if int(count or 0) <= 0:
            continue
        set_id = f"arrivals:{cat_dir}:{week}:{site}"
        children.append(
            {
                "id": set_id,
                "label": site,
                "kind": "set",
                "count": int(count),
                "subtitle": f"{week} 上新",
            }
        )
    return children


def build_tree() -> dict[str, Any]:
    counts = _task_counts()
    fashion_children = []
    for pack in nybfw_prompt.list_packs():
        fashion_children.append(
            {
                "id": f"fashion:{pack.get('file')}",
                "label": pack.get("season_label") or pack.get("season_id") or pack.get("file"),
                "kind": "set",
                "count": int(pack.get("cluster_count") or 0),
                "subtitle": pack.get("season_id") or "",
            }
        )
    at_children = _arrivals_children("AT")
    bd_children = _arrivals_children("BD")
    return {
        "counts": {
            "generating": counts.get("generating", 0),
            "succeeded": counts.get("succeeded", 0),
            "failed": counts.get("failed", 0),
            "all": counts.get("all", 0),
        },
        "groups": [
            {
                "id": "local",
                "label": "本机成品",
                "kind": "group",
                "children": [
                    {"id": "local:all", "label": "全部任务", "kind": "set", "count": counts.get("all", 0)},
                    {"id": "local:generating", "label": "生成中", "kind": "set", "count": counts.get("generating", 0)},
                    {"id": "local:succeeded", "label": "已完成", "kind": "set", "count": counts.get("succeeded", 0)},
                    {"id": "local:failed", "label": "失败", "kind": "set", "count": counts.get("failed", 0)},
                    {"id": "local:hot", "label": "爆款合成", "kind": "set", "count": counts.get("hot_synthesis", 0)},
                    {"id": "local:design", "label": "季节灵感", "kind": "set", "count": counts.get("design", 0)},
                ],
            },
            {
                "id": "arrivals-at",
                "label": "竞品上新 · AT",
                "kind": "group",
                "children": at_children or [
                    {"id": "arrivals:atelier", "label": "暂无 AT 上新 feed", "kind": "set", "count": 0}
                ],
            },
            {
                "id": "arrivals-bd",
                "label": "竞品上新 · BD",
                "kind": "group",
                "children": bd_children or [
                    {"id": "arrivals:bd", "label": "暂无 BD 上新 feed", "kind": "set", "count": 0}
                ],
            },
            {
                "id": "fashion",
                "label": "时尚灵感",
                "kind": "group",
                "children": fashion_children,
            },
        ],
    }


def _local_items(set_id: str) -> dict[str, Any]:
    status = kind = None
    if set_id == "local:generating":
        status = "generating"
    elif set_id == "local:succeeded":
        status = "succeeded"
    elif set_id == "local:failed":
        status = "failed"
    elif set_id == "local:hot":
        kind = "hot_synthesis"
    elif set_id == "local:design":
        kind = "design"
    items = synthesis_service.list_syntheses(limit=200, status=status, kind=kind)
    cards = []
    for item in items:
        st = item.status.value if hasattr(item.status, "value") else str(item.status)
        kd = item.kind.value if hasattr(item.kind, "value") else str(item.kind)
        cards.append(
            {
                "id": item.id,
                "card_kind": "task",
                "title": item.title,
                "image_url": item.thumbnail_url or item.source_image_url or item.competitor_product_image_url,
                "status": st,
                "kind": kd,
                "error_message": item.error_message,
                "created_at": item.created_at,
                "href": f"/result.html?id={quote(item.id)}",
            }
        )
    return {"set": set_id, "title": "本机成品", "items": cards, "card_kind": "task"}


def _arrival_items(set_id: str) -> dict[str, Any]:
    parts = set_id.split(":")
    # arrivals:atelier:2026-W33:Babyboo Fashion  or arrivals:atelier
    cat = "AT" if (len(parts) > 1 and parts[1] == "atelier") else "BD"
    feed = crawler_weekly_adapter.load_new_arrivals_feed(cat)
    products = list((feed or {}).get("products") or [])
    week = parts[2] if len(parts) > 2 else str((feed or {}).get("week") or "")
    site = parts[3] if len(parts) > 3 else ""
    filtered = []
    for p in products:
        if str(p.get("pool") or "competitor") == "own":
            continue
        if week and p.get("week") and p.get("week") != week:
            continue
        if site and str(p.get("site") or "") != site:
            continue
        filtered.append(p)
    cards = []
    for p in filtered:
        cid = str(p.get("id") or "")
        cards.append(
            {
                "id": cid,
                "card_kind": "arrival",
                "title": p.get("title"),
                "image_url": p.get("image_url") or p.get("main_image_url"),
                "site": p.get("site"),
                "week": p.get("week") or week,
                "rank": p.get("rank"),
                "price": p.get("price"),
                "color": p.get("color"),
                "status": "new",
                "new_type": p.get("new_type"),
                "href": f"/gap-fusion.html?competitor_id={quote(cid)}",
                "cta": "用作外部爆款",
            }
        )
    title = f"{site or cat} · {week} 上新" if week else "竞品上新"
    return {"set": set_id, "title": title, "items": cards, "card_kind": "arrival"}


def _fashion_items(set_id: str) -> dict[str, Any]:
    filename = set_id.split(":", 1)[-1]
    try:
        pack = nybfw_prompt.load_pack(filename)
    except FileNotFoundError:
        return {"set": set_id, "title": filename, "items": [], "card_kind": "fashion"}
    cards = []
    for cluster in pack.get("trend_clusters") or []:
        cid = str(cluster.get("cluster_id") or "")
        cards.append(
            {
                "id": cid,
                "card_kind": "fashion",
                "title": cluster.get("label_zh") or cluster.get("label") or cid,
                "subtitle": " · ".join(cluster.get("designer_examples") or [])[:80],
                "status": str((cluster.get("az_fit") or {}).get("AT") or ""),
                "href": f"/design.html?pack={quote(filename)}&cluster={quote(cid)}",
                "cta": "用此趋势开季节灵感",
            }
        )
    return {
        "set": set_id,
        "title": pack.get("season_label") or pack.get("season_id") or filename,
        "subtitle": pack.get("season_id") or "",
        "items": cards,
        "card_kind": "fashion",
    }


def list_items(set_id: str) -> dict[str, Any]:
    sid = (set_id or "local:all").strip()
    if sid.startswith("local"):
        return _local_items(sid)
    if sid.startswith("arrivals"):
        return _arrival_items(sid)
    if sid.startswith("fashion"):
        return _fashion_items(sid)
    return _local_items("local:all")

"""AZ 自有销量周快照：按 ISO 周追加，不覆盖上周。增速不足两周 = unknown。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import config


def current_week() -> str:
    y, w, _ = date.today().isocalendar()
    return f"{y}-W{w:02d}"


def weeks_dir() -> Path:
    path = Path(config.BASE_DIR) / "data" / "az_sales_weeks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def append_snapshot(category: str, products: list[dict[str, Any]], week: str | None = None) -> Path:
    cat = (category or "AT").strip() or "AT"
    use_week = week or current_week()
    path = weeks_dir() / f"{use_week}.json"
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    bucket = dict(data.get(cat) or {})
    for card in products:
        gid = str(card.get("id") or card.get("goods_id") or card.get("product_url") or "")
        if not gid:
            continue
        bucket[gid] = {
            "goods_id": gid,
            "title": card.get("title") or card.get("name") or "",
            "color": card.get("color") or "",
            "category_line": cat,
            "sales_volume_cum": int(card.get("sales_volume") or 0),
            "week": use_week,
        }
    data[cat] = bucket
    data["_week"] = use_week
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_week(week: str) -> dict[str, Any]:
    path = weeks_dir() / f"{week}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def annotate_growth(category: str, products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """给自有卡补 sales_week / growth_rate / trend_label。不足两周一律 unknown。"""
    cat = (category or "AT").strip() or "AT"
    week_files = sorted(weeks_dir().glob("20*-W*.json"), reverse=True)
    weeks = [p.stem for p in week_files][:4]
    series: list[dict[str, dict[str, Any]]] = []
    for wk in reversed(weeks):
        series.append((_load_week(wk).get(cat) or {}))
    out: list[dict[str, Any]] = []
    for card in products:
        item = dict(card)
        gid = str(item.get("id") or item.get("goods_id") or item.get("product_url") or "")
        cum = int(item.get("sales_volume") or 0)
        sales_weeks: list[int | None] = []
        prev_cum: int | None = None
        for bucket in series:
            row = bucket.get(gid) or {}
            this_cum = int(row.get("sales_volume_cum") or 0)
            if prev_cum is None:
                sales_weeks.append(None)
            else:
                sales_weeks.append(max(this_cum - prev_cum, 0))
            prev_cum = this_cum
        valid = [n for n in sales_weeks if n is not None]
        if len(valid) < 2:
            item["sales_week"] = None
            item["growth_rate"] = None
            item["trend_label"] = "unknown"
        else:
            t, prev = valid[-1], valid[-2]
            item["sales_week"] = t
            item["growth_rate"] = (t - prev) / max(prev, 1)
            last3 = valid[-3:]
            if len(last3) >= 2 and last3[-1] > last3[-2] and item["growth_rate"] > 0.15:
                item["trend_label"] = "加速"
            elif len(last3) >= 2 and last3[-1] < last3[-2] and item["growth_rate"] < -0.15:
                item["trend_label"] = "回落"
            else:
                item["trend_label"] = "走平"
        item["sales_volume_cum"] = cum
        item["hot_rank"] = item.get("rank")
        out.append(item)
    return out

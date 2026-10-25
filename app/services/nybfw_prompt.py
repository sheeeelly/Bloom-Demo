"""
方案三 · 季节灵感包 → AI开款 analysis/design Prompt 组装。

一期：人工喂报告 JSON / 勾选趋势芯片；不做当季自动爬取。
成衣（AT/BD/MOB/Prom）与婚纱（Wedding）分属不同灵感包。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import config

CATEGORIES = ("AT", "Wedding", "BD", "MOB", "Prom")

# 品类 → 默认灵感包（婚纱独立）
DEFAULT_PACK_BY_CATEGORY = {
    "AT": "spring_2026_rtw.manual.json",
    "BD": "spring_2026_rtw.manual.json",
    "MOB": "spring_2026_rtw.manual.json",
    "Prom": "spring_2026_rtw.manual.json",
    "Wedding": "wedding_spring_2026.manual.json",
}

_CATEGORY_BRIEF = {
    "AT": "Azazie Atelier / Formal：轻礼服与派对可电商量产，结构清晰、价带友好。",
    "Wedding": "Wedding dress（独立品类）：仪式感可保留，但须可降奢量产；只用婚纱报告芯片，禁止混用成衣 hobby/utility 趋势。",
    "BD": "Bridesmaid：多色可铺、穿着稳定、结构简化，避免过度装饰。",
    "MOB": "Mother of the Bride：优雅得体，避过度露肤与派对短款。",
    "Prom": "Prom：年轻化记忆点可加强，闪光/结饰可控，仍须尺码包容。",
}


def packs_dir() -> Path:
    return Path(config.BASE_DIR) / "data" / "nybfw_packs"


def default_pack_for_category(category: str) -> str:
    cat = (category or "AT").strip()
    return DEFAULT_PACK_BY_CATEGORY.get(cat, DEFAULT_PACK_BY_CATEGORY["AT"])


def list_packs() -> list[dict[str, Any]]:
    root = packs_dir()
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append(
            {
                "file": path.name,
                "season_id": data.get("season_id"),
                "season_label": data.get("season_label"),
                "pack_kind": data.get("pack_kind") or "legacy",
                "categories": data.get("categories") or [],
                "cluster_count": len(data.get("trend_clusters") or []),
            }
        )
    return out


def load_pack(filename: str | None = None, *, category: str = "AT") -> dict[str, Any]:
    name = (filename or "").strip() or default_pack_for_category(category)
    path = packs_dir() / Path(name).name
    if not path.is_file():
        raise FileNotFoundError(f"inspiration pack not found: {path.name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("invalid pack")
    return data


def build_prompts(
    *,
    pack: dict[str, Any],
    category: str,
    selected_cluster_ids: list[str],
    pantone_enabled: bool = False,
) -> dict[str, str]:
    cat = (category or "AT").strip()
    if cat not in CATEGORIES:
        cat = "AT"

    pack_cats = pack.get("categories") or []
    if pack_cats and cat not in pack_cats:
        # 品类与包不匹配时仍组装，但在 brief 中坦白
        mismatch_note = f"WARN: pack categories={pack_cats} vs selected={cat}; prefer switching pack."
    else:
        mismatch_note = ""

    clusters = pack.get("trend_clusters") or []
    selected = [c for c in clusters if c.get("cluster_id") in set(selected_cluster_ids)]
    if not selected and clusters:
        # 默认取对当前品类 az_fit 非 no 的前几个
        selected = [
            c
            for c in clusters
            if (c.get("az_fit") or {}).get(cat, "go") not in {"no"}
        ][:3] or clusters[:1]

    season = pack.get("season_label") or pack.get("season_id") or "current season"
    source_names = ", ".join(
        str(s.get("name") or s.get("url") or "")
        for s in (pack.get("sources") or [])
        if s
    )
    structure_tags: list[str] = []
    fabric_tags: list[str] = []
    motif_tags: list[str] = []
    labels: list[str] = []
    for c in selected:
        labels.append(str(c.get("label_zh") or c.get("label") or c.get("cluster_id")))
        structure_tags.extend(c.get("structure_tags") or [])
        fabric_tags.extend(c.get("fabric_tags") or [])
        motif_tags.extend(c.get("motif_tags") or [])

    def uniq(xs: list[str]) -> list[str]:
        seen, out = set(), []
        for x in xs:
            k = str(x).strip().lower()
            if not k or k in seen:
                continue
            seen.add(k)
            out.append(str(x).strip())
        return out

    structure_tags = uniq(structure_tags)
    fabric_tags = uniq(fabric_tags)
    motif_tags = uniq(motif_tags)

    pantone_line = (
        "Color direction may reference Pantone seasonality if visible in refs."
        if pantone_enabled
        else "Phase-1: DO NOT drive design by Pantone color story; prefer structure/motif novelty first. Color may stay commercial neutrals or follow reference fabrics."
    )

    pack_kind = pack.get("pack_kind") or "legacy"
    analysis_append = f"""
【Season Inspiration Context · manual pack · {pack_kind}】
season: {season}
sources: {source_names or "n/a"}
target_category: {cat} — {_CATEGORY_BRIEF[cat]}
selected_clusters: {", ".join(labels)}
structure_tags: {", ".join(structure_tags) or "n/a"}
fabric_tags: {", ".join(fabric_tags) or "n/a"}
motif_tags: {", ".join(motif_tags) or "n/a"}
{pantone_line}
{mismatch_note}
Phase-1 note: magazine crawl is OFF; if only a technical placeholder image is present, analyze from selected_clusters, do not invent runway photo evidence.
When a real reference image exists, mark each tag above as visible / inferred / missing.
""".strip()

    design_append = f"""
【Designer Agent Brief · Season pack → Azazie {cat}】
You are designing an ORIGINAL manufacturable SKU for Azazie {cat}.
Inspiration season: {season} (pack_kind={pack_kind}).
Lead clusters: {", ".join(labels)}.
MUST translate these into wearable e-commerce construction (not couture / runway copy):
- structure: {", ".join(structure_tags) or "recompose from selected clusters"}
- motifs to consider: {", ".join(motif_tags) or "one clear memory point"}
- fabric language: {", ".join(fabric_tags) or "keep commercial drape"}

Hard rules:
1) Do NOT reproduce a recognizable designer trade dress or full combo from editorial photos.
2) Optimize for size inclusivity, factory repeatability, and clear white-studio e-commerce reads.
3) {pantone_line}
4) If category is Wedding, keep bridal ceremony readability; do not inject RTW hobby/utility tropes.
5) Output a precise identity-lock description for 8 consistent views.

【Planning · 企划摘要】
season: {season}
category: {cat}
selected_clusters: {", ".join(labels) or "n/a"}
""".strip()

    return {
        "analysis_prompt_append": analysis_append,
        "design_prompt_append": design_append,
        "season": str(season),
        "category": cat,
        "clusters": ", ".join(labels),
        "pack_kind": str(pack_kind),
        "sources": source_names,
    }

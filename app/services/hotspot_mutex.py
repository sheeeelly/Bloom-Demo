"""
爆款合成 · 同属性维互斥裁决。

规则（产品锁定）：
- 冲突键 = dim（非 label）
- 人工后勾优先（prefer_side = last_side）
- 趋势批量联动冲突 → AZ 优先
"""
from __future__ import annotations

from typing import Any, Literal

PreferSide = Literal["az", "competitor", "last"]

# V13 design-point category → 卡内 8 维 dim
V13_CATEGORY_TO_DIM = {
    "silhouette": "silhouette",
    "neckline_shoulder": "neckline",
    "fabric": "fabric",
    "color": "colorFamily",
    "surface_detail": "features",
    "waist_hip": "waistline",
    "hem": "dressLength",
    "construction": "features",
    "commercial_selling_point": "features",
}


def point_dim(point: dict[str, Any]) -> str:
    dim = str(point.get("dim") or "").strip()
    if dim:
        return dim
    cat = str(point.get("category") or "").strip()
    return V13_CATEGORY_TO_DIM.get(cat, cat or "features")


def enforce_single_checked_per_dim(
    points: list[dict[str, Any]],
    *,
    prefer_value: str | None = None,
) -> list[dict[str, Any]]:
    """同一侧同一 dim 最多保留一个 checked（板内/卡内单选）。"""
    out = [dict(p) for p in points or []]
    keep_for_dim: dict[str, int] = {}
    prefer_norm = (prefer_value or "").strip().lower()
    for idx, p in enumerate(out):
        if not p.get("checked"):
            continue
        dim = point_dim(p)
        value = str(p.get("value") or p.get("label") or "").strip().lower()
        if dim not in keep_for_dim:
            keep_for_dim[dim] = idx
            continue
        prev = keep_for_dim[dim]
        prev_val = str(out[prev].get("value") or out[prev].get("label") or "").strip().lower()
        if prefer_norm and value == prefer_norm and prev_val != prefer_norm:
            out[prev]["checked"] = False
            out[prev]["mutex_cleared"] = True
            keep_for_dim[dim] = idx
        else:
            p["checked"] = False
            p["mutex_cleared"] = True
    return out


def apply_dim_mutex(
    competitor_points: list[dict[str, Any]],
    az_points: list[dict[str, Any]],
    *,
    prefer: PreferSide = "az",
    last_side: Literal["competitor", "az"] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """对两边已勾属性做同维互斥，返回 (comp, az, notices)。"""
    comp = enforce_single_checked_per_dim([dict(p) for p in competitor_points or []])
    az = enforce_single_checked_per_dim([dict(p) for p in az_points or []])

    winner: Literal["competitor", "az"]
    if prefer == "last" and last_side in {"competitor", "az"}:
        winner = last_side
    elif prefer == "competitor":
        winner = "competitor"
    else:
        winner = "az"

    checked_comp_dims = {point_dim(p) for p in comp if p.get("checked")}
    checked_az_dims = {point_dim(p) for p in az if p.get("checked")}
    conflicts = sorted(checked_comp_dims & checked_az_dims)
    notices: list[str] = []

    for dim in conflicts:
        if winner == "az":
            for p in comp:
                if point_dim(p) == dim and p.get("checked"):
                    p["checked"] = False
                    p["mutex_cleared"] = True
            notices.append(f"同维互斥：{dim} 保留 AZ，已取消竞品")
        else:
            for p in az:
                if point_dim(p) == dim and p.get("checked"):
                    p["checked"] = False
                    p["mutex_cleared"] = True
            notices.append(f"同维互斥：{dim} 保留竞品，已取消 AZ")

    winner_dims = (
        {point_dim(p) for p in az if p.get("checked")}
        if winner == "az"
        else {point_dim(p) for p in comp if p.get("checked")}
    )
    loser = comp if winner == "az" else az
    for p in loser:
        lock = point_dim(p) in winner_dims
        p["disabled"] = lock
        if lock:
            p["checked"] = False
    for p in (az if winner == "az" else comp):
        p["disabled"] = False

    return comp, az, notices


def apply_design_point_mutex(
    points: list[dict[str, Any]],
    selected_ids: list[str],
    *,
    last_point_id: str | None = None,
) -> tuple[list[str], list[str]]:
    """
    设计点多选：同 mapped-dim 竞品/本品不能同时选。
    后勾优先（last_point_id）；否则本品优先。
    返回 (selected_ids, notices)。
    """
    by_id = {str(p.get("id")): p for p in points if p.get("id")}
    selected = [pid for pid in selected_ids if pid in by_id]
    if not selected:
        return [], []

    # group by dim
    dim_to_ids: dict[str, list[str]] = {}
    for pid in selected:
        dim = point_dim(by_id[pid])
        dim_to_ids.setdefault(dim, []).append(pid)

    keep: list[str] = []
    notices: list[str] = []
    for dim, ids in dim_to_ids.items():
        if len(ids) <= 1:
            keep.extend(ids)
            continue
        sources = {str(by_id[i].get("source") or "") for i in ids}
        if sources <= {"competitor"} or sources <= {"product"}:
            keep.extend(ids)
            continue
        # cross-source conflict
        if last_point_id and last_point_id in ids:
            winner_id = last_point_id
        else:
            winner_id = next(
                (i for i in ids if by_id[i].get("source") == "product"),
                ids[0],
            )
        keep.append(winner_id)
        dropped = [i for i in ids if i != winner_id]
        side = "本品" if by_id[winner_id].get("source") == "product" else "竞品"
        notices.append(f"同维互斥：{dim} 保留{side}设计点，已取消对侧")
        _ = dropped

    # preserve original order among kept
    ordered = [pid for pid in selected if pid in set(keep)]
    return ordered, notices

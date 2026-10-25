"""
V13 设计点分析 / 选择合同（对齐 cloudsway_ai ProductDesignV13*）。

- 竞品 / 本品各自产出 points（keyword 按钮文案 + description…）
- 对用户：设计点 UI 隐藏；合成前按爆点语义相似度自动勾选
- Bloom 直连 Cloudsway GPT vision，不依赖 Comfy UI 暂停节点
"""
from __future__ import annotations

import base64
import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse

import requests

import config
from app.services import hotspot_mutex

logger = logging.getLogger(__name__)

POINT_CATEGORIES = {
    "silhouette",
    "neckline_shoulder",
    "fabric",
    "color",
    "surface_detail",
    "waist_hip",
    "hem",
    "construction",
    "commercial_selling_point",
}

V13_COMPETITOR_FOCUS = (
    "提取竞品中值得借鉴但不能直接复制的服装设计语言，重点观察版型、领肩、"
    "面料、表面细节、腰臀结构、裙摆、工艺和商业卖点。"
)
V13_PRODUCT_FOCUS = (
    "提取本品必须保留的识别点、当前优势和可升级空间，重点判断哪些设计点适合"
    "延续，哪些需要重做以避免同质化。"
)

_ANALYSIS_DEVELOPER = """You are a senior fashion product analyst. Analyze only the attached {role} overview image.

Return one JSON object with exactly these top-level fields:
- summary: concise Chinese summary string;
- points: array of 4 to 8 independently selectable design points.

Each point must contain:
- category: one of silhouette, neckline_shoulder, fabric, color, surface_detail, waist_hip, hem, construction, commercial_selling_point;
- keyword: 2 to 6 Chinese characters suitable for a button, never a sentence;
- description: concrete Chinese design observation;
- evidence_image_indices: array of visible numbered-image indices;
- design_value: how this point can inform a new garment;
- risk_note: copying, production, fit or commercial risk; use an empty string when none.

Keep points atomic so a product manager can select them independently. Describe visible evidence only. Do not design the new garment in this step. Do not use Markdown. Return JSON only."""


def _chat_url(base_url: str) -> str:
    url = base_url.strip().rstrip("/")
    if url.lower().endswith("/chat/completions"):
        return url
    return f"{url}/chat/completions"


def _download_image_data_url(image_url: str, *, timeout: float = 45.0) -> str:
    resp = requests.get(image_url, timeout=timeout)
    resp.raise_for_status()
    content_type = (resp.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip()
    if not content_type.startswith("image/"):
        content_type = "image/jpeg"
    encoded = base64.b64encode(resp.content).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise RuntimeError("设计点分析结果为空")
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise RuntimeError("设计点分析结果不是 JSON 对象")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise RuntimeError("设计点分析结果不是 JSON 对象")
    return parsed


def _extract_text(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("API 响应中没有 choices")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise RuntimeError("API 响应中的 choices[0] 格式无效")
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(x for x in parts if x)
    raise RuntimeError("API 响应缺少可解析文本")


def normalize_points(raw: Any, source: str, image_count: int = 1) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise RuntimeError("设计点分析结果中的 points 必须是数组")
    points: list[dict[str, Any]] = []
    prefix = "C" if source == "competitor" else "P"
    for position, item in enumerate(raw[:8], start=1):
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip()
        if category not in POINT_CATEGORIES:
            category = "construction"
        keyword = str(item.get("keyword") or item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        if not keyword or not description:
            continue
        keyword = "".join(keyword.split()).strip("，。；：、,.!！?？-—")
        keyword = keyword[:6]
        evidence: list[int] = []
        for value in item.get("evidence_image_indices") or []:
            if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= max(1, image_count):
                if value not in evidence:
                    evidence.append(value)
        points.append(
            {
                "id": str(item.get("id") or f"{prefix}{position}"),
                "source": source,
                "category": category,
                "keyword": keyword,
                "title": keyword,
                "description": description,
                "evidence_image_indices": evidence,
                "design_value": str(item.get("design_value") or "").strip(),
                "risk_note": str(item.get("risk_note") or "").strip(),
            }
        )
    if not points:
        raise RuntimeError("大模型没有返回可供选择的设计点")
    return points


def points_from_hotspots(hotspots: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    """无视觉分析时的降级：用卡内属性拼成 V13 按钮形态。"""
    raw = []
    for item in hotspots or []:
        label = str(item.get("label") or item.get("value") or "").strip()
        if not label:
            continue
        keyword = re.sub(r"[A-Za-z0-9 ·/\-_]+", "", label) or label
        keyword = "".join(keyword.split())[:6] or label[:6]
        dim = str(item.get("dim") or "features")
        category = {
            "silhouette": "silhouette",
            "neckline": "neckline_shoulder",
            "sleeve": "neckline_shoulder",
            "fabric": "fabric",
            "colorFamily": "color",
            "dressLength": "hem",
            "waistline": "waist_hip",
            "features": "surface_detail",
        }.get(dim, "commercial_selling_point")
        raw.append(
            {
                "category": category,
                "keyword": keyword,
                "description": label,
                "design_value": f"参考{label}做局部差异化",
                "risk_note": "",
                "evidence_image_indices": [1],
            }
        )
    if not raw:
        raw = [
            {
                "category": "commercial_selling_point",
                "keyword": "待补充",
                "description": "缺少可解析属性，请重新分析或手选后补充备注",
                "design_value": "",
                "risk_note": "证据不足",
                "evidence_image_indices": [],
            }
        ]
    return normalize_points(raw, source, 1)


def analyze_source(
    *,
    source: str,
    image_urls: list[str],
    title: str = "",
    focus: str | None = None,
    fallback_hotspots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """分析竞品或本品，返回 {summary, points, status, source, ...}。"""
    if source not in {"competitor", "product"}:
        raise ValueError("source 必须是 competitor 或 product")
    urls = [u.strip() for u in image_urls if str(u or "").strip()][:8]
    if source == "product" and not urls:
        return {
            "stage": "product_design_v13_product_analysis",
            "status": "skipped_no_product_images",
            "source": source,
            "summary": "未提供本品图片，本次仅使用竞品设计点。",
            "points": [],
            "image_count": 0,
        }

    api_key = str(getattr(config, "CLOUDSWAY_API_KEY", "") or "").strip()
    base_url = str(getattr(config, "CLOUDSWAY_GPT_BASE_URL", "") or "").strip()
    model = str(getattr(config, "CLOUDSWAY_GPT_MODEL_ID", "") or "").strip()
    if not api_key or not base_url or not model or not urls:
        logger.warning("V13 分析降级为 hotspot 映射 source=%s", source)
        points = points_from_hotspots(fallback_hotspots or [], source)
        return {
            "stage": f"product_design_v13_{source}_analysis",
            "status": "fallback_hotspots",
            "source": source,
            "summary": f"{'竞品' if source == 'competitor' else '本品'}（降级）：基于商品属性映射设计点。{title}".strip(),
            "points": points,
            "image_count": len(urls),
        }

    role = "竞品" if source == "competitor" else "本品"
    focus_text = (focus or (V13_COMPETITOR_FOCUS if source == "competitor" else V13_PRODUCT_FOCUS)).strip()
    try:
        data_url = _download_image_data_url(urls[0])
        user_text = (
            f"分析对象：{role}。\n"
            f"标题：{title or 'n/a'}。\n"
            f"图片数量：{len(urls)}。总览图中的编号与输入顺序一致。\n"
            f"本次分析重点：{focus_text}"
        )
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "developer",
                    "content": _ANALYSIS_DEVELOPER.format(role=role),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url, "detail": "high"},
                        },
                    ],
                },
            ],
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        # 部分网关不认 reasoning_effort；有则带上
        payload["reasoning_effort"] = "none"
        resp = requests.post(
            _chat_url(base_url),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=float(getattr(config, "AZ_COPILOT_TIMEOUT", 90) or 90),
        )
        try:
            data = resp.json()
        except ValueError as exc:
            raise RuntimeError(f"Cloudsway 返回非 JSON（HTTP {resp.status_code}）") from exc
        if not resp.ok:
            detail = json.dumps(data, ensure_ascii=False)[:800].replace(api_key, "***")
            raise RuntimeError(f"Cloudsway 分析失败 HTTP {resp.status_code}: {detail}")
        parsed = _extract_json_object(_extract_text(data))
        summary = str(parsed.get("summary") or "").strip()
        if not summary:
            raise RuntimeError("设计点分析结果缺少 summary")
        points = normalize_points(parsed.get("points"), source, len(urls))
        return {
            "stage": f"product_design_v13_{source}_analysis",
            "status": "success",
            "source": source,
            "summary": summary,
            "points": points,
            "image_count": len(urls),
            "model": model,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("V13 视觉分析失败，降级 hotspot source=%s err=%s", source, exc)
        points = points_from_hotspots(fallback_hotspots or [], source)
        return {
            "stage": f"product_design_v13_{source}_analysis",
            "status": "fallback_after_error",
            "source": source,
            "summary": f"{role}分析失败已降级：{exc}",
            "points": points,
            "image_count": len(urls),
            "error": str(exc),
        }


def build_selection_payload(
    competitor: dict[str, Any],
    product: dict[str, Any],
    *,
    selected_point_ids: list[str] | None = None,
) -> dict[str, Any]:
    points = list(competitor.get("points") or []) + list(product.get("points") or [])
    by_id = {str(p.get("id")): p for p in points if p.get("id")}
    selected_ids: list[str] = []
    for pid in selected_point_ids or []:
        pid = str(pid).strip()
        if pid in by_id and pid not in selected_ids:
            selected_ids.append(pid)
    available_sources = {str(p.get("source") or "") for p in points}
    required_sources = sorted(s for s in ("competitor", "product") if s in available_sources)
    selected = [by_id[i] for i in selected_ids]
    selected_sources = {str(p.get("source") or "") for p in selected}
    confirmed = bool(required_sources) and set(required_sources).issubset(selected_sources)
    return {
        "stage": "product_design_v13_point_selection",
        "competitor_summary": str(competitor.get("summary") or ""),
        "product_summary": str(product.get("summary") or ""),
        "points": points,
        "selected_point_ids": selected_ids,
        "selected_points": selected,
        "selection_confirmed": confirmed,
        "skip_selection": False,
        "required_sources": required_sources,
        "competitor_status": competitor.get("status"),
        "product_status": product.get("status"),
    }


def validate_selection(payload: dict[str, Any], *, skip: bool = False) -> dict[str, Any]:
    points = list(payload.get("points") or [])
    by_id = {str(p.get("id")): p for p in points}
    if skip:
        return {
            **payload,
            "selected_point_ids": [],
            "selected_points": [],
            "selection_confirmed": False,
            "skip_selection": True,
            "selection_state": "skipped",
        }
    selected_ids = [
        pid
        for pid in (payload.get("selected_point_ids") or [])
        if str(pid) in by_id
    ]
    selected = [by_id[str(pid)] for pid in selected_ids]
    available = {str(p.get("source") or "") for p in points}
    required = {s for s in ("competitor", "product") if s in available}
    selected_sources = {str(p.get("source") or "") for p in selected}
    ok = required.issubset(selected_sources)
    if not ok:
        missing = "、".join("竞品" if s == "competitor" else "本品" for s in sorted(required - selected_sources))
        raise ValueError(f"请至少各选 1 个：{missing}" if missing else "请完成设计点选择")
    return {
        **payload,
        "selected_point_ids": selected_ids,
        "selected_points": selected,
        "selection_confirmed": True,
        "skip_selection": False,
        "selection_state": "confirmed",
        "required_sources": sorted(required),
    }


def format_selected_for_prompt(selected_points: list[dict[str, Any]]) -> str:
    if not selected_points:
        return "n/a"
    lines = []
    for index, point in enumerate(selected_points, start=1):
        src = "竞品" if point.get("source") == "competitor" else "本品"
        lines.append(
            f"{index}. [{point.get('id')}] ({src}/{point.get('category')}) "
            f"{point.get('keyword')}：{point.get('description')}"
        )
    return "\n".join(lines)


def _norm_text(text: str) -> str:
    return " ".join(
        str(text or "")
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
        .replace("·", " ")
        .split()
    )


def _tokens(text: str) -> set[str]:
    t = _norm_text(text)
    words = set(re.findall(r"[a-z0-9]+", t))
    chars = set(re.findall(r"[\u4e00-\u9fff]", t))
    return words | chars


def semantic_similarity(a: str, b: str) -> float:
    """轻量语义近似：子串 / 字符词 Jaccard / SequenceMatcher，无外部 embedding。"""
    na, nb = _norm_text(a), _norm_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.88
    ta, tb = _tokens(na), _tokens(nb)
    jacc = (len(ta & tb) / len(ta | tb)) if (ta or tb) else 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    return max(jacc, seq, 0.55 * jacc + 0.45 * seq)


def _point_match_text(point: dict[str, Any]) -> str:
    return " ".join(
        str(point.get(k) or "")
        for k in ("keyword", "title", "description", "design_value", "category")
    )


def _hotspot_texts(hotspots: list[dict[str, Any]] | list[str]) -> list[tuple[str, str]]:
    """返回 (dim, text) 列表。"""
    out: list[tuple[str, str]] = []
    for item in hotspots or []:
        if isinstance(item, str):
            text = item.strip()
            if text:
                out.append(("", text))
            continue
        dim = str(item.get("dim") or "").strip()
        text = str(
            item.get("label") or item.get("value") or item.get("key") or ""
        ).strip()
        if text:
            out.append((dim, text))
    return out


def auto_select_by_hotspot_similarity(
    points: list[dict[str, Any]],
    *,
    competitor_hotspots: list[dict[str, Any]] | list[str] | None = None,
    product_hotspots: list[dict[str, Any]] | list[str] | None = None,
    min_score: float = 0.28,
) -> tuple[list[str], list[str]]:
    """
    按用户已勾爆点，为两侧设计点做语义最近邻自动勾选（后台，不展示）。
    - 每个爆点挑同侧最高分设计点（同维加权）
    - 同侧同维只留最高分一个
    - 再跑跨侧同维互斥
    """
    by_id = {str(p.get("id")): p for p in points if p.get("id")}
    if not by_id:
        return [], []

    selected: list[str] = []
    notices: list[str] = []
    side_specs = (
        ("competitor", _hotspot_texts(list(competitor_hotspots or []))),
        ("product", _hotspot_texts(list(product_hotspots or []))),
    )

    for source, hotspots in side_specs:
        candidates = [p for p in points if str(p.get("source") or "") == source]
        if not candidates:
            continue
        dim_best: dict[str, tuple[float, str]] = {}
        picked_for_hotspot: list[str] = []

        for dim, text in hotspots:
            best_id = ""
            best_score = -1.0
            for p in candidates:
                pid = str(p.get("id"))
                score = semantic_similarity(text, _point_match_text(p))
                p_dim = hotspot_mutex.point_dim(p)
                if dim and p_dim == dim:
                    score += 0.12
                if score > best_score:
                    best_score = score
                    best_id = pid
            if best_id and best_score >= min_score:
                picked_for_hotspot.append(best_id)
                p_dim = hotspot_mutex.point_dim(by_id[best_id])
                prev = dim_best.get(p_dim)
                if not prev or best_score > prev[0]:
                    dim_best[p_dim] = (best_score, best_id)

        side_ids = [pid for _, pid in dim_best.values()] or picked_for_hotspot
        if not side_ids and candidates:
            # 兜底：与全部爆点文本比总分，或取第一个
            joined = " ".join(t for _, t in hotspots)
            ranked = sorted(
                candidates,
                key=lambda p: semantic_similarity(joined, _point_match_text(p)),
                reverse=True,
            )
            side_ids = [str(ranked[0].get("id"))]
            notices.append(f"设计点自动勾选：{source} 侧无高相似命中，已兜底取最优")

        for pid in side_ids:
            if pid not in selected:
                selected.append(pid)

    selected, mutex_notices = hotspot_mutex.apply_design_point_mutex(points, selected)
    notices.extend(mutex_notices)

    # 同侧同维再收一次（只留一个）
    keep: list[str] = []
    seen_side_dim: set[tuple[str, str]] = set()
    for pid in selected:
        p = by_id.get(pid)
        if not p:
            continue
        key = (str(p.get("source") or ""), hotspot_mutex.point_dim(p))
        if key in seen_side_dim:
            continue
        seen_side_dim.add(key)
        keep.append(pid)

    # 互斥后若某侧被清空，但该侧仍有候选 → 补一个不与对侧同维冲突的点
    for source, hotspots in side_specs:
        if any(str(by_id[i].get("source") or "") == source for i in keep if i in by_id):
            continue
        candidates = [p for p in points if str(p.get("source") or "") == source]
        if not candidates:
            continue
        opposite_dims = {
            hotspot_mutex.point_dim(by_id[i])
            for i in keep
            if i in by_id and str(by_id[i].get("source") or "") != source
        }
        joined = " ".join(t for _, t in hotspots)
        ranked = sorted(
            candidates,
            key=lambda p: (
                0 if hotspot_mutex.point_dim(p) in opposite_dims else 1,
                semantic_similarity(joined, _point_match_text(p)),
            ),
            reverse=True,
        )
        pick = next(
            (p for p in ranked if hotspot_mutex.point_dim(p) not in opposite_dims),
            ranked[0],
        )
        pid = str(pick.get("id"))
        if pid and pid not in keep:
            # 若只能撞维，则让位给本品/后补侧：清掉对侧同维
            p_dim = hotspot_mutex.point_dim(pick)
            if p_dim in opposite_dims:
                keep = [
                    i
                    for i in keep
                    if not (
                        i in by_id
                        and str(by_id[i].get("source") or "") != source
                        and hotspot_mutex.point_dim(by_id[i]) == p_dim
                    )
                ]
                notices.append(f"设计点自动勾选：为保留{source}侧，已让出同维 {p_dim}")
            keep.append(pid)
            notices.append(f"设计点自动勾选：已补齐 {source} 侧")

    return keep, notices


def prepare_auto_selection(
    analyze_result: dict[str, Any],
    *,
    competitor_hotspots: list[dict[str, Any]] | list[str] | None = None,
    product_hotspots: list[dict[str, Any]] | list[str] | None = None,
) -> dict[str, Any]:
    """分析完成后：语义自动勾选 + validate。"""
    selection = dict(analyze_result.get("selection") or {})
    points = list(selection.get("points") or [])
    selected_ids, notices = auto_select_by_hotspot_similarity(
        points,
        competitor_hotspots=competitor_hotspots,
        product_hotspots=product_hotspots,
    )
    payload = {
        "points": points,
        "selected_point_ids": selected_ids,
        "competitor_summary": selection.get("competitor_summary")
        or (analyze_result.get("competitor") or {}).get("summary")
        or "",
        "product_summary": selection.get("product_summary")
        or (analyze_result.get("product") or {}).get("summary")
        or "",
    }
    validated = validate_selection(payload, skip=False)
    validated["mutex_notices"] = notices
    validated["auto_selected"] = True
    return {
        **analyze_result,
        "selection": validated,
        "auto_selected_point_ids": selected_ids,
        "auto_select_notices": notices,
    }


def analyze_pair(
    *,
    competitor_image_urls: list[str],
    product_image_urls: list[str],
    competitor_title: str = "",
    product_title: str = "",
    competitor_hotspots: list[dict[str, Any]] | None = None,
    product_hotspots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    competitor = analyze_source(
        source="competitor",
        image_urls=competitor_image_urls,
        title=competitor_title,
        fallback_hotspots=competitor_hotspots,
    )
    product = analyze_source(
        source="product",
        image_urls=product_image_urls,
        title=product_title,
        fallback_hotspots=product_hotspots,
    )
    payload = build_selection_payload(competitor, product)
    return {
        "competitor": competitor,
        "product": product,
        "selection": payload,
    }

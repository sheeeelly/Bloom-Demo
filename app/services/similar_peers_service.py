"""
相似款参考卡业务：默认半真本地裙装索引 + 属性文本匹配；可选 az-copilot。

Jobs
----
图+图生成新款后，从合成/设计报告抽取新款商品属性，在本地索引（或可选 az-copilot）
上召回相似款，标注重叠度风险并支持「标记相似款」。对照对象是 AI 生成结果，不是输入竞品。
"""
from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any

from pathlib import Path

import config
from app.schemas.similar_peers import (
    GeneratedAttributesResponse,
    QueryAttribute,
    SimilarPeerCard,
    SimilarPeersResponse,
)
from app.schemas.synthesis import SynthesisResult, SynthesisStatus
from app.services import az_copilot_client, result_store

logger = logging.getLogger(__name__)

_CACHE: dict[str, SimilarPeersResponse] = {}
_EXCLUSIONS: dict[str, set[str]] = {}
_LOCK = threading.RLock()
_LOCAL_INDEX_CACHE: list[dict[str, Any]] | None = None

# 本期 Demo 默认半真本地索引；设 SIMILAR_PEERS_USE_COPILOT=true 才尝试 az-copilot
_USE_COPILOT = bool(getattr(config, "SIMILAR_PEERS_USE_COPILOT", False))

# 查询维 ↔ 商品卡字段
_DIM_MAP: list[tuple[str, str, str]] = [
    # (query_key_or_selection_key, peer_attr_key, 中文标签)
    ("silhouette", "silhouette", "版型"),
    ("neckline_shoulder", "neckline", "领型"),
    ("neckline", "neckline", "领型"),
    ("sleeve", "features", "袖型"),
    ("fabric", "fabric", "面料"),
    ("skirt_hem", "features", "裙摆"),
    ("length", "dress_length", "裙长"),
    ("dress_length", "dress_length", "裙长"),
    ("color", "color_family", "色彩"),
    ("colour", "color_family", "色彩"),
]

_ATTR_LABELS = {
    "silhouette": "版型",
    "neckline": "领型",
    "fabric": "面料",
    "dress_length": "裙长",
    "color_family": "色彩",
    "features": "特征",
}

def _load_local_index() -> list[dict[str, Any]]:
    """半真本地裙装索引：data/similar_local_index.json。"""
    global _LOCAL_INDEX_CACHE
    if _LOCAL_INDEX_CACHE is not None:
        return _LOCAL_INDEX_CACHE
    path = Path(config.BASE_DIR) / "data" / "similar_local_index.json"
    peers: list[dict[str, Any]] = []
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            peers = list(data.get("peers") or [])
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("load local similar index failed: %s", exc)
    _LOCAL_INDEX_CACHE = peers
    return peers


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _split_values(raw: str) -> list[str]:
    parts = re.split(r"[,/|·;，、]+", raw or "")
    return [p.strip() for p in parts if p and p.strip()]


def _values_overlap(query_value: str, peer_values: list[str]) -> bool:
    """更严的匹配：整词归一化相等，或长度≥4 的子串包含（避免 a/in 误伤）。"""
    q_parts = [_norm(x) for x in _split_values(query_value)]
    q_parts = [q for q in q_parts if len(q) >= 3]
    if not q_parts:
        return False
    peer_norms = [_norm(pv) for pv in peer_values if pv]
    peer_norms = [p for p in peer_norms if p]
    if not peer_norms:
        return False
    for q in q_parts:
        for p in peer_norms:
            if q == p:
                return True
            if len(q) >= 4 and (q in p or p in q):
                return True
    return False


def _add_attr(
    attrs: list[QueryAttribute],
    seen_keys: set[str],
    *,
    peer_key: str,
    label: str,
    value: str,
    source: str,
    overwrite: bool = False,
) -> None:
    val = str(value or "").strip()
    if not val:
        return
    # 过长领型描述取首段
    if peer_key in {"neckline", "features"} and len(val) > 48:
        val = _split_values(val)[0] if _split_values(val) else val[:48]
    if peer_key in seen_keys:
        if not overwrite:
            return
        attrs[:] = [a for a in attrs if a.key != peer_key]
        seen_keys.discard(peer_key)
    seen_keys.add(peer_key)
    attrs.append(QueryAttribute(key=peer_key, label=label, value=val, source=source))


def _attrs_from_text_blob(blob: str) -> list[tuple[str, str, str]]:
    if not blob:
        return []
    rules = [
        # EN
        (r"\b(fit\s*and\s*flare|a[- ]?line|column|sheath|mermaid|ball\s*gown|empire)\b", "silhouette", "版型"),
        (r"\b(sweetheart|v[- ]?neck|one[- ]?shoulder|halter|strapless|scoop|square\s*neck|cowl|bardot)\b", "neckline", "领型"),
        (r"\b(chiffon|satin|crepe|tulle|velvet|organza|lace)\b", "fabric", "面料"),
        (r"\b(floor[- ]?length|maxi|midi|mini|tea[- ]?length|ankle[- ]?length)\b", "dress_length", "裙长"),
        (r"\b(lemon|yellow|sage|blush|champagne|ivory|black|white|floral|pink|red|blue|green|nude)\b", "color_family", "色彩"),
        # ZH（报告）
        (r"(公主线|鱼尾|直筒|修身|收腰伞摆|A字|A-?Line)", "silhouette", "版型"),
        (r"(心形领|V领|单肩|挂脖|抹胸|方领|圆领|一字肩)", "neckline", "领型"),
        (r"(雪纺|缎面|绉纱|薄纱|丝绒|欧根纱|蕾丝)", "fabric", "面料"),
        (r"(及地|拖地|长裙|中长|迷你|茶长|Maxi|Midi)", "dress_length", "裙长"),
        (r"(柠檬|黄色|雾霾蓝|香槟|象牙白|黑色|白色|碎花|粉色)", "color_family", "色彩"),
    ]
    found: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for pattern, key, label in rules:
        if key in seen:
            continue
        m = re.search(pattern, blob, flags=re.IGNORECASE)
        if m:
            seen.add(key)
            found.append((key, label, m.group(1)))
    return found


# 报告原子维 → 相似款对照维
_REPORT_ATTR_MAP: dict[str, tuple[str, str]] = {
    "silhouette": ("silhouette", "版型"),
    "neckline": ("neckline", "领型"),
    "neckline_shoulder": ("neckline", "领型"),
    "fabric": ("fabric", "面料"),
    "color": ("color_family", "色彩"),
    "color_print": ("color_family", "色彩"),
    "colour": ("color_family", "色彩"),
    "length": ("dress_length", "裙长"),
    "dress_length": ("dress_length", "裙长"),
    "skirt_hem": ("features", "裙摆"),
    "waist": ("features", "腰线"),
    "sleeve": ("features", "袖型"),
}


def _collect_report_corpus(result: SynthesisResult) -> str:
    """拼接合成/设计报告正文（新款属性的权威来源）。"""
    chunks: list[str] = []
    if result.report_markdown:
        chunks.append(result.report_markdown)
    for doc in result.report_docs or []:
        title = (doc.title or "").strip()
        content = (doc.content or "").strip()
        if title or content:
            chunks.append(f"## {title}\n{content}")
    pa = result.product_attributes or {}
    if pa:
        try:
            chunks.append(json.dumps(pa, ensure_ascii=False))
        except TypeError:
            chunks.append(str(pa))
    return "\n\n".join(chunks)


def _iter_json_objects(text: str) -> list[Any]:
    """从报告中捞出可解析的 JSON 对象/数组。"""
    found: list[Any] = []
    if not text:
        return found

    for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE):
        raw = m.group(1).strip()
        try:
            found.append(json.loads(raw))
        except json.JSONDecodeError:
            pass

    for opener, closer in (("{", "}"), ("[", "]")):
        starts = [i for i, ch in enumerate(text) if ch == opener]
        for start in starts[:40]:
            depth = 0
            for i in range(start, min(len(text), start + 12000)):
                ch = text[i]
                if ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        snippet = text[start : i + 1]
                        try:
                            found.append(json.loads(snippet))
                        except json.JSONDecodeError:
                            pass
                        break
    return found


def _value_from_fusion_item(item: dict[str, Any]) -> str:
    for key in ("value", "target", "target_value", "adopted", "final", "本款", "本款采用"):
        raw = item.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return ""


def _attrs_from_fusion_structures(data: Any) -> list[tuple[str, str, str]]:
    """解析 fusion_plan / 商品属性 JSON → (peer_key, label, value)。"""
    out: list[tuple[str, str, str]] = []

    def handle_plan_list(items: list[Any]) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            attr = str(item.get("attr") or item.get("dim") or item.get("key") or "").strip()
            if not attr:
                continue
            mapped = _REPORT_ATTR_MAP.get(attr) or _REPORT_ATTR_MAP.get(attr.lower())
            if not mapped:
                continue
            peer_key, label = mapped
            value = _value_from_fusion_item(item)
            if value:
                out.append((peer_key, label, value))

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            plan = node.get("fusion_plan")
            if isinstance(plan, list):
                handle_plan_list(plan)
            for src_key, (peer_key, label) in _REPORT_ATTR_MAP.items():
                if src_key in node and node[src_key] not in (None, "", [], {}):
                    raw = node[src_key]
                    if isinstance(raw, dict):
                        raw = raw.get("overall") or raw.get("value") or raw.get("name") or ""
                    if isinstance(raw, list):
                        val = ", ".join(str(x) for x in raw if str(x).strip())
                    else:
                        val = str(raw).strip()
                    if val and val not in {"待 GPT 面料工艺分析回填", "参考图可见面料（POC）"}:
                        out.append((peer_key, label, val))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            if node and isinstance(node[0], dict) and ("attr" in node[0] or "dim" in node[0]):
                handle_plan_list(node)
            else:
                for v in node:
                    walk(v)

    walk(data)
    return out


def _attrs_from_labeled_report_fields(text: str) -> list[tuple[str, str, str]]:
    """从中文/英文报告标签行抽取本款属性。"""
    if not text:
        return []
    patterns = [
        (r"(?:本款采用|最终采用|新款|融合结果)?\s*[:：]?\s*(?:廓形|版型|silhouette)\s*[:：]\s*([^\n|;，,]+)", "silhouette", "版型"),
        (r"(?:领型|领肩|neckline)\s*[:：]\s*([^\n|;，,]+)", "neckline", "领型"),
        (r"(?:面料|材质|fabric)\s*[:：]\s*([^\n|;，,]+)", "fabric", "面料"),
        (r"(?:裙长|衣长|length)\s*[:：]\s*([^\n|;，,]+)", "dress_length", "裙长"),
        (r"(?:颜色|色彩|印花|color)\s*[:：]\s*([^\n|;，,]+)", "color_family", "色彩"),
        (r"(?:腰线|收腰|waist)\s*[:：]\s*([^\n|;，,]+)", "features", "腰线"),
        (r"(?:裙摆|下摆|hem)\s*[:：]\s*([^\n|;，,]+)", "features", "裙摆"),
        (r"\|\s*(廓形|版型|领肩|领型|面料|颜色/?印花|裙摆|收腰|袖|衣长|裙长)\s*\|\s*[^|]+\|\s*[^|]+\|\s*\*?\*?([^*\n|]+)\*?\*?\s*\|", "table", "table"),
    ]
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    table_map = {
        "廓形": ("silhouette", "版型"),
        "版型": ("silhouette", "版型"),
        "领肩": ("neckline", "领型"),
        "领型": ("neckline", "领型"),
        "面料": ("fabric", "面料"),
        "颜色/印花": ("color_family", "色彩"),
        "颜色": ("color_family", "色彩"),
        "裙摆": ("features", "裙摆"),
        "收腰": ("features", "腰线"),
        "袖": ("features", "袖型"),
        "衣长": ("dress_length", "裙长"),
        "裙长": ("dress_length", "裙长"),
    }
    for pattern, key, label in patterns:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            if key == "table":
                dim = m.group(1).strip()
                val = m.group(2).strip()
                mapped = table_map.get(dim)
                if not mapped or not val:
                    continue
                peer_key, lab = mapped
                if re.fullmatch(r"(竞品|AZ|新作|保留|参考).*", val, flags=re.IGNORECASE):
                    continue
                if peer_key in seen:
                    continue
                seen.add(peer_key)
                out.append((peer_key, lab, val))
            else:
                val = m.group(1).strip()
                if key in seen or not val:
                    continue
                seen.add(key)
                out.append((key, label, val))
    return out


def extract_query_attributes(result: SynthesisResult) -> list[QueryAttribute]:
    """
    相似款查询属性 = AI 生成新款的属性，权威来源是合成/设计报告。

    1. 报告内 fusion_plan / 商品属性 JSON（本款采用值）
    2. 报告正文标签行 / 结合点表
    3. 报告语料弱关键词（仅补缺）
    4. product_attributes 时装维（设计款报告节点解析结果）

    明确不做：竞品种子、AZ 输入链接、纯干预下拉（那些是输入侧）。
    """
    attrs: list[QueryAttribute] = []
    seen_keys: set[str] = set()
    corpus = _collect_report_corpus(result)

    for obj in _iter_json_objects(corpus):
        for peer_key, label, value in _attrs_from_fusion_structures(obj):
            _add_attr(attrs, seen_keys, peer_key=peer_key, label=label, value=value, source="synthesis_report")

    for peer_key, label, value in _attrs_from_labeled_report_fields(corpus):
        _add_attr(attrs, seen_keys, peer_key=peer_key, label=label, value=value, source="synthesis_report")

    for peer_key, label, value in _attrs_from_text_blob(corpus):
        _add_attr(attrs, seen_keys, peer_key=peer_key, label=label, value=value, source="synthesis_report")

    product_attrs = result.product_attributes or {}
    for src_key, peer_key, label in [
        ("silhouette", "silhouette", "版型"),
        ("neckline", "neckline", "领型"),
        ("neckline_shoulder", "neckline", "领型"),
        ("fabric", "fabric", "面料"),
        ("dress_length", "dress_length", "裙长"),
        ("length", "dress_length", "裙长"),
        ("color", "color_family", "色彩"),
        ("color_print", "color_family", "色彩"),
        ("primary_color", "color_family", "色彩"),
    ]:
        raw = product_attrs.get(src_key)
        if raw is None:
            continue
        if isinstance(raw, dict):
            raw = raw.get("overall") or raw.get("value") or raw.get("name")
        if isinstance(raw, list):
            val = ", ".join(str(x) for x in raw if str(x).strip())
        else:
            val = str(raw or "").strip()
        if val in {"待 GPT 面料工艺分析回填", "参考图可见面料（POC）", "属性待补"}:
            continue
        _add_attr(attrs, seen_keys, peer_key=peer_key, label=label, value=val, source="synthesis_report")

    return attrs


def build_copilot_query(result: SynthesisResult, query_attrs: list[QueryAttribute]) -> str:
    parts = [f"{a.label}/{a.key}={a.value}" for a in query_attrs]
    attr_line = "; ".join(parts) if parts else ""
    pa = result.product_attributes or {}
    title_hint = pa.get("design_name_zh") or pa.get("design_name") or "AI generated dress design"

    if not attr_line:
        return (
            "I need Azazie dresses similar to an AI-generated design, but the synthesis report "
            "did not expose structured product attributes yet. Return few Atelier/formal candidates "
            "with silhouette, neckline, fabric, dressLength, colorFamily for manual review only."
        )

    return " ".join(
        [
            "Find existing Azazie dresses most similar to this AI-generated NEW design (not the competitor input).",
            f"Design name hint: {title_hint}.",
            f"Attributes extracted from the synthesis/design report: {attr_line}.",
            "Prefer Atelier / formal / bridesmaid. Return products including silhouette, neckline, fabric, dressLength, colorFamily.",
            "Do not optimize for the competitor seed product; optimize for the generated design attributes above.",
        ]
    )


# 重叠度权重：核心廓形/领/面料/色 高于裙长与特征
_SCORE_WEIGHTS = {
    "silhouette": 1.4,
    "neckline": 1.3,
    "fabric": 1.2,
    "color_family": 1.2,
    "dress_length": 0.8,
    "features": 0.6,
}


def score_overlap(
    query_attrs: list[QueryAttribute],
    peer: dict[str, Any],
) -> tuple[float, list[str], str, str]:
    if not query_attrs:
        return 0.0, [], "unknown", "缺少新款属性输入，重叠度不可判"

    matched: list[str] = []
    weight_hit = 0.0
    weight_total = 0.0

    for qa in query_attrs:
        peer_vals = peer.get(qa.key) or []
        if qa.key == "color_family" and peer.get("color"):
            peer_vals = list(peer_vals) + [str(peer.get("color"))]
        if not isinstance(peer_vals, list):
            peer_vals = [str(peer_vals)]
        if not any(str(x).strip() for x in peer_vals):
            continue
        w = _SCORE_WEIGHTS.get(qa.key, 1.0)
        weight_total += w
        if _values_overlap(qa.value, [str(x) for x in peer_vals]):
            weight_hit += w
            matched.append(f"{qa.label}≈{qa.value}")

    if weight_total <= 0:
        return 0.0, [], "unknown", "召回款缺少可比属性字段"

    score = weight_hit / weight_total
    # 至少命中 2 个核心维，或加权分高，才标高风险
    core_hits = sum(1 for m in matched if any(k in m for k in ("版型", "领型", "面料", "色彩")))
    if score >= 0.7 and core_hits >= 2:
        risk, label = "high", f"高重叠 {int(score * 100)}% · 建议标记相似款或强差异化"
    elif score >= 0.4 and (core_hits >= 1 or len(matched) >= 2):
        risk, label = "medium", f"中重叠 {int(score * 100)}% · 注意差异化卖点"
    elif len(matched) == 0:
        risk, label = "low", "低重叠 · 属性基本不重合（可作弱参考）"
    else:
        risk, label = "low", f"低重叠 {int(score * 100)}% · 可作参考"
    return score, matched, risk, label


def _peer_to_card(
    peer: dict[str, Any],
    query_attrs: list[QueryAttribute],
    *,
    excluded: bool,
    source: str,
) -> SimilarPeerCard:
    score, matched, risk, label = score_overlap(query_attrs, peer)
    attrs = {
        k: list(peer.get(k) or [])
        for k in ("silhouette", "neckline", "fabric", "dress_length", "color_family", "features")
        if peer.get(k)
    }
    return SimilarPeerCard(
        goods_id=str(peer.get("goods_id") or ""),
        product_id=str(peer.get("product_id") or ""),
        name=str(peer.get("name") or ""),
        url=str(peer.get("url") or ""),
        image_url=str(peer.get("image_url") or ""),
        price=peer.get("price"),
        category_name=str(peer.get("category_name") or ""),
        color=str(peer.get("color") or ""),
        attributes=attrs,
        matched_attributes=matched,
        overlap_score=round(score, 3),
        overlap_risk=risk,  # type: ignore[arg-type]
        overlap_label=label,
        excluded=excluded,
        source=source,  # type: ignore[arg-type]
    )


def get_exclusions(task_id: str) -> set[str]:
    with _LOCK:
        return set(_EXCLUSIONS.get(task_id, set()))


def set_exclusion(task_id: str, goods_id: str, excluded: bool) -> list[str]:
    """标记/取消标记相似款（字段名 excluded 为历史兼容；语义=已标记相似）。"""
    from app.services import synthesis_service

    gid = str(goods_id).strip()
    with _LOCK:
        bucket = _EXCLUSIONS.setdefault(task_id, set())
        if excluded:
            bucket.add(gid)
        else:
            bucket.discard(gid)
        marked_ids = sorted(bucket)
    # 回写任务：历史红标 + 不进选品企划池
    synthesis_service.sync_similar_style_mark(task_id, marked_ids)
    return marked_ids


def _apply_exclusions(resp: SimilarPeersResponse) -> SimilarPeersResponse:
    excluded = get_exclusions(resp.task_id)
    peers = []
    for p in resp.peers:
        peers.append(p.model_copy(update={"excluded": p.goods_id in excluded}))
    # 高重叠未标记的排前；已标记相似款沉底
    peers.sort(key=lambda c: (c.excluded, -c.overlap_score, c.name))
    return resp.model_copy(update={"peers": peers, "excluded_goods_ids": sorted(excluded)})


def _local_response(
    task_id: str,
    query_attrs: list[QueryAttribute],
    query_text: str,
    *,
    reason: str = "",
    status: str = "ready",
) -> SimilarPeersResponse:
    peers = _load_local_index()
    cards = [
        _peer_to_card(p, query_attrs, excluded=False, source="demo_fallback")
        for p in peers
    ]
    cards.sort(key=lambda c: -c.overlap_score)
    hint = (
        "半真本地索引：按合成报告属性做文本匹配；可「标记相似款」→ 历史红标且不进选品企划池。"
        "不依赖线上 Algolia / az-copilot。"
    )
    if reason:
        hint = f"{hint}（{reason}）"
    return SimilarPeersResponse(
        task_id=task_id,
        status=status if cards else "empty",
        source="demo_fallback",
        query_text=query_text,
        query_attributes=query_attrs,
        hint=hint,
        peers=cards[:12],
        error_message=reason or None,
    )


def get_generated_attributes(task_id: str) -> GeneratedAttributesResponse:
    """仅从合成/设计报告解析新款基本属性，不调用 az-copilot。"""
    result = result_store.get(task_id)
    if result is None:
        return GeneratedAttributesResponse(
            task_id=task_id,
            status="error",
            hint="合成任务不存在或已过期",
            error_message="task_not_found",
        )
    if result.status != SynthesisStatus.SUCCEEDED:
        return GeneratedAttributesResponse(
            task_id=task_id,
            status="empty",
            hint="生成尚未完成，完成后可展示报告中的新款属性",
            error_message="task_not_ready",
        )

    attrs = extract_query_attributes(result)
    # 展示顺序：版型 → 领型 → 面料 → 裙长 → 色彩 → 其它
    order = ["silhouette", "neckline", "fabric", "dress_length", "color_family", "features"]
    attrs_sorted = sorted(
        attrs,
        key=lambda a: order.index(a.key) if a.key in order else len(order),
    )
    if not attrs_sorted:
        return GeneratedAttributesResponse(
            task_id=task_id,
            status="empty",
            hint="合成报告中暂未解析到结构化商品属性（需报告含 fusion_plan / 设计规格 / 标签字段）",
            attributes=[],
        )
    return GeneratedAttributesResponse(
        task_id=task_id,
        status="ready",
        hint="以下属性解析自合成/设计报告，代表 AI 生成新款（非输入竞品）",
        attributes=attrs_sorted,
    )


def recall_similar_peers(task_id: str, *, refresh: bool = False) -> SimilarPeersResponse:
    result = result_store.get(task_id)
    if result is None:
        return SimilarPeersResponse(
            task_id=task_id,
            status="error",
            hint="合成任务不存在或已过期",
            error_message="task_not_found",
        )
    if result.status != SynthesisStatus.SUCCEEDED:
        return SimilarPeersResponse(
            task_id=task_id,
            status="empty",
            hint="生成尚未完成，完成后再召回相似款",
            error_message="task_not_ready",
        )

    with _LOCK:
        if not refresh and task_id in _CACHE:
            return _apply_exclusions(_CACHE[task_id])

    query_attrs = extract_query_attributes(result)
    query_text = build_copilot_query(result, query_attrs)

    # 本期默认：半真本地索引（计划 Q7=B）。仅显式打开 USE_COPILOT 时才打 az-copilot。
    if not _USE_COPILOT:
        resp = _local_response(task_id, query_attrs, query_text)
        with _LOCK:
            _CACHE[task_id] = resp
        return _apply_exclusions(resp)

    chat = az_copilot_client.call_chat(
        query_text,
        session_id=f"bloom_{task_id}",
        images=list(result.az_product_image_urls or [])[:2]
        or ([result.source_image_url] if result.source_image_url else []),
    )
    if chat.error or not chat.products:
        reason = chat.error or "copilot 未返回商品卡"
        logger.info(
            "similar peers fallback local task=%s api=%s reason=%s",
            task_id,
            chat.api_mode,
            reason,
        )
        resp = _local_response(
            task_id,
            query_attrs,
            query_text,
            reason=reason,
            status="degraded",
        )
        resp.elapsed_ms = chat.elapsed_ms
        resp.answer_preview = (chat.answer_text or "")[:500]
        with _LOCK:
            _CACHE[task_id] = resp
        return _apply_exclusions(resp)

    cards = [
        _peer_to_card(p, query_attrs, excluded=False, source="az_copilot")
        for p in chat.products
    ]
    cards.sort(key=lambda c: -c.overlap_score)

    if not query_attrs:
        hint = (
            f"已召回站内款（{chat.api_mode}），但合成报告未解析出可用「新款商品属性」"
            "（缺 fusion_plan / 设计规格字段），重叠度不可判。请确认 GPU 报告节点已产出结合点表后再重新召回。"
        )
        status = "degraded"
    else:
        hint = (
            f"属性召回自 az-copilot（{chat.api_mode}）；"
            "重叠度对照维来自合成/设计报告中的新款商品属性（非竞品输入）。"
            "高重叠且核心维命中建议「标记相似款」（历史红标，不进企划池）。"
        )
        status = "ready" if cards else "empty"

    resp = SimilarPeersResponse(
        task_id=task_id,
        status=status,
        source="az_copilot",
        query_text=query_text,
        query_attributes=query_attrs,
        hint=hint,
        answer_preview=(chat.answer_text or "")[:500],
        elapsed_ms=chat.elapsed_ms,
        peers=cards[:12],
    )
    with _LOCK:
        _CACHE[task_id] = resp
    return _apply_exclusions(resp)

"""
裙装属性下拉词表：合并 AZ Atelier 常见筛选口径 + 竞品站（Babyboo 等）采集属性。

用于「人为干预」各设计维的下拉选项；后续可替换为 md_attribute_dict / 实时接口。
"""
from __future__ import annotations

import re
from typing import Any

# 每个维：key / 中文标签 / 选项（value 英文或站内惯用写法，label 展示文案，source=az|competitor|both）
INTERVENTION_DIMENSIONS: list[dict[str, Any]] = [
    {
        "key": "silhouette",
        "label": "廓形 / 版型",
        "options": [
            {"value": "A-Line", "label": "A-Line 公主线", "source": "az"},
            {"value": "Column", "label": "Column 直筒", "source": "az"},
            {"value": "Sheath", "label": "Sheath 修身", "source": "az"},
            {"value": "Fit and Flare", "label": "Fit and Flare 收腰伞摆", "source": "az"},
            {"value": "Mermaid", "label": "Mermaid 鱼尾", "source": "az"},
            {"value": "Ball Gown", "label": "Ball Gown 蓬蓬裙", "source": "az"},
            {"value": "Empire", "label": "Empire 高腰", "source": "az"},
            {"value": "Column shaped skirt", "label": "Column Skirt 直筒裙身", "source": "competitor"},
            {"value": "Flared Skirt", "label": "Flared Skirt 喇叭摆", "source": "competitor"},
            {"value": "Bias Cut", "label": "Bias Cut 斜裁", "source": "competitor"},
            {"value": "Flowy Silhouette", "label": "Flowy 飘逸廓形", "source": "competitor"},
        ],
    },
    {
        "key": "neckline_shoulder",
        "label": "领口 / 肩型",
        "options": [
            {"value": "V-Neck", "label": "V-Neck V领", "source": "az"},
            {"value": "Sweetheart", "label": "Sweetheart 心形领", "source": "az"},
            {"value": "Scoop", "label": "Scoop 圆领", "source": "az"},
            {"value": "Square Neckline", "label": "Square 方领", "source": "both"},
            {"value": "Strapless", "label": "Strapless 抹胸", "source": "both"},
            {"value": "One Shoulder", "label": "One Shoulder 单肩", "source": "both"},
            {"value": "Halter", "label": "Halter 挂脖", "source": "az"},
            {"value": "Off the Shoulder", "label": "Off-Shoulder 露肩", "source": "az"},
            {"value": "Cowl Neckline", "label": "Cowl 垂褶领", "source": "competitor"},
            {"value": "Plunge Neckline", "label": "Plunge 深V", "source": "competitor"},
            {"value": "High Neck", "label": "High Neck 高领", "source": "both"},
            {"value": "Bardot", "label": "Bardot 一字肩", "source": "competitor"},
            {"value": "Asymmetric", "label": "Asymmetric 不对称", "source": "competitor"},
        ],
    },
    {
        "key": "sleeve",
        "label": "袖型",
        "options": [
            {"value": "Sleeveless", "label": "无袖", "source": "az"},
            {"value": "Spaghetti Straps", "label": "细肩带", "source": "both"},
            {"value": "Thin Straps", "label": "细带", "source": "competitor"},
            {"value": "Cap Sleeve", "label": "盖袖", "source": "az"},
            {"value": "Short Sleeve", "label": "短袖", "source": "az"},
            {"value": "Long Sleeve", "label": "长袖", "source": "az"},
            {"value": "Flutter Sleeve", "label": "荷叶袖", "source": "az"},
            {"value": "Off Shoulder Sleeve", "label": "露肩袖", "source": "az"},
        ],
    },
    {
        "key": "waist",
        "label": "腰线 / 腰臀",
        "options": [
            {"value": "Natural Waist", "label": "自然腰", "source": "az"},
            {"value": "Defined Waist", "label": "收腰强调", "source": "az"},
            {"value": "Empire Waist", "label": "高腰 Empire", "source": "az"},
            {"value": "Dropped Waist", "label": "落腰 Dropped", "source": "competitor"},
            {"value": "Corset Bodice", "label": "胸衣 / 鱼骨收腰", "source": "competitor"},
            {"value": "Lace-Up Back", "label": "系带后背收腰", "source": "competitor"},
            {"value": "V-Waist Seam", "label": "V形腰线拼接", "source": "az"},
            {"value": "Ruched Waist", "label": "抽褶腰部", "source": "competitor"},
        ],
    },
    {
        "key": "skirt_hem",
        "label": "裙摆 / 下摆",
        "options": [
            {"value": "Straight Hem", "label": "平摆", "source": "az"},
            {"value": "Layered Hem", "label": "层叠裙摆", "source": "az"},
            {"value": "High-Low Hem", "label": "前短后长", "source": "az"},
            {"value": "Godet Panels", "label": "插角 / Godet", "source": "competitor"},
            {"value": "Cowl Overlay Skirt", "label": "垂褶罩裙", "source": "competitor"},
            {"value": "Thigh High Split", "label": "高开叉", "source": "competitor"},
            {"value": "Full Gathered Skirt", "label": "抽褶丰盈裙摆", "source": "competitor"},
            {"value": "Pleated Skirt", "label": "褶裥裙摆", "source": "both"},
        ],
    },
    {
        "key": "length",
        "label": "衣长 / 裙长",
        "options": [
            {"value": "Mini", "label": "Mini 短裙", "source": "az"},
            {"value": "Tea Length", "label": "Tea Length 茶长", "source": "az"},
            {"value": "Midi", "label": "Midi 及小腿", "source": "both"},
            {"value": "Maxi", "label": "Maxi 及地", "source": "both"},
            {"value": "Floor Length", "label": "Floor Length 拖地", "source": "az"},
            {"value": "Sweep Train", "label": "轻拖尾", "source": "az"},
        ],
    },
    {
        "key": "fabric",
        "label": "面料 / 质感",
        "options": [
            {"value": "Chiffon", "label": "Chiffon 雪纺", "source": "both"},
            {"value": "Satin", "label": "Satin 缎面", "source": "both"},
            {"value": "Stretch Satin", "label": "Stretch Satin 弹力缎", "source": "competitor"},
            {"value": "Crepe", "label": "Crepe 绉缎", "source": "both"},
            {"value": "Lace", "label": "Lace 蕾丝", "source": "both"},
            {"value": "Tulle", "label": "Tulle 网纱", "source": "both"},
            {"value": "Jersey", "label": "Jersey 针织", "source": "both"},
            {"value": "Mesh", "label": "Mesh 网眼", "source": "competitor"},
            {"value": "Sequins", "label": "Sequins 亮片", "source": "az"},
            {"value": "Velvet", "label": "Velvet 丝绒", "source": "az"},
        ],
    },
    {
        "key": "color_print",
        "label": "色彩 / 印花",
        "options": [
            {"value": "Solid Color", "label": "纯色", "source": "az"},
            {"value": "Floral Print", "label": "碎花印花", "source": "az"},
            {"value": "Abstract Print", "label": "抽象印花", "source": "az"},
            {"value": "Ombre", "label": "渐变", "source": "az"},
            {"value": "Metallic", "label": "金属光泽", "source": "az"},
            {"value": "Two-Tone", "label": "撞色双色", "source": "az"},
            {"value": "Burnout Print", "label": "烧花 / Burnout", "source": "competitor"},
            {"value": "Keep AZ Colorway", "label": "保留 AZ 现有配色", "source": "az"},
        ],
    },
]


def get_intervention_options_payload() -> dict[str, Any]:
    return {
        "dimensions": INTERVENTION_DIMENSIONS,
        "rules": {
            "require_selection_or_note": False,
            "require_generated_prompt": False,
            "prompt_is_actual_input": True,
            "hint": "人为干预可选。不填可直接一键合成；若填写属性/简述，可生成 Prompt 作为软约束入参。",
        },
    }


def _dim_by_key(key: str) -> dict[str, Any] | None:
    for dim in INTERVENTION_DIMENSIONS:
        if dim.get("key") == key:
            return dim
    return None


def _options_of(*keys: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for key in keys:
        dim = _dim_by_key(key)
        if not dim:
            continue
        for opt in dim.get("options") or []:
            value = str(opt.get("value") or "").strip()
            if not value or value.lower() in seen:
                continue
            seen.add(value.lower())
            out.append(opt)
    return out


# 爆款合成 / 商品分析 8 维（与 V13 人工干预属性下拉口径对齐）
ANALYSIS_DIMENSIONS: list[dict[str, Any]] = [
    {
        "key": "silhouette",
        "label": "silhouette · 廓形",
        "options": _options_of("silhouette"),
    },
    {
        "key": "neckline",
        "label": "neckline · 领型",
        "options": _options_of("neckline_shoulder"),
    },
    {
        "key": "waistline",
        "label": "waistline · 腰线",
        "options": _options_of("waist"),
    },
    {
        "key": "fabric",
        "label": "fabric · 面料",
        "options": _options_of("fabric"),
    },
    {
        "key": "dressLength",
        "label": "dressLength · 裙长",
        "options": _options_of("length"),
    },
    {
        "key": "colorFamily",
        "label": "colorFamily · 色系",
        "options": _options_of("color_print"),
    },
    {
        "key": "features",
        "label": "features · 特征",
        "options": _options_of("skirt_hem", "waist")
        + [
            {"value": "Draped", "label": "Draped 褶皱垂坠", "source": "competitor"},
            {"value": "Ruched", "label": "Ruched 抽褶", "source": "competitor"},
            {"value": "Bodycon", "label": "Bodycon 修身", "source": "competitor"},
            {"value": "Separates", "label": "Separates 分体", "source": "competitor"},
        ],
    },
    {
        "key": "sleeve",
        "label": "sleeve · 袖型",
        "options": _options_of("sleeve"),
    },
]


def get_analysis_dimensions_payload() -> dict[str, Any]:
    return {
        "dimensions": ANALYSIS_DIMENSIONS,
        "keys": [d["key"] for d in ANALYSIS_DIMENSIONS],
        "source": "V13 intervention attribute dropdown · dress_attr_catalog",
    }


def match_option(dim_key: str, raw: str) -> dict[str, Any] | None:
    """把自由文本 / 旧 dim 值对齐到分析维下拉选项。"""
    text = (raw or "").strip()
    if not text:
        return None
    dim = next((d for d in ANALYSIS_DIMENSIONS if d["key"] == dim_key), None)
    if not dim:
        return None
    low = text.lower()
    for opt in dim.get("options") or []:
        value = str(opt.get("value") or "")
        label = str(opt.get("label") or "")
        if low == value.lower() or low == label.lower():
            return opt
        if value.lower() in low or low in value.lower() or low in label.lower():
            return opt
    return None


ANALYSIS_DIM_KEYS = (
    "silhouette",
    "neckline",
    "waistline",
    "fabric",
    "dressLength",
    "colorFamily",
    "features",
    "sleeve",
)

# 爬虫 baseline metadata / 货盘卡 / Copilot 热销卡 → 8 维
_DIM_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "silhouette": ("silhouette",),
    "neckline": ("neckline", "neckline_shoulder"),
    "waistline": ("waistline", "waist", "waist_hip"),
    "fabric": ("fabric", "fabric_name"),
    "dressLength": ("dressLength", "dress_length", "length"),
    "colorFamily": ("colorFamily", "color_family", "color", "color_name"),
    "features": ("features", "pattern", "aesthetic_tag"),
    "sleeve": ("sleeve", "sleeves"),
}

_NOISE = {
    "adjustable strap",
    "adjustable straps",
    "strap",
    "straps",
    "n/a",
    "na",
    "none",
    "null",
    "-",
    "—",
}

_SHORT_OK = {
    "maxi",
    "midi",
    "mini",
    "lace",
    "slit",
    "cowl",
    "mesh",
    "tulle",
    "crepe",
    "satin",
    "bow",
}

_EXTRA_HINTS: dict[str, tuple[tuple[str, str], ...]] = {
    "silhouette": (
        ("ball gown", "Ball Gown"),
        ("fit and flare", "Fit and Flare"),
        ("fit & flare", "Fit and Flare"),
        ("a-line", "A-Line"),
        ("a line", "A-Line"),
        ("column", "Column"),
        ("mermaid", "Mermaid"),
        ("trumpet", "Mermaid"),
        ("sheath", "Sheath"),
        ("bodycon", "Bodycon"),
        ("bias cut", "Bias Cut"),
        ("flared skirt", "Flared Skirt"),
        ("empire", "Empire"),
    ),
    "neckline": (
        ("off the shoulder", "Off the Shoulder"),
        ("one shoulder", "One Shoulder"),
        ("square neck", "Square Neckline"),
        ("sweetheart", "Sweetheart"),
        ("cowl neck", "Cowl Neckline"),
        ("cowl", "Cowl Neckline"),
        ("v-neck", "V-Neck"),
        ("v neck", "V-Neck"),
        ("strapless", "Strapless"),
        ("halter", "Halter"),
        ("scoop", "Scoop"),
        ("bardot", "Bardot"),
        ("plunge", "Plunge Neckline"),
        ("high neck", "High Neck"),
        ("boat neck", "Boat Neck"),
        ("crew neck", "Crew Neck"),
    ),
    "waistline": (
        ("dropped waist", "Dropped Waist"),
        ("empire waist", "Empire Waist"),
        ("natural waist", "Natural Waist"),
        ("defined waist", "Defined Waist"),
        ("lace-up back", "Lace-Up Back"),
        ("lace up back", "Lace-Up Back"),
        ("corset", "Corset Bodice"),
        ("basque", "Defined Waist"),
        ("ruched waist", "Ruched Waist"),
    ),
    "fabric": (
        ("stretch satin", "Stretch Satin"),
        ("jacquard", "Jacquard"),
        ("chiffon", "Chiffon"),
        ("jersey", "Jersey"),
        ("velvet", "Velvet"),
        ("organza", "Organza"),
        ("sequin", "Sequins"),
        ("tulle", "Tulle"),
        ("crepe", "Crepe"),
        ("satin", "Satin"),
        ("mesh", "Mesh"),
        ("lace", "Lace"),
    ),
    "dressLength": (
        ("floor-length", "Floor Length"),
        ("floor length", "Floor Length"),
        ("tea length", "Tea Length"),
        ("maxi", "Maxi"),
        ("midi", "Midi"),
        ("mini", "Mini"),
    ),
    "features": (
        ("thigh high split", "Thigh High Split"),
        ("high split", "Thigh High Split"),
        ("side split", "Thigh High Split"),
        ("pleated", "Pleated Skirt"),
        ("draped", "Draped"),
        ("ruched", "Ruched"),
        ("bodycon", "Bodycon"),
        ("beaded", "Beaded"),
        ("ruffle", "Ruffle"),
        ("slit", "Thigh High Split"),
        ("wrap", "Wrap"),
    ),
    "sleeve": (
        ("spaghetti strap", "Spaghetti Straps"),
        ("off shoulder sleeve", "Off Shoulder Sleeve"),
        ("long sleeve", "Long Sleeve"),
        ("short sleeve", "Short Sleeve"),
        ("cap sleeve", "Cap Sleeve"),
        ("cape sleeve", "Cap Sleeve"),
        ("flutter sleeve", "Flutter Sleeve"),
        ("sleeveless", "Sleeveless"),
        ("thin strap", "Thin Straps"),
    ),
}


def _split_attr_values(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        out: list[str] = []
        for item in raw:
            out.extend(_split_attr_values(item))
        return out
    text = str(raw).strip()
    if not text:
        return []
    return [p.strip() for p in re.split(r"[/,，;|]+", text) if p.strip()]


def _clean_color_name(raw: str) -> str:
    text = re.split(r"[#/]", str(raw or ""), maxsplit=1)[0].strip()
    text = re.sub(r"^(SP|sp)\s+", "", text).strip()
    return text


def _is_noise(value: str) -> bool:
    low = (value or "").strip().lower()
    if not low or low in _NOISE:
        return True
    if re.fullmatch(r"[\d\s./-]+", low):
        return True
    if len(low) > 48:
        return True
    return False


def _append_point(bucket: list[dict[str, Any]], dim: str, raw: str) -> None:
    text = _clean_color_name(raw) if dim == "colorFamily" else str(raw or "").strip()
    if _is_noise(text):
        return
    matched = match_option(dim, text)
    value = str((matched or {}).get("value") or text).strip()
    label = str((matched or {}).get("label") or text).strip()
    if _is_noise(value):
        return
    key = value.lower()
    if any(str(p.get("value") or "").lower() == key for p in bucket):
        return
    bucket.append(
        {
            "dim": dim,
            "value": value,
            "label": label,
            "default_checked": True,
            "source": "crawler_table",
        }
    )


def _product_blob(card: dict[str, Any]) -> str:
    md = card.get("metadata") if isinstance(card.get("metadata"), dict) else {}
    parts = [
        card.get("title"),
        card.get("product_name"),
        card.get("name"),
        card.get("detail_text"),
        md.get("detail_text"),
        " ".join(str(x) for x in (card.get("attrs_display") or []) if x),
    ]
    return " ".join(str(x) for x in parts if x)


def hotspots_from_product(card: dict[str, Any] | None) -> list[dict[str, Any]]:
    """从爬虫表 / 货盘卡抽出 8 维爆点。对不上词表也保留原文，禁止把有值洗成空。"""
    card = dict(card or {})
    md = card.get("metadata") if isinstance(card.get("metadata"), dict) else {}
    sources = [card, md]
    by_dim: dict[str, list[dict[str, Any]]] = {k: [] for k in ANALYSIS_DIM_KEYS}

    for dim, aliases in _DIM_FIELD_ALIASES.items():
        for src in sources:
            for alias in aliases:
                if alias not in src or src.get(alias) in (None, ""):
                    continue
                for part in _split_attr_values(src.get(alias)):
                    _append_point(by_dim[dim], dim, part)

    blob = _product_blob(card).lower().replace("–", " ").replace("—", " ")
    if blob:
        for dim in ANALYSIS_DIM_KEYS:
            if dim != "features" and by_dim[dim]:
                continue
            for needle, canon in _EXTRA_HINTS.get(dim, ()):
                if needle in blob:
                    _append_point(by_dim[dim], dim, canon)
            dim_meta = next((d for d in ANALYSIS_DIMENSIONS if d["key"] == dim), None)
            opts = sorted(
                list(dim_meta.get("options") or []) if dim_meta else [],
                key=lambda o: len(str(o.get("value") or "")),
                reverse=True,
            )
            for opt in opts:
                value = str(opt.get("value") or "").strip()
                low = value.lower()
                if not low or (len(low) < 4 and low not in _SHORT_OK):
                    continue
                if low in blob:
                    _append_point(by_dim[dim], dim, value)

    points: list[dict[str, Any]] = []
    for dim in ANALYSIS_DIM_KEYS:
        limit = 3 if dim == "features" else 1
        points.extend(by_dim[dim][:limit])
    return points


def merge_hotspots(
    primary: list[dict[str, Any]] | None,
    extra: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for point in list(primary or []) + list(extra or []):
        dim = str(point.get("dim") or "features")
        value = str(point.get("value") or point.get("key") or point.get("label") or "").strip()
        if not value:
            continue
        key = f"{dim}:{value.lower()}"
        if key in seen:
            continue
        seen.add(key)
        out.append(point)
    return out


def dim_fields_from_hotspots(points: list[dict[str, Any]]) -> dict[str, str]:
    """给货盘筛选用的扁平字段；length/color 保持旧 key。"""
    first: dict[str, str] = {}
    features: list[str] = []
    for point in points or []:
        dim = str(point.get("dim") or "")
        value = str(point.get("value") or point.get("label") or "").strip()
        if not dim or not value:
            continue
        if dim == "features":
            if value not in features:
                features.append(value)
            continue
        first.setdefault(dim, value)
    out = {
        "silhouette": first.get("silhouette", ""),
        "neckline": first.get("neckline", ""),
        "waistline": first.get("waistline", ""),
        "fabric": first.get("fabric", ""),
        "dressLength": first.get("dressLength", ""),
        "length": first.get("dressLength", ""),
        "colorFamily": first.get("colorFamily", ""),
        "color": first.get("colorFamily", ""),
        "features": " / ".join(features),
        "pattern": features[0] if features else "",
        "sleeve": first.get("sleeve", ""),
    }
    return out

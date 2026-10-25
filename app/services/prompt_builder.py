"""
爆款合成 · 人为干预 Prompt 组装。

属性下拉选定值 + 自然语言简述 → 一键生成完整分析/生图导向 Prompt。
完整 Prompt 才是合成真正入参；属性与简述至少提供一种。
"""
from __future__ import annotations

from fastapi import HTTPException

from app.services.dress_attr_catalog import INTERVENTION_DIMENSIONS

_DIM_LABELS = {item["key"]: item["label"] for item in INTERVENTION_DIMENSIONS}


def _normalize_selections(
    selections: dict[str, str] | None,
    elements: list[str] | None = None,
) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in (selections or {}).items():
        text = str(value or "").strip()
        if text:
            cleaned[str(key)] = text
    # 兼容旧版只传 elements（无具体值）：记为「强化该维」
    if not cleaned and elements:
        for key in elements:
            if key:
                cleaned[str(key)] = "（强化该设计维，具体取值由分析步决定）"
    return cleaned


def validate_intervention_inputs(
    *,
    selections: dict[str, str] | None,
    elements: list[str] | None,
    note: str,
) -> dict[str, str]:
    cleaned = _normalize_selections(selections, elements)
    if not cleaned and not (note or "").strip():
        raise HTTPException(
            status_code=400,
            detail="请至少选择一项属性下拉，或填写自然语言简述",
        )
    return cleaned


def build_intervention_prompt(
    *,
    selections: dict[str, str] | None = None,
    elements: list[str] | None = None,
    note: str = "",
) -> str:
    """根据属性下拉 + 自然语言简述生成完整干预 Prompt。"""
    cleaned = validate_intervention_inputs(
        selections=selections,
        elements=elements,
        note=note,
    )

    if cleaned:
        lines = []
        for key, value in cleaned.items():
            label = _DIM_LABELS.get(key, key)
            lines.append(f"- {label}（{key}）→ 目标取值：{value}")
        elements_block = "\n".join(lines)
    else:
        elements_block = "- （未选具体属性值，按自然语言简述做软融合）"

    note_text = (note or "").strip() or "（无补充描述）"
    used_dims = ", ".join(cleaned.keys()) if cleaned else "（由简述推断）"

    return f"""【人为干预 · 软约束】本次合成须优先落实下列设计点，未列入的维不要主动向竞品靠拢。
属性词表来源：AZ Atelier 常见筛选 + 竞品裙装采集属性（如 Babyboo neckline/length/fabric）。

## 选定属性（下拉）
{elements_block}

## 运营自然语言简述
{note_text}

## 分析要求
分别拆解竞品图与 AZ 商品图在原子维上的卖点：silhouette, neckline_shoulder, fabric, color_print, waist, skirt_hem, sleeve, length。
先输出 JSON：competitor_take[]、az_keep[]、fusion_plan[]（每维 from=competitor|az|new）、attr_dims_used、control_mode=llm_soft。
attr_dims_used 必须覆盖：{used_dims}；若上方已给出目标取值，fusion_plan 对应维应尽量对齐该取值。
competitor_take 与 az_keep 各建议 ≤3 维。
再输出人读报告（含结合点对照表）。禁止只写「融合两者优点」；禁止无对照表直接进生图。

## 生图要求
仅按已冻结的 fusion_plan 生成电商八视图：from=competitor 对齐竞品图，from=az 对齐 AZ 图，from=new 按报告创作。
未列入 attr_dims_used 的维不要主动向竞品靠拢。说明：llm_soft，不保证像素级隔离。
"""

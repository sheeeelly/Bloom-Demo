"""
/api/synthesis — 爆款一键合成接口
  - POST /api/synthesis                  创建合成任务（GPU 模式立即返回 pending，POC 模式同步返回结果）
  - POST /api/synthesis/build-prompt     勾选元素 + 自然语言 → 一键生成完整干预 Prompt
  - GET  /api/synthesis                  历史生成列表（含设计款，按创建时间倒序）
  - GET  /api/synthesis/options          人为干预可选设计点
  - GET  /api/synthesis/{id}             查询合成结果/进度（前端轮询直至 succeeded / failed）
  - GET  /api/synthesis/{id}/download    下载 zip（仅 succeeded 后可用）
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.schemas.synthesis import (
    BuildPromptRequest,
    BuildPromptResponse,
    SynthesisListResponse,
    SynthesisRequest,
    SynthesisResult,
    SynthesisStatus,
)
from app.services import dress_attr_catalog, prompt_builder, synthesis_service

router = APIRouter(prefix="/api/synthesis", tags=["synthesis"])


@router.post("/build-prompt", response_model=BuildPromptResponse)
def build_prompt(payload: BuildPromptRequest) -> BuildPromptResponse:
    """人为干预：属性下拉 + 自然语言简述 → 生成完整 Prompt（真正合成入参）。"""
    selections = prompt_builder.validate_intervention_inputs(
        selections=payload.selections,
        elements=payload.elements,
        note=payload.note,
    )
    prompt = prompt_builder.build_intervention_prompt(
        selections=selections,
        note=payload.note,
    )
    return BuildPromptResponse(
        prompt=prompt,
        selections=selections,
        elements=list(selections.keys()),
        note=payload.note,
    )


@router.get("/options")
def intervention_options() -> dict:
    return dress_attr_catalog.get_intervention_options_payload()


@router.post("", response_model=SynthesisResult, status_code=202)
def create_synthesis(payload: SynthesisRequest) -> SynthesisResult:
    """点击「一键合成」后调用：基于 AZ URL + 单选竞品创建合成任务。"""
    az_url = payload.az_product_url.strip()
    if not az_url:
        raise HTTPException(status_code=400, detail="AZ 爆款商品 URL 为必填")
    if not payload.competitor_product_id.strip():
        raise HTTPException(status_code=400, detail="请单选 1 个竞品爆款商品")
    # 人为干预为可选：有 intervention_prompt 则注入工作流，无则按默认合成
    # 归一化 selections，并回填 elements
    selections = {
        k: v.strip()
        for k, v in (payload.intervention_selections or {}).items()
        if k and str(v).strip()
    }
    if not selections and payload.intervention_elements:
        selections = {k: "（强化该设计维）" for k in payload.intervention_elements if k}
    payload.intervention_selections = selections
    payload.intervention_elements = list(selections.keys())
    return synthesis_service.create_synthesis(payload)


@router.get("", response_model=SynthesisListResponse)
def list_synthesis(
    limit: int = 100,
    for_planning_pool: bool = Query(
        False,
        description="为 true 时只返回可进选品企划池的任务（排除已标记相似款）",
    ),
    status: str = Query("", description="pending|running|succeeded|failed|generating"),
    kind: str = Query("", description="hot_synthesis|design"),
) -> SynthesisListResponse:
    """成品库 / 历史列表：按创建时间倒序，可按状态与类型过滤。"""
    return SynthesisListResponse(
        items=synthesis_service.list_syntheses(
            limit=limit,
            for_planning_pool=for_planning_pool,
            status=status or None,
            kind=kind or None,
        )
    )


@router.get("/{task_id}", response_model=SynthesisResult)
def get_synthesis(task_id: str) -> SynthesisResult:
    result = synthesis_service.get_synthesis(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="合成结果不存在（未入库或 ID 错误）")
    return result


@router.get("/{task_id}/download")
def download_synthesis(task_id: str) -> Response:
    result = synthesis_service.get_synthesis(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="合成结果不存在（未入库或 ID 错误）")
    if result.status != SynthesisStatus.SUCCEEDED:
        raise HTTPException(status_code=409, detail=f"合成尚未完成（当前状态：{result.status.value}），暂不可下载")

    zip_bytes = synthesis_service.build_download_zip(result)
    kind = result.kind.value if result.kind else "hot_synthesis"
    filename = f"bloom-{kind}-{task_id}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

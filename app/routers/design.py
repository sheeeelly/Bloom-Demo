"""
/api/design — 方案三 季节灵感 → AI开款

  - GET  /api/design/packs
  - GET  /api/design/packs/{filename}
  - POST /api/design/preview-prompt
  - POST /api/design
  - GET  /api/design/files/{name}
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.schemas.synthesis import SynthesisResult
from app.services import design_service, nybfw_prompt

router = APIRouter(prefix="/api/design", tags=["design"])

_MAX_UPLOAD_BYTES = 15 * 1024 * 1024


class PreviewPromptRequest(BaseModel):
    pack_file: str = ""
    category: str = "AT"
    cluster_ids: list[str] = Field(default_factory=list)
    pantone_enabled: bool = False


@router.get("/packs")
def list_packs() -> dict[str, Any]:
    return {
        "packs": nybfw_prompt.list_packs(),
        "categories": list(nybfw_prompt.CATEGORIES),
        "default_pack_by_category": dict(nybfw_prompt.DEFAULT_PACK_BY_CATEGORY),
        "image_policy": {
            "phase1": "no_magazine_crawl_text_led",
            "phase2": "auto_attach_editorial_image_per_cluster",
        },
    }


@router.get("/packs/{filename}")
def get_pack(filename: str) -> dict[str, Any]:
    try:
        pack = nybfw_prompt.load_pack(filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"file": filename, "pack": pack}


@router.post("/preview-prompt")
def preview_prompt(body: PreviewPromptRequest) -> dict[str, Any]:
    pack_file = body.pack_file or nybfw_prompt.default_pack_for_category(body.category)
    try:
        pack = nybfw_prompt.load_pack(pack_file, category=body.category)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    built = nybfw_prompt.build_prompts(
        pack=pack,
        category=body.category,
        selected_cluster_ids=body.cluster_ids,
        pantone_enabled=body.pantone_enabled,
    )
    built["pack_file"] = pack_file
    return built


@router.post("", response_model=SynthesisResult, status_code=202)
async def create_design(
    file: UploadFile | None = File(None, description="可选参考图；一期可不传"),
    pack_file: str = Form(""),
    category: str = Form("AT"),
    cluster_ids: str = Form("", description="逗号分隔 cluster_id"),
    pantone_enabled: str = Form("false"),
    inspiration_url: str = Form(""),
    design_prompt_override: str = Form(""),
    analysis_prompt_override: str = Form(""),
) -> SynthesisResult:
    clusters = [x.strip() for x in cluster_ids.split(",") if x.strip()]
    if not clusters:
        raise HTTPException(status_code=400, detail="请至少勾选 1 个趋势芯片")
    pantone = str(pantone_enabled).strip().lower() in {"1", "true", "yes", "on"}
    resolved_pack = (pack_file or "").strip() or nybfw_prompt.default_pack_for_category(category)

    content: bytes | None = None
    filename = "reference.jpg"
    image_is_placeholder = False
    if file is not None and file.filename:
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="请上传图片文件（image/*）")
        content = await file.read()
        filename = file.filename or "reference.jpg"
    elif inspiration_url.strip():
        resolved = design_service.resolve_inspiration_bytes(inspiration_url.strip())
        if not resolved:
            raise HTTPException(status_code=400, detail="无法加载灵感图 URL")
        content, filename = resolved
    else:
        # 一期：无杂志爬图，使用技术占位图，生成由可编辑 Prompt 主导
        image_is_placeholder = True

    if content is not None:
        if not content:
            raise HTTPException(status_code=400, detail="上传文件为空")
        if len(content) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="图片过大，请控制在 15MB 以内")

    try:
        nybfw_prompt.load_pack(resolved_pack, category=category)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return design_service.create_design(
        content,
        filename=filename,
        pack_file=resolved_pack,
        category=category,
        cluster_ids=clusters,
        pantone_enabled=pantone,
        design_prompt_override=design_prompt_override,
        analysis_prompt_override=analysis_prompt_override,
        image_is_placeholder=image_is_placeholder,
    )


@router.get("/files/{filename}")
def get_design_file(filename: str) -> FileResponse:
    path = design_service.resolve_upload_path(filename)
    if path is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    media = "image/jpeg"
    suffix = path.suffix.lower()
    if suffix == ".png":
        media = "image/png"
    elif suffix == ".webp":
        media = "image/webp"
    elif suffix == ".gif":
        media = "image/gif"
    return FileResponse(path, media_type=media, headers={"Cache-Control": "no-cache"})

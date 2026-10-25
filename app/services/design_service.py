"""
方案三 · NYBFW 季节灵感企划 → AI开款（面料分析 / 重设计 / 八视图）。

POC：本地保存原图，产出 8 视角占位图 + 报告。
GPU：上传至 ComfyUI；注入 analysis_prompt / design_prompt 追加块。
"""
from __future__ import annotations

import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import config
from app.schemas.synthesis import (
    GeneratedImage,
    ReportDoc,
    SynthesisResult,
    SynthesisStatus,
    TaskKind,
)
from app.services import comfy_client, instance_power_service, nybfw_prompt, result_store, synthesis_service

logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="design-gpu")

_UPLOAD_DIR = Path(config.BASE_DIR) / "data" / "uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_IMAGE_SPECS = synthesis_service._IMAGE_SPECS  # noqa: SLF001


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_url(task_id: str, ext: str) -> str:
    return f"/api/design/files/{task_id}{ext}"


def _poc_attributes(task_id: str, meta: dict[str, Any]) -> dict:
    return {
        "design_name_zh": f"季节企划款-{task_id[:6]}",
        "category": meta.get("category") or "AT",
        "season": meta.get("season") or "",
        "clusters": meta.get("clusters") or "",
        "planning": {
            "season": meta.get("season"),
            "category": meta.get("category"),
            "selected_clusters": meta.get("clusters"),
            "image_policy": meta.get("image_policy"),
        },
        "target_customer_and_scene": "季节灵感企划 · Demo",
        "commercial_positioning": "基于 Vogue 人工灵感包的原创重设计（文本主导）",
        "silhouette": {
            "overall": "待 GPT 面料工艺分析回填",
            "neckline_shoulder": "待回填",
            "sleeves": "待回填",
            "waist_hip": "待回填",
            "length_hem": "待回填",
        },
        "material_plan": [
            {
                "material": "由 design_prompt / 分析节点决定",
                "placement": "全身",
                "weight_drape": "unknown",
                "reason": "一期无杂志真图时以文本企划主导",
            }
        ],
        "commercial_selling_points": [
            "季节趋势芯片驱动",
            "提示词可编辑干预",
            "一期不按潘通色向开款",
        ],
        "source": "scheme3_season_poc",
        "workflow": "AI开款_GPT5.5_面料工艺分析_爆款重设计_GPImage2",
        "analysis_prompt_append": meta.get("analysis_prompt_append") or "",
        "design_prompt_append": meta.get("design_prompt_append") or "",
    }


def _poc_report(task_id: str, attrs: dict) -> str:
    planning = attrs.get("planning") or {}
    return f"""# 产品设计报告（方案三 · 季节灵感 AI开款）

## 企划摘要
- 任务 ID：{task_id}
- 季节：{attrs.get("season") or planning.get("season") or "—"}
- 品类：{attrs.get("category") or planning.get("category") or "—"}
- 趋势芯片：{attrs.get("clusters") or planning.get("selected_clusters") or "—"}
- 图片策略：{planning.get("image_policy") or attrs.get("image_policy") or "—"}（一期无杂志爬图）

## 说明
人工灵感包 → 趋势芯片 → **可编辑提示词** → AI开款。
一期不做 Vogue 自动爬图；潘通色向默认关闭。

## Prompt（实际注入）

### analysis_prompt_append
```
{attrs.get("analysis_prompt_append") or "（无）"}
```

### design_prompt_append
```
{attrs.get("design_prompt_append") or "（无）"}
```

## 产品属性
详见同页「产品属性」与下载包 `product_attributes.json`。
"""


def resolve_inspiration_bytes(inspiration_url: str) -> tuple[bytes, str] | None:
    """从本地 static 路径或 http(s) 拉取灵感图。"""
    url = (inspiration_url or "").strip()
    if not url:
        return None
    if url.startswith("/static/"):
        local = Path(config.BASE_DIR) / "app" / url.lstrip("/")
        # url is /static/... → app/static/...
        local = Path(config.BASE_DIR) / "app" / "static" / url[len("/static/") :]
        if local.is_file():
            return local.read_bytes(), local.name
        return None
    if url.startswith("http://") or url.startswith("https://"):
        try:
            req = Request(url, headers={"User-Agent": "az-bloom-design/1.0"})
            with urlopen(req, timeout=20) as resp:  # noqa: S310 — demo 拉取公开图
                data = resp.read()
            name = Path(url.split("?", 1)[0]).name or "inspiration.jpg"
            return data, name
        except (URLError, TimeoutError, OSError) as exc:
            logger.warning("inspiration download failed: %s", exc)
            return None
    return None


_DEFAULT_PLACEHOLDER_URL = "/static/gallery/AT/at-001_01.jpg"


def create_design(
    image_bytes: bytes | None = None,
    *,
    filename: str = "reference.jpg",
    pack_file: str = "",
    category: str = "AT",
    cluster_ids: list[str] | None = None,
    pantone_enabled: bool = False,
    design_prompt_override: str = "",
    analysis_prompt_override: str = "",
    image_is_placeholder: bool = False,
) -> SynthesisResult:
    """创建设计款 / 方案三任务。一期可无杂志图，用技术占位图 + 文本 Prompt。"""
    task_id = uuid.uuid4().hex[:12]
    now = _now_iso()

    resolved_pack = (pack_file or "").strip() or nybfw_prompt.default_pack_for_category(category)
    pack = nybfw_prompt.load_pack(resolved_pack, category=category)
    prompt_meta = nybfw_prompt.build_prompts(
        pack=pack,
        category=category,
        selected_cluster_ids=list(cluster_ids or []),
        pantone_enabled=pantone_enabled,
    )
    if (design_prompt_override or "").strip():
        prompt_meta["design_prompt_append"] = design_prompt_override.strip()
    if (analysis_prompt_override or "").strip():
        prompt_meta["analysis_prompt_append"] = analysis_prompt_override.strip()

    if image_bytes is None:
        resolved = resolve_inspiration_bytes(_DEFAULT_PLACEHOLDER_URL)
        if not resolved:
            raise FileNotFoundError("缺少技术占位图，无法提交开款任务")
        image_bytes, filename = resolved
        image_is_placeholder = True

    meta = {
        **prompt_meta,
        "pack_file": resolved_pack,
        "pantone_enabled": pantone_enabled,
        "image_is_placeholder": image_is_placeholder,
        "image_policy": (
            "phase1_text_led_no_magazine_crawl"
            if image_is_placeholder
            else "user_or_manual_image"
        ),
    }

    suffix = Path(filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        suffix = ".jpg"
    save_path = _UPLOAD_DIR / f"{task_id}{suffix}"
    save_path.write_bytes(image_bytes)
    source_url = _source_url(task_id, suffix)

    if instance_power_service.gpu_enabled():
        result = SynthesisResult(
            id=task_id,
            kind=TaskKind.DESIGN,
            status=SynthesisStatus.PENDING,
            mode="gpu",
            progress_message="NYBFW 企划已提交，等待 GPU 实例就绪...",
            source_image_url=source_url,
            competitor_product_title=f"NYBFW · {meta.get('season')} · {meta.get('category')}",
            competitor_product_image_url=source_url,
            intervention_prompt=meta.get("design_prompt_append") or "",
            product_attributes={
                "season": meta.get("season"),
                "category": meta.get("category"),
                "clusters": meta.get("clusters"),
                "planning": {
                    "season": meta.get("season"),
                    "category": meta.get("category"),
                    "selected_clusters": meta.get("clusters"),
                    "image_policy": meta.get("image_policy"),
                },
                "analysis_prompt_append": meta.get("analysis_prompt_append"),
                "design_prompt_append": meta.get("design_prompt_append"),
            },
            created_at=now,
            updated_at=now,
        )
        result_store.put(result)
        logger.info("design(gpu) created id=%s category=%s", task_id, category)
        _EXECUTOR.submit(_run_gpu_design, task_id, save_path, meta)
        return result

    attrs = _poc_attributes(task_id, meta)
    images = [
        GeneratedImage(id=f"{task_id}-{index + 1}", label=label, url=source_url)
        for index, (label, _slug) in enumerate(_IMAGE_SPECS)
    ]
    report_docs = [
        ReportDoc(
            key="报告1",
            title="面料与工艺分析（POC）",
            content="POC：正式环境回填 GPT-5.5 面料/结构分析。已附带 NYBFW analysis 追加块。",
        ),
        ReportDoc(
            key="报告2",
            title="原创爆款设计规格（POC）",
            content=json.dumps(attrs, ensure_ascii=False, indent=2),
        ),
        ReportDoc(
            key="报告3",
            title="Designer Brief（注入 Prompt）",
            content=meta.get("design_prompt_append") or "",
        ),
    ]
    result = SynthesisResult(
        id=task_id,
        kind=TaskKind.DESIGN,
        status=SynthesisStatus.SUCCEEDED,
        mode="poc",
        progress_message="已完成（POC · NYBFW 企划占位）",
        source_image_url=source_url,
        competitor_product_title=str(attrs.get("design_name_zh") or "设计款"),
        competitor_product_image_url=source_url,
        product_attributes=attrs,
        images=images,
        report_markdown=_poc_report(task_id, attrs),
        report_docs=report_docs,
        intervention_prompt=meta.get("design_prompt_append") or "",
        created_at=now,
        updated_at=now,
    )
    result_store.put(result)
    logger.info("design(poc) created id=%s", task_id)
    return result


def resolve_upload_path(filename: str) -> Path | None:
    name = Path(filename).name
    path = _UPLOAD_DIR / name
    if not path.is_file():
        return None
    if path.resolve().parent != _UPLOAD_DIR.resolve():
        return None
    return path


def _run_gpu_design(task_id: str, image_path: Path, meta: dict[str, Any]) -> None:
    def _update(**changes: object) -> None:
        result_store.update(task_id, **changes, updated_at=_now_iso())

    try:
        _update(status=SynthesisStatus.RUNNING, progress_message="正在检查 GPU 实例状态...")
        comfy_base_url = instance_power_service.ensure_instance_ready()
        instance_power_service.touch_usage()

        image_bytes = image_path.read_bytes()
        uploaded_name = comfy_client.upload_image_bytes(
            comfy_base_url, image_path.name, image_bytes
        )

        template_path = Path(config.COMFY_FASHION_WORKFLOW_TEMPLATE_PATH)
        use_formal = template_path.is_file()
        final_node_id: str | None = None
        report_nodes: list[dict[str, str]] = []

        if use_formal:
            _update(progress_message="正在提交 NYBFW → AI开款工作流...")
            template = comfy_client.load_workflow_template(str(template_path))
            workflow, final_node_id, report_nodes = comfy_client.build_fashion_design_workflow(
                template,
                uploaded_image_name=uploaded_name,
                analysis_prompt_append=str(meta.get("analysis_prompt_append") or ""),
                design_prompt_append=str(meta.get("design_prompt_append") or ""),
            )
        else:
            logger.warning("设计款正式模板不存在 path=%s，退回占位工作流", template_path)
            _update(progress_message="正在提交占位工作流（正式 API 模板未配置）...")
            workflow = comfy_client.build_placeholder_workflow(uploaded_name, _IMAGE_SPECS)

        prompt_id = comfy_client.queue_prompt(comfy_base_url, workflow)
        logger.info(
            "design queued comfy prompt_id=%s task=%s formal=%s template=%s",
            prompt_id,
            task_id,
            use_formal,
            template_path.name,
        )
        _update(progress_message=f"已提交 Comfy 开款工作流（已修复版），生成中 prompt={prompt_id[:8]}…")
        outputs = comfy_client.wait_for_outputs(
            comfy_base_url,
            prompt_id,
            timeout_seconds=config.COMFY_GENERATE_TIMEOUT_SECONDS,
            poll_interval_seconds=config.COMFY_GENERATE_POLL_INTERVAL_SECONDS,
        )
        instance_power_service.touch_usage()

        raw_images = comfy_client.extract_final_images(outputs, final_node_id)
        images = [
            GeneratedImage(
                id=f"{task_id}-{index + 1}",
                label=_IMAGE_SPECS[index][0] if index < len(_IMAGE_SPECS) else f"生成图 {index + 1}",
                url=comfy_client.build_view_url(comfy_base_url, file_info),
            )
            for index, file_info in enumerate(raw_images)
        ]
        if not images:
            raise RuntimeError(f"ComfyUI 未返回任何输出图片 prompt_id={prompt_id}")

        report_docs: list[ReportDoc] = []
        product_attributes: dict = {
            "season": meta.get("season"),
            "category": meta.get("category"),
            "clusters": meta.get("clusters"),
            "analysis_prompt_append": meta.get("analysis_prompt_append"),
            "design_prompt_append": meta.get("design_prompt_append"),
            "source": "scheme3_nybfw_gpu",
            "formal_workflow": use_formal,
        }
        if report_nodes:
            report_texts = comfy_client.extract_report_texts(outputs, report_nodes)
            for node in report_nodes:
                if node["key"] not in report_texts:
                    continue
                content = report_texts[node["key"]]
                report_docs.append(
                    ReportDoc(key=node["key"], title=node["title"], content=content)
                )
                if "规格" in node["title"] or "JSON" in node["title"]:
                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, dict):
                            product_attributes = {**product_attributes, **parsed}
                    except json.JSONDecodeError:
                        pass

        if "design_name_zh" not in product_attributes:
            product_attributes["design_name_zh"] = f"NYBFW企划款-{task_id[:6]}"

        current = result_store.get(task_id)
        source_url = current.source_image_url if current else ""
        _update(
            status=SynthesisStatus.SUCCEEDED,
            progress_message="已完成（GPU · NYBFW AI开款）",
            images=images,
            product_attributes=product_attributes,
            report_docs=report_docs,
            competitor_product_title=str(
                product_attributes.get("design_name_zh") or "设计款"
            ),
            report_markdown=_poc_report(task_id, product_attributes).replace(
                "一期不做当季自动爬取",
                "本次已走 GPU/Comfy 开款链路；一期不做当季自动爬取",
            ),
            source_image_url=source_url,
            intervention_prompt=str(meta.get("design_prompt_append") or ""),
        )
        logger.info(
            "design(gpu) succeeded id=%s images=%s formal=%s",
            task_id,
            len(images),
            use_formal,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("design(gpu) failed id=%s", task_id)
        msg = instance_power_service.friendly_gpu_error(exc)
        if msg == str(exc) and ("Read timed out" in msg or "连接失败" in msg):
            msg = (
                "Cloudsway 视觉分析超时或网络不稳定。"
                "已提高 Comfy 节点读超时并支持重试，请再点一次生成；"
                f"若仍失败请稍后重试。详情：{msg[:400]}"
            )
        _update(
            status=SynthesisStatus.FAILED,
            progress_message="生成失败",
            error_message=msg,
        )

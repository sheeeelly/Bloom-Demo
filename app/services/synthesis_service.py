"""
爆款合成服务。

两条执行路径共用同一套 SynthesisResult 结构：
  - POC 占位路径：`SYNTHESIS_GPU_ENABLED=false`（默认）时，同步复用竞品主图
    构造 8 张「视角」占位结果，用于选品链路演示，不依赖任何外部凭证。
  - GPU 生成路径：`SYNTHESIS_GPU_ENABLED=true` 且已配置仙宫云凭证时，
    异步在线程池中执行「确保实例开机 → 提交 ComfyUI 工作流 → 轮询结果」，
    任务创建后立即返回 status=pending，由前端轮询获取进度。
    GPU 路径下又分两种工作流（取决于 `COMFY_WORKFLOW_TEMPLATE_PATH` 指向的
    文件是否存在），详见 `_run_gpu_synthesis`：
      - 正式工作流：竞品/AZ 商品图片直链注入 `comfy_client.build_product_design_workflow`，
        由 Cloudsway GPT + GP Image 2 云端接口完成真实创意生成
      - 占位工作流：模板文件缺失时的兜底方案，仅验证「开机→上传→生成→下载」链路

结果缓存在内存中，进程重启后清空（与一期 POC 保持一致的持久化策略）。
`list_syntheses` 提供按时间倒序的历史列表（裁剪字段），供「历史生成」页浏览、避免重复发起相同合成。
"""
from __future__ import annotations

import io
import json
import logging
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import config
from app.schemas.synthesis import (
    GeneratedImage,
    ReportDoc,
    SynthesisRequest,
    SynthesisResult,
    SynthesisStatus,
    SynthesisSummary,
    TaskKind,
)
from app.services import comfy_client, instance_power_service, result_store

logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="synthesis-gpu")

# 8 张图：展示标签 + zip 内安全英文文件名 / ComfyUI 输出文件前缀
_IMAGE_SPECS = [
    ("正面全身", "front_full"),
    ("侧面廓形", "side_silhouette"),
    ("背面细节", "back_detail"),
    ("上身特写", "upper_closeup"),
    ("面料纹理", "fabric_texture"),
    ("领型细节", "neckline_detail"),
    ("裙摆动态", "hem_motion"),
    ("搭配场景", "styling_scene"),
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_synthesis(payload: SynthesisRequest) -> SynthesisResult:
    """创建一次合成任务。GPU 路径下立即返回 pending，POC 路径下同步返回完成结果。"""
    task_id = uuid.uuid4().hex[:12]
    now = _now_iso()

    if instance_power_service.gpu_enabled():
        result = SynthesisResult(
            id=task_id,
            kind=TaskKind.HOT_SYNTHESIS,
            status=SynthesisStatus.PENDING,
            mode="gpu",
            progress_message="任务已提交，等待 GPU 实例就绪...",
            az_product_url=payload.az_product_url,
            az_product_image_urls=list(payload.az_product_image_urls or [])[:8],
            competitor_product_id=payload.competitor_product_id,
            competitor_product_title=payload.competitor_product_title,
            competitor_product_image_url=payload.competitor_product_image_url,
            competitor_detail_images=list(payload.competitor_detail_images or [])[:8],
            competitor_source_url=payload.competitor_source_url,
            competitor_source_site=payload.competitor_source_site,
            intervention_selections=dict(payload.intervention_selections),
            intervention_elements=list(payload.intervention_elements or list(payload.intervention_selections.keys())),
            intervention_note=payload.intervention_note,
            intervention_prompt=payload.intervention_prompt,
            created_at=now,
            updated_at=now,
        )
        result_store.put(result)
        logger.info("synthesis(gpu) created id=%s competitor=%s", task_id, payload.competitor_product_id)
        _EXECUTOR.submit(_run_gpu_synthesis, task_id, payload)
        return result

    result = _build_poc_result(task_id, payload, now)
    result_store.put(result)
    logger.info("synthesis(poc) created id=%s competitor=%s", task_id, payload.competitor_product_id)
    return result


def get_synthesis(task_id: str) -> SynthesisResult | None:
    return result_store.get(task_id)


def list_syntheses(
    limit: int = 100,
    *,
    for_planning_pool: bool = False,
    status: str | None = None,
    kind: str | None = None,
) -> list[SynthesisSummary]:
    """历史生成列表（爆款合成 + 设计款），按创建时间倒序。

    for_planning_pool=True 时排除已标记相似款的任务（不进选品企划池）。
    status: pending|running|succeeded|failed|generating（pending+running）
    kind: hot_synthesis|design
    """
    results = result_store.list_all()
    results.sort(key=lambda r: r.created_at, reverse=True)
    summaries: list[SynthesisSummary] = []
    want_status = (status or "").strip().lower()
    want_kind = (kind or "").strip().lower()
    for r in results:
        st = r.status.value if hasattr(r.status, "value") else str(r.status)
        kd = r.kind.value if hasattr(r.kind, "value") else str(r.kind)
        if want_kind and kd != want_kind:
            continue
        if want_status == "generating":
            if st not in {"pending", "running"}:
                continue
        elif want_status and st != want_status:
            continue
        if for_planning_pool and (
            r.marked_as_similar_style or not r.eligible_for_planning_pool
        ):
            continue
        if r.kind == TaskKind.DESIGN:
            title = (
                (r.product_attributes or {}).get("design_name_zh")
                or "设计款"
            )
            thumb = (
                r.panorama_image.url
                if r.panorama_image
                else (r.images[0].url if r.images else r.source_image_url)
            )
        else:
            title = r.competitor_product_title or r.id
            thumb = (
                r.panorama_image.url
                if r.panorama_image
                else (r.images[0].url if r.images else r.competitor_product_image_url)
            )
        summaries.append(
            SynthesisSummary(
                id=r.id,
                kind=r.kind,
                status=r.status,
                mode=r.mode,
                progress_message=r.progress_message,
                error_message=r.error_message,
                az_product_url=r.az_product_url,
                competitor_product_title=r.competitor_product_title,
                competitor_product_image_url=r.competitor_product_image_url,
                competitor_source_site=r.competitor_source_site,
                source_image_url=r.source_image_url,
                thumbnail_url=thumb,
                image_count=len(r.images),
                title=str(title),
                marked_as_similar_style=bool(r.marked_as_similar_style),
                marked_similar_goods_ids=list(r.marked_similar_goods_ids or []),
                eligible_for_planning_pool=bool(r.eligible_for_planning_pool),
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )
        if len(summaries) >= limit:
            break
    return summaries


def sync_similar_style_mark(task_id: str, marked_goods_ids: list[str]) -> None:
    """结果页标记相似款后回写任务：历史红标 + 禁入选品企划池。"""
    from datetime import datetime, timezone

    ids = [str(x).strip() for x in marked_goods_ids if str(x).strip()]
    marked = bool(ids)
    result_store.update(
        task_id,
        marked_as_similar_style=marked,
        marked_similar_goods_ids=ids,
        eligible_for_planning_pool=not marked,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def _report_key_slug(key: str) -> str:
    """“报告2” → “report2”，用于 zip 内文件名（避免中文/特殊字符导致的兼容性问题）。"""
    digits = "".join(ch for ch in key if ch.isdigit())
    return f"report{digits}" if digits else "report"


def build_download_zip(result: SynthesisResult) -> bytes:
    """
    打包生成图 + 分析报告为 zip。图片拉取失败时写入占位说明。

    `report_docs`（工作流「报告N」节点提取的详细文本）额外拆分为 `reports/reportN.md`
    独立文件，与压缩包根目录汇总性的 `report.md` 互为补充，满足下载后按报告分类查看。
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("report.md", result.report_markdown)

        if result.product_attributes:
            zf.writestr(
                "product_attributes.json",
                json.dumps(result.product_attributes, ensure_ascii=False, indent=2) + "\n",
            )

        for doc in result.report_docs:
            filename = f"reports/{_report_key_slug(doc.key)}.md"
            zf.writestr(filename, f"# {doc.key}｜{doc.title}\n\n{doc.content}\n")

        meta_lines = [
            f"synthesis_id: {result.id}",
            f"mode: {result.mode}",
            f"az_product_url: {result.az_product_url}",
            f"competitor_product_id: {result.competitor_product_id}",
            f"competitor_product_title: {result.competitor_product_title}",
            f"created_at: {result.created_at}",
            "",
            "images:",
        ]

        if result.panorama_image:
            filename = "images/00_panorama.jpg"
            meta_lines.append(f"  - {filename} ({result.panorama_image.label}): {result.panorama_image.url}")
            content = _fetch_bytes(result.panorama_image.url)
            if content:
                zf.writestr(filename, content)
            else:
                zf.writestr(
                    "images/00_panorama.txt",
                    f"图片下载失败，原始地址：{result.panorama_image.url}\n",
                )

        for index, image in enumerate(result.images, start=1):
            slug = _IMAGE_SPECS[index - 1][1] if index <= len(_IMAGE_SPECS) else f"image_{index}"
            filename = f"images/{index:02d}_{slug}.jpg"
            meta_lines.append(f"  - {filename} ({image.label}): {image.url}")
            content = _fetch_bytes(image.url)
            if content:
                zf.writestr(filename, content)
            else:
                zf.writestr(
                    f"images/{index:02d}_{slug}.txt",
                    f"图片下载失败，原始地址：{image.url}\n",
                )

        zf.writestr("meta.txt", "\n".join(meta_lines) + "\n")

    return buffer.getvalue()


# ── POC 占位路径 ────────────────────────────────────────────────


def _build_poc_result(task_id: str, payload: SynthesisRequest, now: str) -> SynthesisResult:
    base_image = payload.competitor_product_image_url
    images = [
        GeneratedImage(id=f"{task_id}-{index + 1}", label=label, url=base_image)
        for index, (label, _slug) in enumerate(_IMAGE_SPECS)
    ]
    return SynthesisResult(
        id=task_id,
        kind=TaskKind.HOT_SYNTHESIS,
        status=SynthesisStatus.SUCCEEDED,
        mode="poc",
        progress_message="已完成（POC 占位合成）",
        az_product_url=payload.az_product_url,
        az_product_image_urls=list(payload.az_product_image_urls or [])[:8],
        competitor_product_id=payload.competitor_product_id,
        competitor_product_title=payload.competitor_product_title,
        competitor_product_image_url=payload.competitor_product_image_url,
        competitor_detail_images=list(payload.competitor_detail_images or [])[:8],
        competitor_source_url=payload.competitor_source_url,
        competitor_source_site=payload.competitor_source_site,
        intervention_selections=dict(payload.intervention_selections),
        intervention_elements=list(payload.intervention_elements or list(payload.intervention_selections.keys())),
        intervention_note=payload.intervention_note,
        intervention_prompt=payload.intervention_prompt,
        images=images,
        report_markdown=_build_report(payload, mode="poc"),
        created_at=now,
        updated_at=now,
    )


# ── GPU 生成路径（仙宫云 + ComfyUI）──────────────────────────────


def _resolve_competitor_image_urls(payload: SynthesisRequest) -> list[str]:
    """竞品参考图：优先使用详情页多图（最多 8 张，工作流原生上限），为空时退回单张主图。"""
    urls = [u.strip() for u in payload.competitor_detail_images if u and u.strip()]
    if not urls:
        urls = [payload.competitor_product_image_url]
    return urls[:8]


def _resolve_product_image_urls(payload: SynthesisRequest) -> list[str]:
    """AZ 商品参考图：工作流本身选填，直接透传前端已采集的直链（最多 8 张）。"""
    return [u.strip() for u in payload.az_product_image_urls if u and u.strip()][:8]


def _run_gpu_synthesis(task_id: str, payload: SynthesisRequest) -> None:
    def _update(**changes: object) -> None:
        result_store.update(task_id, **changes, updated_at=_now_iso())

    try:
        _update(status=SynthesisStatus.RUNNING, progress_message="正在检查 GPU 实例状态...")
        comfy_base_url = instance_power_service.ensure_instance_ready()
        instance_power_service.touch_usage()

        template_path = Path(config.COMFY_WORKFLOW_TEMPLATE_PATH)
        use_formal_workflow = template_path.is_file()
        final_node_id: str | None = None
        panorama_node_id: str | None = None
        report_nodes: list[dict[str, str]] = []

        if use_formal_workflow:
            _update(progress_message="正在提交正式合成工作流（竞品＋AZ 商品直链）...")
            template = comfy_client.load_workflow_template(str(template_path))
            workflow, final_node_id, panorama_node_id, report_nodes = comfy_client.build_product_design_workflow(
                template,
                competitor_image_urls=_resolve_competitor_image_urls(payload),
                product_image_urls=_resolve_product_image_urls(payload),
                intervention_prompt=payload.intervention_prompt.strip(),
            )
        else:
            logger.warning("正式工作流模板不存在 path=%s，退回占位工作流（仅验证基础设施链路）", template_path)
            _update(progress_message="正在上传竞品图到 ComfyUI（占位工作流）...")
            image_bytes = _fetch_bytes(payload.competitor_product_image_url)
            if not image_bytes:
                raise RuntimeError(f"竞品主图下载失败，无法上传：{payload.competitor_product_image_url}")
            uploaded_name = comfy_client.upload_image_bytes(comfy_base_url, "competitor.jpg", image_bytes)
            workflow = comfy_client.build_placeholder_workflow(uploaded_name, _IMAGE_SPECS)

        prompt_id = comfy_client.queue_prompt(comfy_base_url, workflow)

        _update(progress_message="GPU 正在生成图片，请稍候（正式工作流耗时可能达十余分钟）...")
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

        panorama_image: GeneratedImage | None = None
        raw_panorama = comfy_client.extract_node_images(outputs, panorama_node_id)
        if raw_panorama:
            panorama_image = GeneratedImage(
                id=f"{task_id}-panorama",
                label="全景图",
                url=comfy_client.build_view_url(comfy_base_url, raw_panorama[0]),
            )

        report_docs: list[ReportDoc] = []
        if report_nodes:
            report_texts = comfy_client.extract_report_texts(outputs, report_nodes)
            report_docs = [
                ReportDoc(key=node["key"], title=node["title"], content=report_texts[node["key"]])
                for node in report_nodes
                if node["key"] in report_texts
            ]

        _update(
            status=SynthesisStatus.SUCCEEDED,
            progress_message="已完成（GPU 实时生成）",
            images=images,
            panorama_image=panorama_image,
            report_docs=report_docs,
            report_markdown=_build_report(
                payload,
                mode="gpu",
                formal_workflow=use_formal_workflow,
                report_doc_count=len(report_docs),
            ),
        )
        logger.info(
            "synthesis(gpu) succeeded id=%s images=%s formal_workflow=%s panorama=%s reports=%s",
            task_id,
            len(images),
            use_formal_workflow,
            bool(panorama_image),
            len(report_docs),
        )
    except Exception as exc:  # noqa: BLE001 - 需要将任意失败原因透传给前端
        logger.exception("synthesis(gpu) failed id=%s", task_id)
        _update(
            status=SynthesisStatus.FAILED,
            progress_message="生成失败",
            error_message=instance_power_service.friendly_gpu_error(exc),
        )


def _build_report(
    payload: SynthesisRequest,
    *,
    mode: str,
    formal_workflow: bool = False,
    report_doc_count: int = 0,
) -> str:
    """
    生成压缩包 `report.md` 与可视化页面「分析报告」概要区展示的固定文案。

    真正来自工作流的详细分析（设计简报、竞品/商品卖点分析、创意候选方案等）由
    `report_doc_count` 对应的 `ReportDoc` 列表承载，在可视化页面「详细报告」分区
    单独展示、压缩包内拆分为 `reports/reportN.md`；此处仅根据是否提取到详细报告
    调整「下一步」提示文案，不重复内嵌详细内容，避免与独立报告文件冗余。
    """
    site = payload.competitor_source_site or "竞品站点"
    if mode == "gpu":
        source_note = (
            "本次合成已接入仙宫云 GPU 实例 + ComfyUI 正式「V9 竞品+商品直链」创意工作流"
            "（Cloudsway GPT + GP Image 2 云端生成）。"
            if formal_workflow
            else "本次合成已接入仙宫云 GPU 实例 + ComfyUI 实时生成链路（占位工作流，正式工作流模板未配置）。"
        )
    else:
        source_note = "本次合成为 POC 占位演示，生成图暂复用竞品主图，用于验证前后端链路。"

    if report_doc_count:
        next_step_note = (
            f"- 已从工作流提取 {report_doc_count} 份详细报告（设计简报、竞品/商品卖点分析、创意候选方案等），"
            "详见下方「详细报告」分区，下载压缩包 `reports/` 目录含对应 md 文件"
        )
    elif formal_workflow:
        next_step_note = "- 正式工作流本次未返回可解析的报告节点文本，暂无法展示详细报告，请检查模板报告节点是否被改动"
    else:
        next_step_note = "- 替换正式 ComfyUI 创意工作流后，本报告将补充色彩、面料、廓形等结构化评分"

    elements = ", ".join(
        f"{k}={v}" for k, v in (payload.intervention_selections or {}).items()
    ) or (", ".join(payload.intervention_elements) if payload.intervention_elements else "（未选）")
    intervention_block = f"""
## 人为干预（软约束）
- 选定属性：{elements}
- 自然语言简述：{payload.intervention_note.strip() or "（无）"}
- 完整 Prompt（真正入参）：
```
{payload.intervention_prompt.strip() or "（未填写）"}
```
""".rstrip()

    return f"""# 爆款合成分析报告

## 合成说明
本次合成基于「竞品爆款 + AZ 爆款」卖点结合，用于智能选品 MVP 的可视化演示。
{source_note}

## 输入信息
- AZ 爆款商品 URL：{payload.az_product_url}
- 竞品站点：{site}
- 竞品爆款：{payload.competitor_product_title}
- 竞品原页：{payload.competitor_source_url or "—"}
{intervention_block}

## 卖点结合建议
- 保留 AZ 爆款在版型、穿着场景与品牌调性上的优势卖点
- 吸收竞品爆款在视觉冲击、细节设计与流行元素上的差异化卖点
- 输出 8 个视角图，覆盖全身、细节与场景，便于选品评审与落地沟通

## 下一步
{next_step_note}
- 下载压缩包可获取 8 张图与本报告，便于同步给设计 / 买手团队
"""


def _fetch_bytes(url: str) -> bytes | None:
    # 优先读历史落盘 / 本地静态，避免 Comfy 链接过期后 zip 下载失败
    from app.services import result_store

    local = result_store.fetch_asset_bytes(url, timeout=30)
    if local is not None:
        return local
    try:
        req = Request(url, headers={"User-Agent": "az-bloom-poc/0.1"})
        with urlopen(req, timeout=12) as resp:
            return resp.read()
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        logger.warning("fetch image failed url=%s err=%s", url, exc)
        return None

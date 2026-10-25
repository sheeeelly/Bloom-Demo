"""
ComfyUI HTTP 客户端 + 两套工作流构造（正式 / 占位）。

标准 ComfyUI HTTP API：`/upload/image`、`/prompt`、`/history/{id}`、`/view`、`/queue`，
调用方式与 aigc-retouch-worker 项目一致（无官方 SDK，直连 requests）。

工作流选择策略（见 synthesis_service._run_gpu_synthesis）：
  - 正式工作流（`build_product_design_workflow`）：加载 `COMFY_WORKFLOW_TEMPLATE_PATH`
    （默认 `workflows/product_design_v13.json`，V13 UI 导出的 API 版：
    `V13版本-指定模型仅高清_严格锁定原构图_8并发_原比例2X_新增设计点可视化选择`）。
    注入竞品/商品图片直链后提交；规划/生图由 Cloudsway + ProductDesignV13* 等
    自定义节点驱动，末端 LayerUtility 定尺 1140×1578。
  - 占位工作流（`build_placeholder_workflow`）：模板文件缺失时的退回方案，仅用
    ComfyUI 核心节点（LoadImage / ImageScale / SaveImage）验证基础设施链路，
    不依赖任何自定义节点，用于在正式模板就绪前打通全链路。
"""
from __future__ import annotations

import copy
import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)


class ComfyError(RuntimeError):
    """ComfyUI HTTP 调用失败或工作流执行失败。"""


def check_ready(base_url: str, *, timeout_seconds: float = 10.0) -> bool:
    """探测 ComfyUI `/queue` 是否可访问。"""
    try:
        resp = requests.get(f"{base_url}/queue", timeout=timeout_seconds)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.debug("ComfyUI 未就绪 base_url=%s err=%s", base_url, exc)
        return False


def wait_ready(base_url: str, *, timeout_seconds: float, poll_interval_seconds: float) -> None:
    """轮询等待 ComfyUI 就绪，超时抛出 ComfyError。"""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if check_ready(base_url, timeout_seconds=min(10.0, poll_interval_seconds * 2)):
            return
        time.sleep(poll_interval_seconds)
    raise ComfyError(f"ComfyUI 服务等待超时（{timeout_seconds}s）：{base_url}")


def upload_image_bytes(base_url: str, filename: str, content: bytes, *, timeout_seconds: float = 45.0) -> str:
    """上传图片到 ComfyUI input 目录，返回服务端保存的文件名。"""
    # 唯一文件名避免 ComfyUI 按文件名缓存导致复用旧图
    upload_name = f"{uuid.uuid4().hex}-{filename}"
    try:
        resp = requests.post(
            f"{base_url}/upload/image",
            files={"image": (upload_name, content, "application/octet-stream")},
            timeout=timeout_seconds,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise ComfyError(f"上传图片到 ComfyUI 失败：{exc}") from exc
    data = resp.json()
    name = data.get("name")
    if not name:
        raise ComfyError(f"ComfyUI 上传响应缺少 name 字段：{data}")
    return str(name)


def queue_prompt(base_url: str, workflow: dict[str, Any], *, timeout_seconds: float = 60.0) -> str:
    """提交工作流到 ComfyUI 排队，返回 prompt_id。"""
    client_id = str(uuid.uuid4())
    try:
        resp = requests.post(
            f"{base_url}/prompt",
            json={"prompt": workflow, "client_id": client_id},
            timeout=timeout_seconds,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        detail = getattr(exc.response, "text", "") if getattr(exc, "response", None) else ""
        raise ComfyError(f"提交 ComfyUI 工作流失败：{exc} {detail[:500]}") from exc
    data = resp.json()
    if data.get("node_errors"):
        raise ComfyError(f"ComfyUI 工作流校验失败：{data['node_errors']}")
    prompt_id = data.get("prompt_id")
    if not prompt_id:
        raise ComfyError(f"ComfyUI 提交响应缺少 prompt_id：{data}")
    return str(prompt_id)


def wait_for_outputs(
    base_url: str,
    prompt_id: str,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> dict[str, Any]:
    """轮询 `/history/{prompt_id}`，完成后返回 outputs；执行失败则抛出 ComfyError。"""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            resp = requests.get(f"{base_url}/history/{prompt_id}", timeout=30)
            resp.raise_for_status()
            history = resp.json()
        except requests.RequestException as exc:
            logger.warning("轮询 ComfyUI history 失败，继续重试 prompt_id=%s err=%s", prompt_id, exc)
            time.sleep(poll_interval_seconds)
            continue

        entry = history.get(prompt_id)
        if entry:
            status = entry.get("status") or {}
            if status.get("status_str") == "error":
                raise ComfyError(f"ComfyUI 工作流执行失败 prompt_id={prompt_id}：{status.get('messages')}")
            outputs = entry.get("outputs")
            if outputs:
                return outputs
        time.sleep(poll_interval_seconds)
    raise ComfyError(f"ComfyUI 生成超时（{timeout_seconds}s）prompt_id={prompt_id}")


def build_view_url(base_url: str, file_info: dict[str, Any]) -> str:
    """
    按 ComfyUI `/view` 约定拼接可直接访问的图片 URL（无需经本服务转发）。

    该 URL 既用于前端直接展示，也被 synthesis_service 的通用 `_fetch_bytes()`
    复用来下载字节打包 ZIP，因此本模块不再单独提供下载函数。
    """
    filename = file_info.get("filename", "")
    subfolder = file_info.get("subfolder", "") or ""
    type_ = file_info.get("type", "output") or "output"
    return f"{base_url}/view?filename={filename}&subfolder={subfolder}&type={type_}"


def extract_images(outputs: dict[str, Any]) -> list[dict[str, Any]]:
    """从 history outputs 中提取所有图片输出（按节点顺序），保留 SaveImage 元数据。"""
    images: list[dict[str, Any]] = []
    for node_output in outputs.values():
        for image in node_output.get("images") or []:
            images.append(image)
    return images


def extract_final_images(outputs: dict[str, Any], final_node_id: str | None) -> list[dict[str, Any]]:
    """
    优先只取 `final_node_id` 对应节点的图片。

    正式工作流里有多个调试用 PreviewImage/Comparer 节点（竞品多图总览、规划选图、
    高清精修中间态等），若不限定节点会把调试图和最终 8 张成品图混在一起返回；
    `final_node_id` 未知（如占位工作流，或正式模板结构被改动导致定位失败）时
    才退回扫描全部节点。
    """
    if final_node_id and final_node_id in outputs:
        return list(outputs[final_node_id].get("images") or [])
    return extract_images(outputs)


def extract_node_images(outputs: dict[str, Any], node_id: str | None) -> list[dict[str, Any]]:
    """取指定节点的图片输出（不存在则返回空列表），用于全景母版等单点定位场景。"""
    if not node_id or node_id not in outputs:
        return []
    return list(outputs[node_id].get("images") or [])


# 正式模板中「报告N｜标题」PreviewAny 节点标题格式，如 "报告2｜最终选中创意方案中文设计简报"
_REPORT_TITLE_PATTERN = re.compile(r"^(报告\d+)｜(.+)$")


def find_report_nodes(workflow: dict[str, Any]) -> list[dict[str, str]]:
    """
    定位正式工作流模板中所有「报告N｜标题」的 `PreviewAny` 节点。

    这些节点由 Cloudsway 自定义节点（规划 / 采集 / 切图 / 高清精修等）的调试输出口接出，
    承载 GPT 侧生成的中文设计简报、竞品与商品卖点分析、创意候选方案等详细文本——
    此前一直被当作纯调试节点忽略，现在作为「分析报告」正式内容的数据源之一。

    @return 按报告序号升序排列的 [{"node_id", "key", "title"}, ...]；
            key 形如 "报告2"，title 为标题中「｜」后的说明文字。
    """
    reports: list[dict[str, str]] = []
    for node_id, node in workflow.items():
        if node.get("class_type") != "PreviewAny":
            continue
        title = (node.get("_meta", {}) or {}).get("title") or ""
        match = _REPORT_TITLE_PATTERN.match(title)
        if not match:
            continue
        reports.append({"node_id": node_id, "key": match.group(1), "title": match.group(2)})

    def _report_number(item: dict[str, str]) -> int:
        digits = re.search(r"\d+", item["key"])
        return int(digits.group()) if digits else 0

    reports.sort(key=_report_number)
    return reports


def extract_report_texts(
    outputs: dict[str, Any], report_nodes: list[dict[str, str]]
) -> dict[str, str]:
    """
    从 `/history` outputs 中提取 `find_report_nodes` 定位到的报告节点文本内容。

    `PreviewAny`（ComfyUI-Custom-Scripts）执行后写入 `{"text": [...]}`（通常仅 1 项，
    多项时按行拼接）；节点缺失、字段为空或内容为空串时跳过该报告，不影响其余报告与
    最终图片的正常展示（对应 `ReportDoc` 允许部分缺失）。
    """
    texts: dict[str, str] = {}
    for report in report_nodes:
        node_output = outputs.get(report["node_id"])
        if not node_output:
            continue
        raw = node_output.get("text")
        if not raw:
            continue
        value = "\n".join(str(item) for item in raw) if isinstance(raw, (list, tuple)) else str(raw)
        value = value.strip()
        if value:
            texts[report["key"]] = value
    return texts


def load_workflow_template(path: str) -> dict[str, Any]:
    """加载正式 ComfyUI 工作流模板（ComfyUI 网页端「导出（API）」得到的 JSON）。"""
    file_path = Path(path)
    if not file_path.is_file():
        raise ComfyError(f"工作流模板文件不存在：{path}")
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _find_node_id(workflow: dict[str, Any], class_type: str, *, title_contains: str = "") -> str | None:
    """
    按 class_type（+ 可选标题关键字）定位节点 id。

    正式模板会在 ComfyUI 网页端持续编辑，节点 id 可能因此重新编号，
    用 class_type（必要时叠加标题关键字区分同类型的多个节点）匹配
    比硬编码数字 id 更稳妥。
    """
    for node_id, node in workflow.items():
        if node.get("class_type") != class_type:
            continue
        if title_contains and title_contains not in (node.get("_meta", {}).get("title") or ""):
            continue
        return node_id
    return None


# 最终定尺裁剪节点的 class_type，按模板版本从新到旧依次尝试：
#   - V9：不再有专用裁剪节点，改用通用图层工具节点 "LayerUtility: ImageMaskScaleAsV2"
#     居中裁剪定尺 1140×1578
#   - V0.8：专用节点 "ProductDesignV08GPHDCenterCrop"（保留兼容，防止个别环境仍用旧模板）
_FINAL_CROP_CLASS_TYPES = (
    "LayerUtility: ImageMaskScaleAsV2",
    "ProductDesignV08GPHDCenterCrop",
)


def _cloudsway_settings() -> dict[str, str]:
    try:
        import config
    except Exception:  # noqa: BLE001
        return {}
    return {
        "api_key": str(getattr(config, "CLOUDSWAY_API_KEY", "") or "").strip(),
        "gpt_base_url": str(getattr(config, "CLOUDSWAY_GPT_BASE_URL", "") or "").strip(),
        "gpt_model_id": str(getattr(config, "CLOUDSWAY_GPT_MODEL_ID", "") or "").strip(),
        "image_base_url": str(getattr(config, "CLOUDSWAY_IMAGE_BASE_URL", "") or "").strip(),
        "image_model_id": str(getattr(config, "CLOUDSWAY_IMAGE_MODEL_ID", "") or "").strip(),
    }


def inject_cloudsway_api_key(workflow: dict[str, Any]) -> int:
    """兼容旧名：注入 Cloudsway 密钥 + GPT/Image 路由。"""
    return inject_cloudsway_credentials(workflow)


def inject_cloudsway_credentials(workflow: dict[str, Any]) -> int:
    """
    从环境变量注入 Cloudsway 凭证与 GPT-5.5 / GP Image 路由。
    - api_key：仅填空
    - gpt_base_url / gpt_model_id / image_*：配置非空时覆盖节点值
    """
    cfg = _cloudsway_settings()
    key = cfg.get("api_key") or ""
    if not key:
        logger.warning("CLOUDSWAY_API_KEY 未配置：Cloudsway 节点若依赖节点内 Key 将失败")

    touched = 0
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue

        if "api_key" in inputs and key and not str(inputs.get("api_key") or "").strip():
            inputs["api_key"] = key
            touched += 1

        if "gpt_base_url" in inputs and cfg.get("gpt_base_url"):
            if inputs.get("gpt_base_url") != cfg["gpt_base_url"]:
                inputs["gpt_base_url"] = cfg["gpt_base_url"]
                touched += 1
        if "gpt_model_id" in inputs and cfg.get("gpt_model_id"):
            if inputs.get("gpt_model_id") != cfg["gpt_model_id"]:
                inputs["gpt_model_id"] = cfg["gpt_model_id"]
                touched += 1

        # PersonReplace 用 image_base_url / image_model_id；GP Image Edit 用 base_url / model
        if "image_base_url" in inputs and cfg.get("image_base_url"):
            if inputs.get("image_base_url") != cfg["image_base_url"]:
                inputs["image_base_url"] = cfg["image_base_url"]
                touched += 1
        if "image_model_id" in inputs and cfg.get("image_model_id"):
            if inputs.get("image_model_id") != cfg["image_model_id"]:
                inputs["image_model_id"] = cfg["image_model_id"]
                touched += 1

        class_type = str(node.get("class_type") or "")
        if class_type == "CloudswayGPImageEdit":
            if "base_url" in inputs and cfg.get("image_base_url"):
                if inputs.get("base_url") != cfg["image_base_url"]:
                    inputs["base_url"] = cfg["image_base_url"]
                    touched += 1
            if "model" in inputs and cfg.get("image_model_id"):
                if inputs.get("model") != cfg["image_model_id"]:
                    inputs["model"] = cfg["image_model_id"]
                    touched += 1
            # gpt-image-2 / MaaS_GP_image_2 不接受 input_fidelity，须 omit（节点不发送该字段）
            model_blob = f"{inputs.get('model') or ''} {inputs.get('api_model') or ''} {inputs.get('image_model_id') or ''} {inputs.get('image_api_model') or ''}".lower()
            if ("image_2" in model_blob or "image-2" in model_blob) and "input_fidelity" in inputs:
                if inputs.get("input_fidelity") != "omit":
                    inputs["input_fidelity"] = "omit"
                    touched += 1

        # 开款八视图节点：模型在 api_config 里，本节点仍可能带 input_fidelity=auto
        if class_type == "CloudswayFashionEightViewGPTImage2" and "input_fidelity" in inputs:
            if inputs.get("input_fidelity") != "omit":
                inputs["input_fidelity"] = "omit"
                touched += 1

    if touched:
        logger.info("已注入 Cloudsway 凭证/路由字段 %s 处", touched)
    return touched


def build_product_design_workflow(
    template: dict[str, Any],
    *,
    competitor_image_urls: list[str],
    product_image_urls: list[str],
    intervention_prompt: str = "",
) -> tuple[dict[str, Any], str | None, str | None, list[dict[str, str]]]:
    """
    基于正式工作流模板（API 格式），注入本次请求的图片直链。

    模板节点约定（`workflows/product_design_v13.json` = V13 工作流 API 版；
    图片直链由节点自行下载，无需先 upload）：
      - "CR Text"（标题含"竞品图片"）：竞品图片直链，每行 1 张，1-8 张，必填
      - "CR Text"（标题含"商品图片"）：AZ 商品图片直链，每行 1 张，1-8 张，选填
      - 可选人为干预：若模板存在标题含「人工干预」或「规划 GPT User Prompt」的 CR Text，
        则写入/追加 intervention_prompt（V12「放开 prompt」工作流可用；V9 无此节点时跳过）
      - "LayerUtility: ImageMaskScaleAsV2"（V9 末端定尺裁剪节点）下游的
        SaveImage/PreviewImage：最终 8 张成品图。
      - "SaveImage"（标题含"全景母版"）：拆分前的原始 4×2 全景整图。
      - "PreviewAny"（标题形如"报告N｜xxx"）：见 `find_report_nodes`。

    @return (可提交的 workflow 字典, 最终输出节点 id, 全景母版节点 id, 报告节点列表)
    """
    workflow = copy.deepcopy(template)

    competitor_node_id = _find_node_id(workflow, "CR Text", title_contains="竞品图片")
    if not competitor_node_id:
        raise ComfyError("工作流模板缺少竞品图片 URL 输入节点（CR Text，标题含“竞品图片”），请检查模板是否被改动")
    workflow[competitor_node_id]["inputs"]["text"] = "\n".join(competitor_image_urls)

    product_node_id = _find_node_id(workflow, "CR Text", title_contains="商品图片")
    if product_node_id:
        # 该项工作流内为选填：无直链时清空，避免误用模板里遗留的示例图片
        workflow[product_node_id]["inputs"]["text"] = "\n".join(product_image_urls)

    if intervention_prompt.strip():
        _inject_intervention_prompt(workflow, intervention_prompt.strip())

    final_node_id = _find_final_output_node_id(workflow)
    if final_node_id:
        workflow[final_node_id]["class_type"] = "SaveImage"
        workflow[final_node_id]["inputs"]["filename_prefix"] = "az_bloom_final"
    else:
        logger.warning("未在模板中定位到最终 8 视图输出节点，生成结果将退回扫描全部输出（可能混入调试/报告预览图）")

    panorama_node_id = _find_node_id(workflow, "SaveImage", title_contains="全景母版")
    if not panorama_node_id:
        logger.warning("未在模板中定位到全景母版节点，可视化页面将不展示首屏缩略图")

    report_nodes = find_report_nodes(workflow)
    if not report_nodes:
        logger.warning("未在模板中定位到任何「报告N｜标题」节点，分析报告将仅保留固定模板文案")

    inject_cloudsway_api_key(workflow)
    return workflow, final_node_id, panorama_node_id, report_nodes


def _inject_intervention_prompt(workflow: dict[str, Any], prompt: str) -> None:
    """
    将人为干预 Prompt 写入可编辑文本节点。

    匹配优先级：
      1. 标题含「人工干预」
      2. 标题含「规划 GPT User Prompt」
    找不到则仅打日志（V9 模板无对应节点时属预期）。
    """
    node_id = _find_node_id(workflow, "CR Text", title_contains="人工干预")
    if not node_id:
        node_id = _find_node_id(workflow, "CR Text", title_contains="规划 GPT User Prompt")
    if not node_id:
        logger.info("工作流模板无人工干预/User Prompt 文本节点，干预 Prompt 仅写入业务报告，不注入 Comfy")
        return

    existing = str(workflow[node_id].get("inputs", {}).get("text") or "").strip()
    if existing:
        workflow[node_id]["inputs"]["text"] = f"{existing}\n\n{prompt}"
    else:
        workflow[node_id]["inputs"]["text"] = prompt
    logger.info("已向节点 %s 注入人为干预 Prompt（%s 字符）", node_id, len(prompt))


def build_fashion_design_workflow(
    template: dict[str, Any],
    *,
    uploaded_image_name: str,
    analysis_prompt_append: str = "",
    design_prompt_append: str = "",
) -> tuple[dict[str, Any], str | None, list[dict[str, str]]]:
    """
    基于「AI 开款 / 设计款」正式工作流 API 模板，注入已上传的参考图文件名。

    约定：
      - 至少一个 `LoadImage`（优先标题含「参考图01」）写入 `uploaded_image_name`
      - 可选追加 `analysis_prompt` / `design_prompt`（方案三 NYBFW 干预）
      - 最终 `SaveImage`（标题含「保存」或「多视图」）作为成品输出节点
      - `PreviewAny` 报告节点：标题含「面料」「设计规格」「分析」等，映射为报告 docs

    模板需为 ComfyUI「导出（API）」格式；UI 格式 JSON 不可直接 `/prompt`。
    """
    workflow = copy.deepcopy(template)

    load_id = _find_node_id(workflow, "LoadImage", title_contains="参考图01")
    if not load_id:
        load_id = _find_node_id(workflow, "LoadImage")
    if not load_id:
        raise ComfyError("设计款工作流模板缺少 LoadImage 节点")
    workflow[load_id]["inputs"]["image"] = uploaded_image_name

    if analysis_prompt_append.strip():
        for node_id, node in workflow.items():
            if node.get("class_type") != "CloudswayFashionMaterialCraftAnalyzerGPT55":
                continue
            base = str(node.get("inputs", {}).get("analysis_prompt") or "").rstrip()
            workflow[node_id].setdefault("inputs", {})["analysis_prompt"] = (
                f"{base}\n\n{analysis_prompt_append.strip()}" if base else analysis_prompt_append.strip()
            )
            break

    if design_prompt_append.strip():
        for node_id, node in workflow.items():
            if node.get("class_type") != "CloudswayFashionBestsellerDesignerGPT55":
                continue
            base = str(node.get("inputs", {}).get("design_prompt") or "").rstrip()
            workflow[node_id].setdefault("inputs", {})["design_prompt"] = (
                f"{base}\n\n{design_prompt_append.strip()}" if base else design_prompt_append.strip()
            )
            break

    # 季节灵感 / 开款：多模态 GPT 调用易超过默认读超时；强制拉高节点 timeout，并缩小参考边长降 payload
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if class_type in {
            "CloudswayFashionMaterialCraftAnalyzerGPT55",
            "CloudswayFashionBestsellerDesignerGPT55",
        }:
            try:
                current = int(inputs.get("timeout") or 0)
            except (TypeError, ValueError):
                current = 0
            if current < 600:
                inputs["timeout"] = 600
            try:
                side = int(inputs.get("reference_max_side") or 0)
            except (TypeError, ValueError):
                side = 0
            if side <= 0 or side > 1024:
                inputs["reference_max_side"] = 1024
        if class_type == "CloudswayFashionEightViewGPTImage2":
            try:
                current = int(inputs.get("timeout") or 0)
            except (TypeError, ValueError):
                current = 0
            if current < 900:
                inputs["timeout"] = 900
            # gpt-image-2 / MaaS_GP_image_2 不支持 input_fidelity；节点若按 image_api_model=gpt-image-1 判断会误发
            if inputs.get("input_fidelity") != "omit":
                inputs["input_fidelity"] = "omit"

    final_node_id = _find_node_id(workflow, "SaveImage", title_contains="多视图")
    if not final_node_id:
        final_node_id = _find_node_id(workflow, "SaveImage", title_contains="保存")
    if not final_node_id:
        final_node_id = _find_node_id(workflow, "SaveImage")
    if final_node_id:
        workflow[final_node_id]["inputs"]["filename_prefix"] = "az_bloom_design"

    report_nodes: list[dict[str, str]] = []
    for node_id, node in workflow.items():
        if node.get("class_type") != "PreviewAny":
            continue
        title = (node.get("_meta", {}) or {}).get("title") or ""
        if any(key in title for key in ("面料", "分析", "设计规格", "身份锁定", "报告")):
            report_nodes.append({"node_id": node_id, "key": f"报告{len(report_nodes) + 1}", "title": title})

    inject_cloudsway_api_key(workflow)
    return workflow, final_node_id, report_nodes


def _find_final_output_node_id(workflow: dict[str, Any]) -> str | None:
    """定位最终 8 视图裁剪结果的输出节点（SaveImage 优先，否则退回 PreviewImage）。"""
    crop_node_id = next(
        (nid for ct in _FINAL_CROP_CLASS_TYPES if (nid := _find_node_id(workflow, ct))),
        None,
    )
    if not crop_node_id:
        return None

    candidates = [
        node_id
        for node_id, node in workflow.items()
        if node.get("class_type") in ("SaveImage", "PreviewImage")
        and node.get("inputs", {}).get("images") == [crop_node_id, 0]
    ]
    if not candidates:
        return None
    return next((nid for nid in candidates if workflow[nid]["class_type"] == "SaveImage"), candidates[0])


def build_placeholder_workflow(input_image_name: str, view_specs: list[tuple[str, str]]) -> dict[str, Any]:
    """
    构造占位工作流：1 张 LoadImage 输入，分流出多个 ImageScale + SaveImage 分支。

    @param input_image_name 已上传到 ComfyUI 的服务端文件名
    @param view_specs [(展示标签, 文件名前缀slug), ...]，每个 spec 产出 1 张输出图
    @return ComfyUI `/prompt` 所需的 workflow（API 格式）字典

    仅依赖 ComfyUI 核心内置节点，不依赖任何 checkpoint / 自定义节点，
    可在任意标准 ComfyUI 实例上直接跑通，用于验证基础设施链路。
    """
    workflow: dict[str, Any] = {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": input_image_name},
        }
    }

    # 用不同缩放尺寸让 8 张占位输出图产生可观察差异，便于确认链路是逐张真实生成
    base_size = 1024
    for index, (_label, slug) in enumerate(view_specs):
        scale_node_id = f"scale_{index}"
        save_node_id = f"save_{index}"
        target_size = base_size - (index * 24)
        workflow[scale_node_id] = {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["1", 0],
                "upscale_method": "lanczos",
                "width": target_size,
                "height": target_size,
                "crop": "center",
            },
        }
        workflow[save_node_id] = {
            "class_type": "SaveImage",
            "inputs": {
                "images": [scale_node_id, 0],
                "filename_prefix": f"az_bloom_{slug}",
            },
        }
    return workflow

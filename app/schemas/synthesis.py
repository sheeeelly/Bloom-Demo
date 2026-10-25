"""
生成任务相关数据模型（爆款合成 + 设计款共用响应结构）。

支持两种执行路径，二者共用同一份请求/响应结构，前端无需感知差异：
  - POC 占位路径（SYNTHESIS_GPU_ENABLED=false 或未配置仙宫云凭证）：
    同步返回，复用输入图构造 8 张占位图。
  - GPU 生成路径（SYNTHESIS_GPU_ENABLED=true）：
    异步任务，POST 立即返回 status=pending，前端轮询
    `GET /api/synthesis/{id}` 直至 status 变为 succeeded / failed。
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SynthesisStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TaskKind(str, Enum):
    """历史生成需要区分任务类型。"""

    HOT_SYNTHESIS = "hot_synthesis"  # 爆款合成
    DESIGN = "design"  # 设计款


# 爆款合成页「人为干预」设计维（下拉选项见 dress_attr_catalog）
INTERVENTION_ELEMENT_OPTIONS: list[dict[str, str]] = [
    {"key": "silhouette", "label": "廓形 / 版型"},
    {"key": "neckline_shoulder", "label": "领口 / 肩型"},
    {"key": "sleeve", "label": "袖型"},
    {"key": "waist", "label": "腰线 / 腰臀"},
    {"key": "skirt_hem", "label": "裙摆 / 下摆"},
    {"key": "length", "label": "衣长 / 裙长"},
    {"key": "fabric", "label": "面料 / 质感"},
    {"key": "color_print", "label": "色彩 / 印花"},
]


class SynthesisRequest(BaseModel):
    az_product_url: str = Field(..., description="AZ 爆款商品详情页 URL（必填）")
    az_product_image_urls: list[str] = Field(
        default_factory=list,
        description=(
            "AZ 商品图片直链（选填，最多 8 张）。GPU 生成模式下作为设计参考图传入正式工作流；"
            "工作流对该项本身即为选填，留空仍可正常生成，仅缺少 AZ 商品作为参考。"
        ),
    )
    competitor_product_id: str = Field(..., description="选中的竞品商品 ID（单选）")
    competitor_product_title: str = Field(..., description="竞品商品标题")
    competitor_product_image_url: str = Field(..., description="竞品商品主图")
    competitor_detail_images: list[str] = Field(
        default_factory=list,
        description="竞品商品详情页多图（选填，最多 8 张）。GPU 生成模式下优先于单张主图使用，为空时退回主图。",
    )
    competitor_source_url: str = Field(default="", description="竞品商品原页链接")
    competitor_source_site: str = Field(default="", description="竞品站点名称")

    # 人为干预（软约束）：下拉选定属性值 + 自然语言 + 一键生成的完整 Prompt（真正入参）
    intervention_selections: dict[str, str] = Field(
        default_factory=dict,
        description="各设计维下拉选中的具体属性值，如 {\"silhouette\": \"A-Line\", \"skirt_hem\": \"Layered Hem\"}",
    )
    intervention_elements: list[str] = Field(
        default_factory=list,
        description="已选择的设计维 key 列表（可由 selections 推导，兼容旧字段）",
    )
    intervention_note: str = Field(default="", description="自然语言简单描述")
    intervention_prompt: str = Field(
        default="",
        description="完整干预 Prompt（可选）；有则作为合成入参注入工作流，无则按默认合成",
    )


class BuildPromptRequest(BaseModel):
    selections: dict[str, str] = Field(
        default_factory=dict,
        description="设计维 → 属性值，如 silhouette=A-Line",
    )
    elements: list[str] = Field(
        default_factory=list,
        description="兼容旧版：仅传维 key（无具体值时）",
    )
    note: str = Field(default="", description="自然语言简单描述")


class BuildPromptResponse(BaseModel):
    prompt: str
    selections: dict[str, str] = Field(default_factory=dict)
    elements: list[str] = Field(default_factory=list)
    note: str = ""


class GeneratedImage(BaseModel):
    id: str
    label: str
    url: str


class ReportDoc(BaseModel):
    """从 ComfyUI 正式工作流「报告N｜标题」节点提取的一份详细报告。"""

    key: str = Field(..., description="报告序号标识，如“报告2”")
    title: str = Field(..., description="报告标题说明，如“最终选中创意方案中文设计简报”")
    content: str = Field(..., description="节点原始文本内容（PreviewAny 输出）")


class SynthesisResult(BaseModel):
    id: str = Field(..., description="任务 ID")
    kind: TaskKind = Field(default=TaskKind.HOT_SYNTHESIS, description="任务类型：爆款合成 / 设计款")
    status: SynthesisStatus = Field(default=SynthesisStatus.SUCCEEDED, description="任务状态")
    mode: str = Field(default="poc", description="执行路径：poc（占位）| gpu（仙宫云+ComfyUI 真实生成）")
    progress_message: str = Field(default="", description="当前阶段说明，用于前端展示进度提示")
    error_message: str | None = Field(default=None, description="status=failed 时的失败原因")

    az_product_url: str = ""
    az_product_image_urls: list[str] = Field(
        default_factory=list,
        description="AZ 商品参考图直链，结果页「AZ 爆款商品图」展示",
    )
    competitor_product_id: str = ""
    competitor_product_title: str = ""
    competitor_product_image_url: str = ""
    competitor_detail_images: list[str] = Field(
        default_factory=list,
        description="竞品详情多图，结果页「竞品爆款商品图」展示；为空时退回主图",
    )
    competitor_source_url: str = ""
    competitor_source_site: str = ""

    # 人为干预回显
    intervention_selections: dict[str, str] = Field(default_factory=dict)
    intervention_elements: list[str] = Field(default_factory=list)
    intervention_note: str = ""
    intervention_prompt: str = ""

    # 设计款专用
    source_image_url: str = Field(default="", description="设计款上传原图可访问 URL")
    product_attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="设计款产品属性（结构化 JSON，后续对接面料分析/重设计节点输出）",
    )

    images: list[GeneratedImage] = Field(default_factory=list, description="生成的商品图，完成前为空")
    panorama_image: GeneratedImage | None = Field(
        default=None,
        description=(
            "拆分前的 4×2 全景母版缩略图，用于可视化页面首屏展示；"
            "POC 占位路径或正式模板未定位到全景母版节点时为空"
        ),
    )
    report_markdown: str = Field(default="", description="分析报告概要（Markdown），完成前为空")
    report_docs: list[ReportDoc] = Field(
        default_factory=list,
        description=(
            "从工作流「报告N」节点提取的详细报告列表，用于分析报告分区展示与下载 zip 拆分为独立 md 文件；"
            "POC 占位路径或节点文本提取失败时为空列表"
        ),
    )
    # 相似款标记：结果页「标记相似款」后写入；历史红标 + 不进选品企划池
    marked_as_similar_style: bool = Field(
        default=False,
        description="是否已标记为相似款（与在售 AZ 款重叠过高，不进企划池）",
    )
    marked_similar_goods_ids: list[str] = Field(
        default_factory=list,
        description="被标记为相似的 AZ goods_id 列表",
    )
    eligible_for_planning_pool: bool = Field(
        default=True,
        description="是否可进入选品企划池；标记相似款后为 false",
    )

    created_at: str
    updated_at: str = ""


class SynthesisSummary(BaseModel):
    """历史列表条目：裁剪掉 report_markdown / report_docs / 完整 images，仅保留列表展示所需字段。"""

    id: str
    kind: TaskKind = TaskKind.HOT_SYNTHESIS
    status: SynthesisStatus
    mode: str
    progress_message: str = ""
    error_message: str | None = None

    az_product_url: str = ""
    competitor_product_title: str = ""
    competitor_product_image_url: str = ""
    competitor_source_site: str = ""
    source_image_url: str = ""

    thumbnail_url: str = Field(default="", description="缩略图：优先取第 1 张生成图，未完成时退回输入图")
    image_count: int = Field(default=0, description="已生成图片数量")
    title: str = Field(default="", description="列表主标题")
    marked_as_similar_style: bool = False
    marked_similar_goods_ids: list[str] = Field(default_factory=list)
    eligible_for_planning_pool: bool = True
    created_at: str
    updated_at: str = ""


class SynthesisListResponse(BaseModel):
    items: list[SynthesisSummary] = Field(default_factory=list)

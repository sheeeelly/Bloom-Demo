"""
az-bloom 配置模块：从 .env 读取运行配置，对外提供统一入口。

一期数据来源为本地种子文件（SEED_DATA_PATH），二期接入真实爬虫数据后
可在此扩展数据库连接配置，无需改动业务代码。
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(override=True)

BASE_DIR = Path(__file__).parent


def _env_str(name: str, default: str) -> str:
    """读取字符串型环境变量：.env 中 `KEY=`（空值）与未配置该 KEY 一样视为“未设置”，
    统一回退到默认值，避免 os.getenv 对空字符串也原样返回导致的路径类配置被误置空。
    """
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value


# 当前使用环境：test | prod，暂只影响日志级别等非关键配置
ENV = os.getenv("ENV", "test").lower()

# 服务监听端口（本地开发用，Docker 部署由 Dockerfile 内的 uvicorn 命令决定）
PORT = int(os.getenv("PORT", 8000))

# 选品种子数据文件路径，二期替换为真实爬虫产出的数据源时，
# 可切换为数据库配置或新的文件路径，无需改动 API / 前端。
SEED_DATA_PATH = Path(_env_str("SEED_DATA_PATH", str(BASE_DIR / "data" / "seed_products.json")))


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# ============================================================
#  爆款合成 · 仙宫云 GPU 实例 + ComfyUI 接入配置
#  未配置 XGY_OPEN_API_TOKEN 或 SYNTHESIS_GPU_ENABLED=false 时，
#  /api/synthesis 自动回退为 POC 占位合成，不影响 Demo 可用性。
# ============================================================

# 合成能力总开关：关闭时走 POC 占位逻辑（复用竞品主图，不访问仙宫云/ComfyUI）
SYNTHESIS_GPU_ENABLED = _env_bool("SYNTHESIS_GPU_ENABLED", False)

# 仙宫云 OpenAPI：访问令牌入口 https://www.xiangongyun.com/console/user/accesstoken
XGY_OPEN_API_BASE_URL = os.getenv("XGY_OPEN_API_BASE_URL", "https://api.xiangongyun.com").rstrip("/")
XGY_OPEN_API_TOKEN = os.getenv("XGY_OPEN_API_TOKEN", "")

# 目标 GPU 实例定位方式：优先使用精确 instance_id（直接查询，无需先拉取实例列表）；
# 未配置 id 时退回按名称精确匹配，再退回按关键字（逗号分隔）模糊匹配
XGY_INSTANCE_ID = os.getenv("XGY_INSTANCE_ID", "")  # 当前目标：.env 中的实例 ID
XGY_INSTANCE_NAME = os.getenv("XGY_INSTANCE_NAME", "")
XGY_INSTANCE_NAME_KEYWORDS = [
    kw.strip() for kw in os.getenv("XGY_INSTANCE_NAME_KEYWORDS", "").split(",") if kw.strip()
]

XGY_REQUEST_TIMEOUT_SECONDS = float(os.getenv("XGY_REQUEST_TIMEOUT_SECONDS", 30))
XGY_REQUEST_RETRIES = int(os.getenv("XGY_REQUEST_RETRIES", 3))
XGY_BOOT_WAIT_TIMEOUT_SECONDS = float(os.getenv("XGY_BOOT_WAIT_TIMEOUT_SECONDS", 180))
XGY_BOOT_POLL_INTERVAL_SECONDS = float(os.getenv("XGY_BOOT_POLL_INTERVAL_SECONDS", 5))
# 实例空闲超过该时长（秒）后自动关机释放 GPU，降低闲置成本；<=0 表示不自动关机
XGY_IDLE_SHUTDOWN_SECONDS = float(os.getenv("XGY_IDLE_SHUTDOWN_SECONDS", 600))
# 后台空闲检查轮询间隔（秒）
XGY_IDLE_CHECK_INTERVAL_SECONDS = float(os.getenv("XGY_IDLE_CHECK_INTERVAL_SECONDS", 60))

# ComfyUI 公网地址拼接规则：https://{instance_id}-{port}{host_suffix}
COMFY_SCHEME = os.getenv("COMFY_SCHEME", "https")
COMFY_PORT = int(os.getenv("COMFY_PORT", 8188))
COMFY_HOST_SUFFIX = os.getenv("COMFY_HOST_SUFFIX", ".container.x-gpu.com")
COMFY_READY_TIMEOUT_SECONDS = float(os.getenv("COMFY_READY_TIMEOUT_SECONDS", 90))
COMFY_READY_POLL_INTERVAL_SECONDS = float(os.getenv("COMFY_READY_POLL_INTERVAL_SECONDS", 3))
# 正式工作流内含 GP Image 生成（默认超时 600s）+ GPT 高清精修（默认超时 900s）等多段云端调用，
# 需要比占位工作流更充裕的总超时；实际未就绪时会提前失败并携带错误信息，不会白等
COMFY_GENERATE_TIMEOUT_SECONDS = float(os.getenv("COMFY_GENERATE_TIMEOUT_SECONDS", 1800))
COMFY_GENERATE_POLL_INTERVAL_SECONDS = float(os.getenv("COMFY_GENERATE_POLL_INTERVAL_SECONDS", 3))

# 正式 ComfyUI 工作流模板路径（ComfyUI 网页端「导出（API）」得到的 JSON）。
# 该模板内嵌 Cloudsway GPT / GP Image 云端代理地址（URL 中带租户路由标识），
# 与 .env 同等敏感，不提交仓库（见 .gitignore /workflows/）；部署时需手动放置。
# 文件不存在时，/api/synthesis 的 GPU 路径自动退回核心节点占位工作流（仅验证链路，不做真实创意生成）。
# 默认 product_design_v13.json：V13「指定模型仅高清…」UI 导出转 API 版
COMFY_WORKFLOW_TEMPLATE_PATH = _env_str(
    "COMFY_WORKFLOW_TEMPLATE_PATH", str(BASE_DIR / "workflows" / "product_design_v13.json")
)

# 设计款开款工作流（ComfyUI「导出（API）」JSON）。
# UI 格式参考见 workflows/fashion_design_ui.json；未配置或文件不存在时 GPU 路径退回占位工作流。
COMFY_FASHION_WORKFLOW_TEMPLATE_PATH = _env_str(
    "COMFY_FASHION_WORKFLOW_TEMPLATE_PATH",
    str(BASE_DIR / "workflows" / "fashion_design_api.json"),
)

# 方案四 V13：仓库内为 UI 导出 JSON（product_design_v13_ui.json），不可直接 /prompt。
# 运行时默认仍用 API 模板（v9/V12）；待 Comfy「导出 API」后把路径指到 API 版即可。
COMFY_V13_UI_WORKFLOW_PATH = _env_str(
    "COMFY_V13_UI_WORKFLOW_PATH",
    str(BASE_DIR / "workflows" / "product_design_v13_ui.json"),
)
COMFY_GAP_FUSION_WORKFLOW_TEMPLATE_PATH = _env_str(
    "COMFY_GAP_FUSION_WORKFLOW_TEMPLATE_PATH",
    str(BASE_DIR / "workflows" / "product_design_v13.json"),
)

# ============================================================
#  相似款参考卡 · AZ Copilot（导购）属性召回
#  Cookie 未配置时结果页走本地演示降级，不阻塞主链路。
# ============================================================
AZ_COPILOT_BASE_URL = os.getenv("AZ_COPILOT_BASE_URL", "https://az-copilot-t.azazie.com").rstrip("/")
# 默认走 Zendesk Workflow 同步 JSON（无需 Cookie）；sse 才需要 Cookie
AZ_COPILOT_MODE = os.getenv("AZ_COPILOT_MODE", "zendesk").strip().lower()
AZ_COPILOT_ZENDESK_PATH = os.getenv("AZ_COPILOT_ZENDESK_PATH", "/v1/chat/zendesk")
AZ_COPILOT_CHAT_PATH = os.getenv("AZ_COPILOT_CHAT_PATH", "/v1/chat")
AZ_COPILOT_TIMEOUT = float(os.getenv("AZ_COPILOT_TIMEOUT", 90))
AZ_COPILOT_COOKIE = os.getenv("AZ_COPILOT_COOKIE", "")
# 本期 Demo 默认 false：半真本地索引；true 时才尝试 az-copilot
SIMILAR_PEERS_USE_COPILOT = _env_bool("SIMILAR_PEERS_USE_COPILOT", False)

# ============================================================
#  方案四 · 爬虫周报 / 商品多图库 / AZ Copilot 热卖
# ============================================================
CRAWLER_ROOT = Path(
    _env_str(
        "CRAWLER_ROOT",
        str(Path.home() / "Desktop" / "自动化选品" / "爬虫" / "competitor_project_optimized-master"),
    )
)
PRODUCT_IMAGE_STORE_PATH = Path(
    _env_str(
        "PRODUCT_IMAGE_STORE_PATH",
        str(BASE_DIR / "data" / "product_image_store.json"),
    )
)
# 历史生成持久化：SQLite + 本地图片/报告目录（代码变更/重启后仍可回看）
HISTORY_DIR = Path(_env_str("HISTORY_DIR", str(BASE_DIR / "data" / "history")))
# Cloudsway（Comfy 自定义节点）：提交时注入；勿把真 Key 写进 workflows/*.json
CLOUDSWAY_API_KEY = os.getenv("CLOUDSWAY_API_KEY", "").strip()
# GPT-5.5（规划 / PersonReplace 等节点）
CLOUDSWAY_GPT_BASE_URL = _env_str(
    "CLOUDSWAY_GPT_BASE_URL",
    "",
)
CLOUDSWAY_GPT_MODEL_ID = _env_str("CLOUDSWAY_GPT_MODEL_ID", "MaaS_GP_5.5_20260424")
CLOUDSWAY_GPT_API = _env_str("CLOUDSWAY_GPT_API", "openai-completions")
CLOUDSWAY_GPT_MODEL_NAME = _env_str("CLOUDSWAY_GPT_MODEL_NAME", "GPT-5.5")
# GP Image 2（生图节点，可选覆盖）
CLOUDSWAY_IMAGE_BASE_URL = _env_str(
    "CLOUDSWAY_IMAGE_BASE_URL",
    "",
)
CLOUDSWAY_IMAGE_MODEL_ID = _env_str("CLOUDSWAY_IMAGE_MODEL_ID", "MaaS_GP_image_2")

# 爆款合成 AZ 热卖默认走 Copilot zendesk；失败回退本地缓存/种子
GAP_FUSION_USE_COPILOT_HOT = _env_bool("GAP_FUSION_USE_COPILOT_HOT", True)
# AZ 热卖本地缓存 TTL（秒）。首屏 /seed 与选款会多次调用；过短会导致反复打 Copilot（单次约 7–8s）
GAP_FUSION_AZ_HOT_CACHE_TTL = float(os.getenv("GAP_FUSION_AZ_HOT_CACHE_TTL", "3600"))

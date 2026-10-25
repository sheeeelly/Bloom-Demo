"""
仙宫云 GPU 实例生命周期管理（固定命名实例 + 自动开关机）。

策略与 aigc-retouch-worker 的 `config_ui_power.py` 保持一致：
- 按实例名称 / 关键字匹配一台常驻实例（不做弹性部署 / 销毁）
- 任务到来时：如实例未运行则调用开机接口，轮询至 running 且 ComfyUI `/queue` 可访问
- 空闲超过 `XGY_IDLE_SHUTDOWN_SECONDS` 后台自动关机释放 GPU，降低闲置成本

本模块只服务单进程 Demo 场景，使用内存状态 + 线程锁，不依赖外部队列/数据库。
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import config
from app.services import comfy_client
from app.services.xiangongyun_client import (
    XiangongyunBusyError,
    XiangongyunClient,
    XiangongyunError,
    mask_instance,
    resolve_target_instance,
)

logger = logging.getLogger(__name__)

# 已在开机/部署，只需等 running，不要再发 boot
_BOOTING_STATUSES = {
    "booting",
    "starting",
    "deploying",
    "restarting",
    "creating",
    "pending",
    "rebooting",
}
# 关机/释放 GPU 过程中发 boot 会返回「暂时无法进行操作」
_SHUTTING_STATUSES = {
    "shutting_down",
    "shutdowning",
    "stopping",
    "releasing",
    "releasing_gpu",
}
_DEAD_STATUSES = {"destroying", "destroyed"}


class InstanceNotConfiguredError(RuntimeError):
    """未开启 GPU 合成能力或缺少必要配置。"""


@dataclass
class _InstanceState:
    instance_id: str = ""
    instance_name: str = ""
    comfy_base_url: str = ""
    status: str = "unknown"
    last_used_at: float = 0.0
    last_checked_at: float = 0.0


_state = _InstanceState()
_state_lock = threading.RLock()
_idle_watcher_started = False
_idle_watcher_lock = threading.Lock()


def gpu_enabled() -> bool:
    return bool(config.SYNTHESIS_GPU_ENABLED)


def _build_client() -> XiangongyunClient:
    if not config.XGY_OPEN_API_TOKEN:
        raise InstanceNotConfiguredError("未配置 XGY_OPEN_API_TOKEN，无法调用仙宫云 OpenAPI")
    return XiangongyunClient(
        token=config.XGY_OPEN_API_TOKEN,
        base_url=config.XGY_OPEN_API_BASE_URL,
        timeout_seconds=config.XGY_REQUEST_TIMEOUT_SECONDS,
        retries=config.XGY_REQUEST_RETRIES,
    )


def _resolve_instance(client: XiangongyunClient) -> dict[str, Any]:
    """优先按已知 instance_id 直接查询（省去列表接口）；否则退回按名称/关键字匹配。"""
    if config.XGY_INSTANCE_ID:
        instance = client.get_instance(config.XGY_INSTANCE_ID)
        if not instance.get("id"):
            raise XiangongyunError(f"未找到指定实例：XGY_INSTANCE_ID={config.XGY_INSTANCE_ID}")
        return instance

    if not config.XGY_INSTANCE_NAME and not config.XGY_INSTANCE_NAME_KEYWORDS:
        raise InstanceNotConfiguredError(
            "未配置 XGY_INSTANCE_ID / XGY_INSTANCE_NAME / XGY_INSTANCE_NAME_KEYWORDS，无法定位目标 GPU 实例"
        )
    instances = client.list_instances()
    return resolve_target_instance(
        instances, name=config.XGY_INSTANCE_NAME, keywords=config.XGY_INSTANCE_NAME_KEYWORDS
    )


def _comfy_base_url(instance_id: str) -> str:
    suffix = config.COMFY_HOST_SUFFIX if config.COMFY_HOST_SUFFIX.startswith(".") else f".{config.COMFY_HOST_SUFFIX}"
    return f"{config.COMFY_SCHEME}://{instance_id}-{config.COMFY_PORT}{suffix}".rstrip("/")


def ensure_instance_ready() -> str:
    """
    确保目标实例已开机且 ComfyUI 可访问，返回可直接访问的 ComfyUI base_url。

    并发调用时通过 `_state_lock` 串行化，避免重复触发开机指令。
    """
    if not gpu_enabled():
        raise InstanceNotConfiguredError("SYNTHESIS_GPU_ENABLED 未开启，未启用 GPU 合成能力")

    _start_idle_watcher_once()

    with _state_lock:
        client = _build_client()
        instance = _resolve_instance(client)
        instance_id = str(instance.get("id") or "")
        instance_name = str(instance.get("name") or "")
        if not instance_id:
            raise XiangongyunError(f"匹配到实例但缺少 id：{mask_instance(instance)}")

        status = str(instance.get("status") or "").strip().lower()
        logger.info("仙宫云目标实例 id=%s name=%s status=%s", instance_id, instance_name, status or "-")

        if status != "running":
            instance = _wait_until_running(client, instance_id, initial_status=status)

        comfy_base_url = _comfy_base_url(instance_id)
        comfy_client.wait_ready(
            comfy_base_url,
            timeout_seconds=config.COMFY_READY_TIMEOUT_SECONDS,
            poll_interval_seconds=config.COMFY_READY_POLL_INTERVAL_SECONDS,
        )

        now = time.time()
        _state.instance_id = instance_id
        _state.instance_name = instance_name
        _state.comfy_base_url = comfy_base_url
        _state.status = "running"
        _state.last_used_at = now
        _state.last_checked_at = now
        return comfy_base_url


def _wait_until_running(
    client: XiangongyunClient,
    instance_id: str,
    *,
    initial_status: str = "",
) -> dict[str, Any]:
    """等到 running。过渡态只轮询；关机完成后再 boot；「暂时无法操作」不当作终态失败。"""
    deadline = time.monotonic() + config.XGY_BOOT_WAIT_TIMEOUT_SECONDS
    last_status = (initial_status or "").strip().lower()
    next_boot_at = 0.0
    last_busy = ""

    while time.monotonic() < deadline:
        if last_status == "running":
            return client.get_instance(instance_id)
        if last_status in _DEAD_STATUSES:
            raise XiangongyunError(f"实例状态异常，无法开机使用：id={instance_id} status={last_status}")

        waiting_only = last_status in _BOOTING_STATUSES or last_status in _SHUTTING_STATUSES
        if waiting_only:
            logger.info("实例切换中，等待可开机/运行 id=%s status=%s", instance_id, last_status or "-")
        elif time.monotonic() >= next_boot_at:
            logger.info("实例未运行，下发开机指令 id=%s status=%s", instance_id, last_status or "-")
            try:
                client.boot_instance(instance_id)
                next_boot_at = time.monotonic() + max(15.0, config.XGY_BOOT_POLL_INTERVAL_SECONDS * 3)
            except XiangongyunBusyError as exc:
                last_busy = str(exc)
                next_boot_at = time.monotonic() + max(8.0, config.XGY_BOOT_POLL_INTERVAL_SECONDS * 2)
                logger.warning("开机暂不可用，将继续轮询实例状态 id=%s err=%s", instance_id, exc)

        time.sleep(config.XGY_BOOT_POLL_INTERVAL_SECONDS)
        instance = client.get_instance(instance_id)
        last_status = str(instance.get("status") or "").strip().lower()
        if last_status == "running":
            return instance

    detail = last_busy or f"last_status={last_status or '-'}"
    raise XiangongyunError(
        "GPU 实例正在开机或关机切换中，暂时不能下发开机指令。"
        "请等 1–2 分钟后再点一次生成；若连续失败，请到仙宫云控制台确认实例状态。"
        f"（id={instance_id} {detail}）"
    )


def friendly_gpu_error(exc: BaseException) -> str:
    """把仙宫云原始 dict 错误收成对操作者可读的一句话。"""
    text = str(exc)
    if "暂时无法进行操作" in text or "暂时无法操作" in text or isinstance(exc, XiangongyunBusyError):
        return (
            "GPU 实例正在开机或关机切换中，暂时不能操作。"
            "请等 1–2 分钟后再点一次生成；"
            "若连续失败，请到仙宫云控制台确认实例是否可开机。"
        )
    return text


def touch_usage() -> None:
    """任务实际使用实例时调用，刷新空闲计时起点。"""
    with _state_lock:
        _state.last_used_at = time.time()


def _start_idle_watcher_once() -> None:
    global _idle_watcher_started
    if _idle_watcher_started or config.XGY_IDLE_SHUTDOWN_SECONDS <= 0:
        return
    with _idle_watcher_lock:
        if _idle_watcher_started:
            return
        thread = threading.Thread(target=_idle_watcher_loop, name="xgy-idle-watcher", daemon=True)
        thread.start()
        _idle_watcher_started = True
        logger.info(
            "已启动实例空闲自动关机检查线程 idle_seconds=%s interval=%s",
            config.XGY_IDLE_SHUTDOWN_SECONDS,
            config.XGY_IDLE_CHECK_INTERVAL_SECONDS,
        )


def _idle_watcher_loop() -> None:
    while True:
        time.sleep(max(5.0, config.XGY_IDLE_CHECK_INTERVAL_SECONDS))
        try:
            _check_and_shutdown_if_idle()
        except Exception:
            logger.exception("空闲自动关机检查异常")


def _check_and_shutdown_if_idle() -> None:
    with _state_lock:
        if not _state.instance_id or _state.status != "running":
            return
        idle_seconds = time.time() - _state.last_used_at
        if idle_seconds < config.XGY_IDLE_SHUTDOWN_SECONDS:
            return
        instance_id = _state.instance_id

    try:
        client = _build_client()
        client.shutdown_release_gpu(instance_id)
    except XiangongyunError as exc:
        logger.warning("空闲自动关机失败 id=%s err=%s", instance_id, exc)
        return

    with _state_lock:
        if _state.instance_id == instance_id:
            _state.status = "shutting_down"
    logger.info("实例空闲超时，已下发关机释放 GPU 指令 id=%s idle_seconds=%.0f", instance_id, idle_seconds)

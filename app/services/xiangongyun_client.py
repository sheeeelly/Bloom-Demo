"""
仙宫云 OpenAPI 客户端（GPU 实例管理）。

参考 aigc-retouch-worker 项目的接入方式：仙宫云官方不提供 Python SDK，
统一走 `requests` 直连 OpenAPI（base_url=https://api.xiangongyun.com），
鉴权方式为 `Authorization: Bearer <token>`。

本模块只封装项目实际需要的只读查询 + 开关机接口，不涉及部署 / 销毁 /
镜像写入等高危操作（与知识库《仙宫云OpenAPI速查.md》保持一致的收录范围）。
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

# 查询实例响应中的敏感字段，日志与对外接口一律脱敏，避免泄露
_SENSITIVE_INSTANCE_FIELDS = {"password", "jupyter_token", "xgcos_token", "ssh_key"}


class XiangongyunError(RuntimeError):
    """仙宫云 OpenAPI 调用失败（网络异常、鉴权失败、响应异常等）。"""


class XiangongyunBusyError(XiangongyunError):
    """实例处于开关机切换等过渡态，暂时无法下发指令（可等待后重试）。"""


class InstanceNotFoundError(XiangongyunError):
    """按名称 / 关键字未匹配到任何实例。"""


def is_temporarily_unavailable(result: dict[str, Any] | None) -> bool:
    """仙宫云业务错误：实例正在开机/关机/释放 GPU 时不能再下发开关机。"""
    payload = result or {}
    msg = str(payload.get("msg") or payload.get("message") or "")
    return "暂时无法进行操作" in msg or "暂时无法操作" in msg


def mask_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """返回脱敏后的实例信息副本，供日志或前端展示使用。"""
    masked = dict(instance)
    for field in _SENSITIVE_INSTANCE_FIELDS:
        if masked.get(field):
            masked[field] = "***"
    return masked


def _normalize_match_text(value: str) -> str:
    return re.sub(r"[\s_\-—–]+", "", str(value or "")).lower()


def resolve_target_instance(
    instances: list[dict[str, Any]],
    *,
    name: str = "",
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    """
    按精确名称优先、关键字兜底的方式，从实例列表中选出目标实例。

    与 aigc-retouch-worker 的 `resolve_target_instance_spec` 保持同样的匹配语义，
    避免同名/相似实例误连。
    """
    keywords = keywords or []
    name = (name or "").strip()

    if name:
        matched = [i for i in instances if str(i.get("name") or "").strip() == name]
        if matched:
            return _choose_instance(matched)

    if keywords:
        normalized_keywords = [_normalize_match_text(k) for k in keywords if str(k or "").strip()]
        matched = [
            i
            for i in instances
            if normalized_keywords
            and all(k in _normalize_match_text(str(i.get("name") or "")) for k in normalized_keywords)
        ]
        if matched:
            return _choose_instance(matched)

    available = [str(i.get("name") or "") for i in instances if i.get("name")]
    raise InstanceNotFoundError(
        f"未找到匹配的仙宫云实例：name={name!r} keywords={keywords!r}，当前可用实例：{available}"
    )


def _choose_instance(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """多实例命中时优先选择运行中的实例，其次取第一个。"""
    for instance in candidates:
        if str(instance.get("status") or "").strip().lower() == "running":
            return instance
    return candidates[0]


class XiangongyunClient:
    """仙宫云 OpenAPI 轻量客户端，封装实例查询与开关机操作。"""

    def __init__(
        self,
        token: str,
        base_url: str = "https://api.xiangongyun.com",
        timeout_seconds: float = 30.0,
        retries: int = 3,
    ) -> None:
        if not token:
            raise XiangongyunError("未配置 XGY_OPEN_API_TOKEN，无法调用仙宫云 OpenAPI")
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._retries = max(1, retries)
        self._session = requests.Session()

    def _headers(self) -> dict[str, str]:
        auth = self._token if self._token.lower().startswith("bearer ") else f"Bearer {self._token}"
        return {"Authorization": auth}

    def _request(self, method: str, path: str, *, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        last_exc: BaseException | None = None
        for attempt in range(1, self._retries + 1):
            try:
                response = self._session.request(
                    method,
                    url,
                    headers=self._headers(),
                    json=json_body,
                    timeout=self._timeout,
                )
                if response.status_code >= 500:
                    response.raise_for_status()
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_exc = exc
                if attempt >= self._retries:
                    break
                logger.warning("仙宫云 OpenAPI 请求失败，将重试 %s/%s：%s %s err=%s", attempt, self._retries, method, path, exc)
                time.sleep(min(2.0 * attempt, 10.0))
        raise XiangongyunError(f"仙宫云 OpenAPI 请求失败：{method} {path} err={last_exc}") from last_exc

    def list_instances(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/open/instances")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        instances = (data or {}).get("list")
        return instances if isinstance(instances, list) else []

    def get_instance(self, instance_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/open/instance/{instance_id}")
        data = payload.get("data")
        if isinstance(data, dict):
            return data.get("instance") if isinstance(data.get("instance"), dict) else data
        return payload if isinstance(payload, dict) else {}

    def boot_instance(self, instance_id: str) -> None:
        """异步下发开机命令，需自行轮询 `get_instance` 确认状态变为 running。"""
        result = self._request("POST", "/open/instance/boot", json_body={"id": instance_id})
        if result.get("success") is False:
            if is_temporarily_unavailable(result):
                raise XiangongyunBusyError(f"仙宫云开机指令暂不可用：{result}")
            raise XiangongyunError(f"仙宫云开机指令失败：{result}")

    def shutdown_release_gpu(self, instance_id: str) -> None:
        """异步下发关机释放 GPU 命令，磁盘按低价保留计费，可随时重新开机。"""
        result = self._request(
            "POST", "/open/instance/shutdown_release_gpu", json_body={"id": instance_id}
        )
        if result.get("success") is False:
            if is_temporarily_unavailable(result):
                raise XiangongyunBusyError(f"仙宫云关机指令暂不可用：{result}")
            raise XiangongyunError(f"仙宫云关机指令失败：{result}")

"""
AZ Copilot 能力封装（Bloom 相似款召回）。

默认走 Zendesk Workflow 同步 JSON 合同（无需浏览器 Cookie）：
  POST {AZ_COPILOT_BASE_URL}/v1/chat/zendesk
  文档：Desktop/zendesk-workflow-chat-api.md

可选回退：SSE `/v1/chat` + AZ_COPILOT_COOKIE（导购页探测合同）。
由 AZ_COPILOT_MODE=zendesk|sse 控制，默认 zendesk。
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

import requests

import config  # noqa: F401  # 触发 dotenv

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = str(
    getattr(config, "AZ_COPILOT_BASE_URL", None)
    or os.environ.get("AZ_COPILOT_BASE_URL", "https://az-copilot-t.azazie.com")
).rstrip("/")
DEFAULT_ZENDESK_PATH = str(
    getattr(config, "AZ_COPILOT_ZENDESK_PATH", None)
    or os.environ.get("AZ_COPILOT_ZENDESK_PATH", "/v1/chat/zendesk")
)
DEFAULT_SSE_PATH = str(
    getattr(config, "AZ_COPILOT_CHAT_PATH", None)
    or os.environ.get("AZ_COPILOT_CHAT_PATH", "/v1/chat")
)
DEFAULT_MODE = str(
    getattr(config, "AZ_COPILOT_MODE", None)
    or os.environ.get("AZ_COPILOT_MODE", "zendesk")
).strip().lower()
DEFAULT_TIMEOUT = float(
    getattr(config, "AZ_COPILOT_TIMEOUT", None)
    or os.environ.get("AZ_COPILOT_TIMEOUT", "90")
)


class CopilotConfigError(RuntimeError):
    """配置缺失（仅 SSE 模式需要 Cookie）。"""


def get_cookie() -> str:
    cookie = (
        getattr(config, "AZ_COPILOT_COOKIE", None)
        or os.environ.get("AZ_COPILOT_COOKIE", "")
    ).strip()
    if not cookie:
        raise CopilotConfigError(
            "SSE 模式需要 AZ_COPILOT_COOKIE；或改用默认 AZ_COPILOT_MODE=zendesk"
        )
    return cookie


def is_configured() -> bool:
    """zendesk 模式默认可用；sse 模式需 Cookie。"""
    mode = DEFAULT_MODE
    if mode in {"sse", "chat", "stream"}:
        cookie = (
            getattr(config, "AZ_COPILOT_COOKIE", None)
            or os.environ.get("AZ_COPILOT_COOKIE", "")
        ).strip()
        return bool(cookie)
    return True


@dataclass
class SseEvent:
    event: str | None
    data_raw: str
    data_json: Any | None
    parse_error: str | None = None


@dataclass
class CopilotChatResult:
    session_id: str
    message: str
    status_code: int | None
    elapsed_ms: int
    events: list[SseEvent] = field(default_factory=list)
    error: str | None = None
    products: list[dict[str, Any]] = field(default_factory=list)
    answer_text: str = ""
    mode: str = "live"  # live | unavailable
    api_mode: str = "zendesk"  # zendesk | sse
    tools_called: list[str] = field(default_factory=list)
    raw_errors: list[str] = field(default_factory=list)


def iter_sse_events(lines: Iterable[bytes | str]) -> Iterator[SseEvent]:
    buf_event: str | None = None
    buf_data: list[str] = []

    def flush() -> SseEvent | None:
        nonlocal buf_event, buf_data
        if not buf_data and buf_event is None:
            return None
        data_raw = "\n".join(buf_data)
        parsed: Any | None = None
        parse_error: str | None = None
        if data_raw:
            stripped = data_raw.strip()
            if stripped == "[DONE]":
                parsed = "[DONE]"
            else:
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    parse_error = f"{exc.__class__.__name__}: {exc}"
        evt = SseEvent(
            event=buf_event,
            data_raw=data_raw,
            data_json=parsed,
            parse_error=parse_error,
        )
        buf_event = None
        buf_data = []
        return evt

    for raw in lines:
        if isinstance(raw, bytes):
            line = raw.decode("utf-8", errors="replace")
        else:
            line = raw
        if line == "":
            evt = flush()
            if evt is not None:
                yield evt
            continue
        if line.startswith(":"):
            continue
        if ":" in line:
            field_name, _, value = line.partition(":")
            if value.startswith(" "):
                value = value[1:]
        else:
            field_name, value = line, ""
        if field_name == "event":
            buf_event = value
        elif field_name == "data":
            buf_data.append(value)

    evt = flush()
    if evt is not None:
        yield evt


def extract_product_cards(events: list[SseEvent]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    for evt in events:
        payload = evt.data_json
        if not (
            isinstance(payload, dict)
            and payload.get("type") == "products"
            and isinstance(payload.get("items"), list)
        ):
            continue
        for item in payload["items"]:
            if not isinstance(item, dict):
                continue
            key = str(item.get("objectID") or item.get("goodsId") or id(item))
            if key in seen:
                continue
            seen.add(key)
            cards.append(item)
    return cards


def extract_answer_text(events: list[SseEvent]) -> str:
    chunks: list[str] = []
    for evt in events:
        payload = evt.data_json
        if (
            isinstance(payload, dict)
            and payload.get("type") == "text"
            and isinstance(payload.get("content"), str)
        ):
            chunks.append(payload["content"].strip())
    return "\n".join(c for c in chunks if c).strip()


def normalize_product_card(item: dict[str, Any]) -> dict[str, Any]:
    def _as_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        text = str(value).strip()
        return [text] if text else []

    return {
        "product_id": str(item.get("objectID") or item.get("goodsId") or ""),
        "goods_id": str(item.get("goodsId") or ""),
        "name": item.get("name")
        or item.get("goodsAccurateName")
        or item.get("goodsName")
        or "",
        "category_name": item.get("categoryName") or "",
        "price": item.get("display_price")
        or item.get("price_display")
        or item.get("price")
        or item.get("shopPrice"),
        "color": item.get("color") or "",
        "origin_color": item.get("originColor") or "",
        "color_family": _as_list(item.get("colorFamily") or item.get("colors")),
        "silhouette": _as_list(item.get("silhouette")),
        "neckline": _as_list(item.get("neckline")),
        "fabric": _as_list(item.get("fabric")),
        "dress_length": _as_list(item.get("dressLength")),
        "features": _as_list(item.get("features")),
        "image_url": item.get("image_url") or item.get("goodsThumb") or "",
        "url": item.get("url") or item.get("goodsUrl") or "",
        "in_stock": item.get("in_stock") if "in_stock" in item else item.get("inStock"),
        "sales_volume": item.get("salesVolume"),
        "rating": item.get("commentRating") or item.get("rating"),
    }


def call_zendesk_chat(
    message: str,
    *,
    conversation_id: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    path: str = DEFAULT_ZENDESK_PATH,
    timeout: float = DEFAULT_TIMEOUT,
    images: list[str] | None = None,
    locale: str = "en-us",
    country: str = "US",
    region: str = "CA",
) -> CopilotChatResult:
    """同步 JSON：POST /v1/chat/zendesk（Bloom 默认路径）。"""
    cid = conversation_id or f"bloom_similar_{uuid.uuid4().hex[:16]}"
    url = base_url.rstrip("/") + path
    body: dict[str, Any] = {
        "conversation_id": cid,
        "message": message,
        "images": images or [],
        "text_format": "plain",
        "context": {
            "channel": "bloom",
            "ticket_id": "bloom_similar_peers",
            "requester_id": "az_bloom",
            "locale": locale,
            "country": country,
            "region": region,
            "user_token": "",
        },
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    started = time.time()
    status_code: int | None = None
    error: str | None = None
    products: list[dict[str, Any]] = []
    answer_text = ""
    tools_called: list[str] = []
    raw_errors: list[str] = []

    try:
        resp = requests.post(url, json=body, headers=headers, timeout=timeout)
        status_code = resp.status_code
        if resp.status_code >= 400:
            error = f"HTTP {resp.status_code}: {resp.text[:1500]}"
        else:
            data = resp.json()
            if not isinstance(data, dict):
                error = "zendesk response is not a JSON object"
            else:
                answer_text = str(data.get("reply") or "").strip()
                raw_products = data.get("products") if isinstance(data.get("products"), list) else []
                products = [
                    normalize_product_card(p) for p in raw_products if isinstance(p, dict)
                ]
                tools = data.get("tools_called")
                if isinstance(tools, list):
                    tools_called = [str(t) for t in tools]
                errs = data.get("errors")
                if isinstance(errs, list):
                    raw_errors = [str(e) for e in errs if e]
                if raw_errors and not products:
                    error = "; ".join(raw_errors)
    except requests.RequestException as exc:
        error = f"{exc.__class__.__name__}: {exc}"
        logger.warning("az-copilot zendesk call failed: %s", error)
    except ValueError as exc:
        error = f"JSONDecodeError: {exc}"

    elapsed_ms = int((time.time() - started) * 1000)
    return CopilotChatResult(
        session_id=cid,
        message=message,
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        error=error,
        products=products,
        answer_text=answer_text,
        mode="live" if not error else "unavailable",
        api_mode="zendesk",
        tools_called=tools_called,
        raw_errors=raw_errors,
    )


def call_sse_chat(
    message: str,
    *,
    session_id: str | None = None,
    user_token: str = "",
    base_url: str = DEFAULT_BASE_URL,
    chat_path: str = DEFAULT_SSE_PATH,
    timeout: float = DEFAULT_TIMEOUT,
) -> CopilotChatResult:
    """SSE：POST /v1/chat + Cookie（导购页合同，可选）。"""
    sid = session_id or str(uuid.uuid4())
    try:
        cookie = get_cookie()
    except CopilotConfigError as exc:
        return CopilotChatResult(
            session_id=sid,
            message=message,
            status_code=None,
            elapsed_ms=0,
            error=str(exc),
            mode="unavailable",
            api_mode="sse",
        )

    url = base_url.rstrip("/") + chat_path
    body = {"session_id": sid, "message": message, "user_token": user_token}
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Cookie": cookie,
    }

    started = time.time()
    events: list[SseEvent] = []
    status_code: int | None = None
    error: str | None = None

    try:
        with requests.post(url, json=body, headers=headers, stream=True, timeout=timeout) as resp:
            status_code = resp.status_code
            resp.encoding = "utf-8"
            if resp.status_code >= 400:
                try:
                    text = resp.text
                except Exception as read_exc:  # pragma: no cover
                    text = f"<failed to read body: {read_exc}>"
                error = f"HTTP {resp.status_code}: {text[:1500]}"
            else:
                events = list(iter_sse_events(resp.iter_lines(decode_unicode=False)))
    except requests.RequestException as exc:
        error = f"{exc.__class__.__name__}: {exc}"
        logger.warning("az-copilot sse call failed: %s", error)

    elapsed_ms = int((time.time() - started) * 1000)
    raw_products = extract_product_cards(events) if not error else []
    return CopilotChatResult(
        session_id=sid,
        message=message,
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        events=events,
        error=error,
        products=[normalize_product_card(p) for p in raw_products],
        answer_text=extract_answer_text(events) if not error else "",
        mode="live" if not error else "unavailable",
        api_mode="sse",
    )


def call_chat(
    message: str,
    *,
    session_id: str | None = None,
    images: list[str] | None = None,
    **kwargs: Any,
) -> CopilotChatResult:
    """统一入口：默认 zendesk；AZ_COPILOT_MODE=sse 时走 Cookie SSE。"""
    mode = DEFAULT_MODE
    if mode in {"sse", "chat", "stream"}:
        return call_sse_chat(message, session_id=session_id, **kwargs)
    return call_zendesk_chat(
        message,
        conversation_id=session_id,
        images=images,
    )

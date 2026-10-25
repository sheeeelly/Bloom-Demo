"""
生成任务持久化结果库（爆款合成 + 设计款共用）。

存储形态：
  - SQLite 索引：`data/history/bloom_history.db`
  - 任务目录：`data/history/{task_id}/result.json` + `images/` + `reports/`
  - 内存缓存：加速同进程读写

成功任务会把远程 Comfy 图下载到本地，并把 URL 改写为 `/history-assets/{id}/...`，
这样代码改动、服务重启、甚至 Comfy 实例关机后，历史记录与图片仍可打开。
"""
from __future__ import annotations

import json
import logging
import mimetypes
import re
import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import config

if TYPE_CHECKING:
    from app.schemas.synthesis import SynthesisResult

logger = logging.getLogger(__name__)

_RESULTS: dict[str, "SynthesisResult"] = {}
_RESULTS_LOCK = threading.Lock()
_DB_LOCK = threading.Lock()
_MATERIALIZE_LOCK = threading.Lock()
_MATERIALIZING: set[str] = set()

_HISTORY_URL_PREFIX = "/history-assets/"


def history_root() -> Path:
    root = Path(getattr(config, "HISTORY_DIR", config.BASE_DIR / "data" / "history"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def db_path() -> Path:
    return history_root() / "bloom_history.db"


def task_dir(task_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", task_id.strip()) or "unknown"
    path = history_root() / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _DB_LOCK:
        conn = _connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS synthesis_tasks (
                  id TEXT PRIMARY KEY,
                  kind TEXT NOT NULL DEFAULT 'hot_synthesis',
                  status TEXT NOT NULL,
                  mode TEXT NOT NULL DEFAULT 'poc',
                  title TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL DEFAULT '',
                  updated_at TEXT NOT NULL DEFAULT '',
                  payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_synthesis_created "
                "ON synthesis_tasks(created_at DESC)"
            )
            conn.commit()
        finally:
            conn.close()


def _result_title(result: "SynthesisResult") -> str:
    if getattr(result, "kind", None) and str(result.kind.value if hasattr(result.kind, "value") else result.kind) == "design":
        return str((result.product_attributes or {}).get("design_name_zh") or "设计款")
    return str(result.competitor_product_title or result.id)


def _to_model(data: dict[str, Any]) -> "SynthesisResult":
    from app.schemas.synthesis import SynthesisResult

    return SynthesisResult.model_validate(data)


def _serialize(result: "SynthesisResult") -> dict[str, Any]:
    return result.model_dump(mode="json")


def _write_json_file(result: "SynthesisResult") -> None:
    path = task_dir(result.id) / "result.json"
    path.write_text(
        json.dumps(_serialize(result), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _upsert_db(result: "SynthesisResult") -> None:
    payload = json.dumps(_serialize(result), ensure_ascii=False)
    kind = result.kind.value if hasattr(result.kind, "value") else str(result.kind)
    status = result.status.value if hasattr(result.status, "value") else str(result.status)
    with _DB_LOCK:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO synthesis_tasks
                  (id, kind, status, mode, title, created_at, updated_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  kind=excluded.kind,
                  status=excluded.status,
                  mode=excluded.mode,
                  title=excluded.title,
                  created_at=excluded.created_at,
                  updated_at=excluded.updated_at,
                  payload_json=excluded.payload_json
                """,
                (
                    result.id,
                    kind,
                    status,
                    result.mode or "poc",
                    _result_title(result),
                    result.created_at or "",
                    result.updated_at or result.created_at or "",
                    payload,
                ),
            )
            conn.commit()
        finally:
            conn.close()


def _load_from_disk(task_id: str) -> "SynthesisResult | None":
    json_path = task_dir(task_id) / "result.json"
    if json_path.is_file():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return _to_model(data)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("read result.json failed id=%s err=%s", task_id, exc)

    with _DB_LOCK:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT payload_json FROM synthesis_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        finally:
            conn.close()
    if not row:
        return None
    try:
        return _to_model(json.loads(row["payload_json"]))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("parse db payload failed id=%s err=%s", task_id, exc)
        return None


def _write_report_files(result: "SynthesisResult") -> None:
    """报告文本同步落盘（不依赖图片下载）。"""
    reports_dir = task_dir(result.id) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    if result.report_markdown:
        (reports_dir / "report.md").write_text(result.report_markdown.rstrip() + "\n", encoding="utf-8")
    for doc in result.report_docs or []:
        digits = "".join(ch for ch in str(doc.key) if ch.isdigit())
        slug = f"report{digits}" if digits else re.sub(r"[^A-Za-z0-9_-]+", "_", str(doc.key) or "report")
        body = f"# {doc.key}｜{doc.title}\n\n{doc.content}\n"
        (reports_dir / f"{slug}.md").write_text(body, encoding="utf-8")


def _persist(result: "SynthesisResult", *, materialize: bool = True) -> "SynthesisResult":
    _write_json_file(result)
    _upsert_db(result)
    status = result.status.value if hasattr(result.status, "value") else str(result.status)
    if status in {"succeeded", "failed"}:
        try:
            _write_report_files(result)
        except OSError:
            logger.exception("write report files failed id=%s", result.id)
    if materialize and status == "succeeded":
        return _maybe_materialize_async(result)
    return result


def fetch_asset_bytes(url: str, *, timeout: float = 60.0) -> bytes | None:
    if not url:
        return None
    if url.startswith(_HISTORY_URL_PREFIX):
        rel = url[len(_HISTORY_URL_PREFIX) :]
        local = history_root() / rel
        if local.is_file():
            try:
                return local.read_bytes()
            except OSError:
                return None
        return None
    if url.startswith("/static/"):
        local = Path(config.BASE_DIR) / "app" / "static" / url[len("/static/") :]
        if local.is_file():
            try:
                return local.read_bytes()
            except OSError:
                return None
    if url.startswith("/"):
        # 其他本站相对路径：不跨网拉取
        return None
    try:
        req = Request(url, headers={"User-Agent": "az-bloom-history/1.0"})
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — 历史落盘拉取公开/Comfy 图
            return resp.read()
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        logger.warning("history fetch failed url=%s err=%s", url[:160], exc)
        return None


def _ext_from_url_or_bytes(url: str, content: bytes | None) -> str:
    path = url.split("?", 1)[0]
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    if content and content[:8].startswith(b"\x89PNG"):
        return ".png"
    if content and content[:2] == b"\xff\xd8":
        return ".jpg"
    guessed, _ = mimetypes.guess_type(path)
    if guessed == "image/png":
        return ".png"
    return ".jpg"


def _local_asset_url(task_id: str, relative: str) -> str:
    return f"{_HISTORY_URL_PREFIX}{task_id}/{relative}".replace("\\", "/")


def _needs_materialize(result: "SynthesisResult") -> bool:
    urls: list[str] = []
    for img in result.images or []:
        urls.append(img.url or "")
    if result.panorama_image and result.panorama_image.url:
        urls.append(result.panorama_image.url)
    if result.source_image_url:
        urls.append(result.source_image_url)
    for url in urls:
        if url and not url.startswith(_HISTORY_URL_PREFIX) and not url.startswith("/static/"):
            return True
    # 报告文件缺失也补写
    reports_dir = task_dir(result.id) / "reports"
    if (result.report_docs or result.report_markdown) and not reports_dir.exists():
        return True
    return False


def materialize_assets(result: "SynthesisResult") -> "SynthesisResult":
    """把远程图/报告落到本地，并改写可访问 URL。"""
    from app.schemas.synthesis import GeneratedImage

    root = task_dir(result.id)
    images_dir = root / "images"
    reports_dir = root / "reports"
    images_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    changed = False

    def save_image(url: str, stem: str) -> str:
        nonlocal changed
        if not url:
            return url
        if url.startswith(_HISTORY_URL_PREFIX):
            return url
        content = fetch_asset_bytes(url)
        if not content and url.startswith("/static/"):
            # 静态资源保留原 URL，无需复制
            return url
        if not content:
            return url
        ext = _ext_from_url_or_bytes(url, content)
        filename = f"{stem}{ext}"
        (images_dir / filename).write_bytes(content)
        changed = True
        return _local_asset_url(result.id, f"images/{filename}")

    new_images: list[GeneratedImage] = []
    for index, img in enumerate(result.images or [], start=1):
        new_url = save_image(img.url, f"{index:02d}")
        new_images.append(GeneratedImage(id=img.id, label=img.label, url=new_url))

    panorama = result.panorama_image
    if panorama and panorama.url:
        p_url = save_image(panorama.url, "00_panorama")
        panorama = GeneratedImage(id=panorama.id, label=panorama.label, url=p_url)

    source_url = result.source_image_url or ""
    if source_url and not source_url.startswith(("/static/", _HISTORY_URL_PREFIX)):
        source_url = save_image(source_url, "source")

    _write_report_files(result)

    meta = {
        "id": result.id,
        "kind": result.kind.value if hasattr(result.kind, "value") else result.kind,
        "status": result.status.value if hasattr(result.status, "value") else result.status,
        "mode": result.mode,
        "created_at": result.created_at,
        "updated_at": result.updated_at,
        "assets_localized": True,
    }
    (root / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    updated = result.model_copy(
        update={
            "images": new_images,
            "panorama_image": panorama,
            "source_image_url": source_url,
        }
    )
    if changed or _needs_materialize(result):
        _write_json_file(updated)
        _upsert_db(updated)
        with _RESULTS_LOCK:
            _RESULTS[updated.id] = updated
        logger.info(
            "history assets materialized id=%s images=%s reports=%s",
            updated.id,
            len(new_images),
            len(list(reports_dir.glob("*.md"))),
        )
    return updated


def _maybe_materialize_async(result: "SynthesisResult") -> "SynthesisResult":
    if not _needs_materialize(result):
        return result
    with _MATERIALIZE_LOCK:
        if result.id in _MATERIALIZING:
            return result
        _MATERIALIZING.add(result.id)

    def _job() -> None:
        try:
            current = get(result.id) or result
            materialize_assets(current)
        except Exception:  # noqa: BLE001
            logger.exception("materialize history assets failed id=%s", result.id)
        finally:
            with _MATERIALIZE_LOCK:
                _MATERIALIZING.discard(result.id)

    threading.Thread(target=_job, name=f"history-materialize-{result.id[:8]}", daemon=True).start()
    return result


def put(result: "SynthesisResult") -> None:
    with _RESULTS_LOCK:
        _RESULTS[result.id] = result
    _persist(result, materialize=True)


def get(task_id: str) -> "SynthesisResult | None":
    with _RESULTS_LOCK:
        cached = _RESULTS.get(task_id)
    if cached is not None:
        return cached
    loaded = _load_from_disk(task_id)
    if loaded is not None:
        with _RESULTS_LOCK:
            _RESULTS[task_id] = loaded
    return loaded


def update(task_id: str, **changes: object) -> "SynthesisResult | None":
    with _RESULTS_LOCK:
        current = _RESULTS.get(task_id)
        if current is None:
            current = _load_from_disk(task_id)
            if current is None:
                return None
        updated = current.model_copy(update=changes)
        _RESULTS[task_id] = updated
    return _persist(updated, materialize=True)


def list_all() -> list["SynthesisResult"]:
    """按库中全部任务返回（含磁盘持久化）；内存未命中则回填。"""
    with _DB_LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT id, payload_json FROM synthesis_tasks ORDER BY created_at DESC"
            ).fetchall()
        finally:
            conn.close()

    out: list["SynthesisResult"] = []
    for row in rows:
        tid = row["id"]
        with _RESULTS_LOCK:
            cached = _RESULTS.get(tid)
        if cached is not None:
            out.append(cached)
            continue
        try:
            item = _to_model(json.loads(row["payload_json"]))
        except (json.JSONDecodeError, ValueError):
            item = _load_from_disk(tid)
        if item is None:
            continue
        with _RESULTS_LOCK:
            _RESULTS[tid] = item
        out.append(item)

    # 兼容：磁盘有 result.json 但尚未进库的孤儿任务
    for path in history_root().glob("*/result.json"):
        tid = path.parent.name
        if any(x.id == tid for x in out):
            continue
        item = _load_from_disk(tid)
        if item is None:
            continue
        _upsert_db(item)
        with _RESULTS_LOCK:
            _RESULTS[tid] = item
        out.append(item)

    return out


def bootstrap() -> int:
    """进程启动时初始化库，并预热内存索引。"""
    _init_db()
    items = list_all()
    logger.info("history store ready tasks=%s dir=%s", len(items), history_root())
    return len(items)


# 模块导入即初始化（uvicorn reload 子进程也会执行）
try:
    bootstrap()
except Exception:  # noqa: BLE001
    logger.exception("history store bootstrap failed")

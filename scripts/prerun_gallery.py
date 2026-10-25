#!/usr/bin/env python3
"""
按 data/gallery/inputs.json 用真合成链路预跑品类效果图，并登记到 gallery manifest。

用法（在 az-bloom-master 根目录、已激活 venv）：
  1. cp data/gallery/inputs.example.json data/gallery/inputs.json
  2. 填入每类输入图链接（用户提供）
  3. 确保 SYNTHESIS_GPU_ENABLED=true 且 Comfy 可用（计划：必须真引擎）
  4. 先启动服务：uvicorn app.main:app --port 8000
  5. python scripts/prerun_gallery.py

失败结果也会写入 manifest（如实展示，供老板评判）。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:8000"
INPUTS = ROOT / "data" / "gallery" / "inputs.json"
POLL_SECONDS = 8
MAX_WAIT = 2400


def _http_json(method: str, path: str, body: dict | None = None) -> dict:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        raw = json.dumps(body).encode("utf-8")
        data = raw
        headers["Content-Type"] = "application/json"
    req = Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _wait_synthesis(task_id: str) -> dict:
    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        result = _http_json("GET", f"/api/synthesis/{task_id}")
        status = result.get("status")
        print(f"  … {task_id} status={status} {result.get('progress_message') or ''}")
        if status in {"succeeded", "failed"}:
            return result
        time.sleep(POLL_SECONDS)
    return {"id": task_id, "status": "failed", "error_message": "prerun_timeout"}


def main() -> int:
    if not INPUTS.exists():
        print(f"缺少 {INPUTS}，请先复制 inputs.example.json 并填入输入链接")
        return 1

    with INPUTS.open("r", encoding="utf-8") as fh:
        inputs = json.load(fh)

    health = _http_json("GET", "/api/health")
    print("health:", health)

    categories = inputs.get("categories") or []
    for cat in categories:
        cat_id = cat.get("id") or ""
        items = cat.get("items") or []
        print(f"\n=== category {cat_id} ({len(items)} items) ===")
        for item in items:
            item_id = item.get("id") or "item"
            print(f"-> prerun {item_id}")
            payload = {
                "az_product_url": item.get("az_product_url") or "https://www.azazie.com/",
                "az_product_image_urls": item.get("az_product_image_urls") or [],
                "competitor_product_id": item.get("competitor_product_id") or item_id,
                "competitor_product_title": item.get("competitor_product_title") or item_id,
                "competitor_product_image_url": item.get("competitor_product_image_url") or "",
                "competitor_detail_images": item.get("competitor_detail_images") or [],
                "competitor_source_url": item.get("competitor_source_url") or "",
                "competitor_source_site": item.get("competitor_source_site") or "",
            }
            if not payload["competitor_product_image_url"] and not payload["competitor_detail_images"]:
                print("  skip: 缺少竞品图链接")
                _http_json(
                    "POST",
                    "/api/gallery/items",
                    {
                        "category_id": cat_id,
                        "item_id": item_id,
                        **{k: payload[k] for k in payload},
                        "status": "failed",
                        "error_message": "missing_competitor_image",
                        "mode": "prerun",
                    },
                )
                continue

            try:
                created = _http_json("POST", "/api/synthesis", payload)
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                print(f"  create failed: {exc.code} {detail}")
                _http_json(
                    "POST",
                    "/api/gallery/items",
                    {
                        "category_id": cat_id,
                        "item_id": item_id,
                        **{k: payload[k] for k in payload},
                        "status": "failed",
                        "error_message": f"create_http_{exc.code}",
                        "mode": "prerun",
                    },
                )
                continue
            except URLError as exc:
                print(f"  create failed: {exc}")
                return 2

            task_id = created.get("id")
            if created.get("status") == "succeeded":
                result = created
            else:
                result = _wait_synthesis(task_id)

            image_urls = [img.get("url") for img in (result.get("images") or []) if img.get("url")]
            if result.get("panorama_image") and result["panorama_image"].get("url"):
                image_urls.insert(0, result["panorama_image"]["url"])

            status = "ready" if result.get("status") == "succeeded" and image_urls else "failed"
            _http_json(
                "POST",
                "/api/gallery/items",
                {
                    "category_id": cat_id,
                    "item_id": item_id,
                    **{k: payload[k] for k in payload},
                    "result_image_urls": image_urls[:8],
                    "synthesis_task_id": task_id or "",
                    "status": status,
                    "error_message": result.get("error_message") or "",
                    "mode": result.get("mode") or "",
                },
            )
            print(f"  registered status={status} images={len(image_urls)}")

    print("\nDone. Open http://127.0.0.1:8000/gallery.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

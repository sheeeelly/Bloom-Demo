"""
AZ Bloom（AI选品）— FastAPI 入口
启动：uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app.routers import (
    az_product,
    dashboard,
    design,
    gallery,
    gap_fusion,
    library,
    monitor,
    new_category,
    selection,
    similar_peers,
    synthesis,
)

STATIC_DIR = Path(__file__).parent / "static"


class NoCacheStaticFiles(StaticFiles):
    """
    Demo 项目前端（原生 HTML/JS/CSS）迭代频繁，浏览器对无 `Cache-Control` 的静态资源会启用
    启发式缓存，单纯刷新页面（非强制刷新）时可能仍命中刷新前的旧版 `result.js` 等文件，
    导致新功能「看起来没生效」。这里强制每次请求都带 `Cache-Control: no-cache`，
    浏览器会照常用 ETag/Last-Modified 向服务端校验（未变化时仍走 304，不影响性能），
    但绝不会跳过校验直接复用本地缓存，确保刷新页面即可拿到最新前端代码。
    """

    def file_response(self, *args: object, **kwargs: object) -> Response:
        response = super().file_response(*args, **kwargs)  # type: ignore[arg-type]
        response.headers["Cache-Control"] = "no-cache"
        return response


# 页面入口（index / result / history）同样禁用强缓存，理由同 NoCacheStaticFiles
_NO_CACHE_HEADERS = {"Cache-Control": "no-cache"}

app = FastAPI(
    title="Bloom",
    description="视觉与创意 · 双爆款合成 / 趋势改造",
    version="2.3.0",
)

# ── API 路由 ────────────────────────────────────────────────────
app.include_router(selection.router)
app.include_router(similar_peers.router)
app.include_router(synthesis.router)
app.include_router(design.router)
app.include_router(gap_fusion.router)
app.include_router(az_product.router)
app.include_router(gallery.router)
app.include_router(new_category.router)
app.include_router(dashboard.router)
app.include_router(monitor.router)
app.include_router(library.router)


# ── 健康检查 ────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "az-bloom"}


# ── 静态文件 & 页面 ────────────────────────────────────────────
app.mount("/static", NoCacheStaticFiles(directory=str(STATIC_DIR)), name="static")

# 历史生成本地资产（图片/报告）：与代码变更无关，落在 data/history/
_HISTORY_DIR = Path(__file__).resolve().parent.parent / "data" / "history"
_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/history-assets",
    NoCacheStaticFiles(directory=str(_HISTORY_DIR)),
    name="history-assets",
)


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "studio.html"), headers=_NO_CACHE_HEADERS)


@app.get("/studio.html")
def studio_page():
    return FileResponse(str(STATIC_DIR / "studio.html"), headers=_NO_CACHE_HEADERS)


@app.get("/index.html")
def aicreate_page():
    return FileResponse(str(STATIC_DIR / "index.html"), headers=_NO_CACHE_HEADERS)


@app.get("/result.html")
def result_page():
    return FileResponse(str(STATIC_DIR / "result.html"), headers=_NO_CACHE_HEADERS)


@app.get("/history.html")
def history_page():
    return RedirectResponse(url="/library.html", status_code=302)


@app.get("/library.html")
def library_page():
    return FileResponse(str(STATIC_DIR / "library.html"), headers=_NO_CACHE_HEADERS)


@app.get("/dashboard.html")
def dashboard_page():
    return FileResponse(str(STATIC_DIR / "dashboard.html"), headers=_NO_CACHE_HEADERS)


@app.get("/monitor.html")
def monitor_page():
    return FileResponse(str(STATIC_DIR / "monitor.html"), headers=_NO_CACHE_HEADERS)


@app.get("/workbench.html")
def workbench_page():
    return FileResponse(str(STATIC_DIR / "workbench.html"), headers=_NO_CACHE_HEADERS)


@app.get("/design.html")
def design_page():
    return FileResponse(str(STATIC_DIR / "design.html"), headers=_NO_CACHE_HEADERS)


@app.get("/gap-fusion.html")
def gap_fusion_page():
    return FileResponse(str(STATIC_DIR / "gap-fusion.html"), headers=_NO_CACHE_HEADERS)


@app.get("/gallery.html")
def gallery_page():
    return FileResponse(str(STATIC_DIR / "gallery.html"), headers=_NO_CACHE_HEADERS)


@app.get("/blank.html")
def blank_page():
    return FileResponse(str(STATIC_DIR / "blank.html"), headers=_NO_CACHE_HEADERS)


@app.get("/new-category.html")
def new_category_page():
    return FileResponse(str(STATIC_DIR / "new-category.html"), headers=_NO_CACHE_HEADERS)


@app.exception_handler(404)
async def not_found(request, exc):
    # 非 API 未知路径回落作品首页
    if not request.url.path.startswith("/api"):
        return RedirectResponse(url="/", status_code=302)
    # API 路径下的 404 可能来自业务逻辑主动抛出的 HTTPException（如「合成结果不存在或已过期」），
    # 需要透传其原始 detail，否则会被这里统一覆盖成没有意义的 "Not found"，前端也就没法展示准确原因
    detail = getattr(exc, "detail", None) or "Not found"
    return JSONResponse({"detail": detail}, status_code=404)

"""前端托管：单页应用（React SPA）。

构建产物位于 ``web/spa``（Vite 本地输出或 host 镜像多阶段构建写入）。
鉴权完全交由前端 ``AuthProvider`` 处理：访问任意页面时前端拉取 ``/api/me``，401 自动跳转 ``/login``。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

WEB_DIR = Path(__file__).resolve().parent
SPA_DIR = WEB_DIR / "spa"
SPA_INDEX = SPA_DIR / "index.html"

# 后端保留前缀：这些路径不回退到 SPA，未匹配时返回 404
API_PREFIXES = ("api/", "internal/", "assets/")


class ImmutableStaticFiles(StaticFiles):
    """静态资源统一短缓存。

    当前前端使用稳定文件名（如 index.js/index.css），不能使用 immutable 长缓存，
    否则新版本部署后浏览器会长期命中旧资源。
    """

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "no-cache"
        return response


def install_pages(app: FastAPI) -> None:
    if not SPA_INDEX.exists():
        return

    assets_dir = SPA_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", ImmutableStaticFiles(directory=str(assets_dir)), name="assets")

    def spa_index() -> FileResponse:
        # index.html 引用哈希资源，必须每次校验，避免新部署被缓存挡住
        return FileResponse(SPA_INDEX, headers={"Cache-Control": "no-cache"})

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return HTMLResponse("", status_code=204)

    # 通用 history 回退：非后端前缀的 GET 一律返回 index.html，交由前端 Router 处理
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith(API_PREFIXES):
            raise HTTPException(status_code=404)
        return spa_index()

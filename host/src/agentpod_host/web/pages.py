"""前端托管：单页应用（React SPA）。

构建产物位于 ``web/spa``（由 Vite 输出）。鉴权完全交由前端 ``AuthProvider``
处理：访问任意页面时前端拉取 ``/api/me``，401 自动跳转 ``/login``。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

WEB_DIR = Path(__file__).resolve().parent
SPA_DIR = WEB_DIR / "spa"
SPA_INDEX = SPA_DIR / "index.html"

# 前端 Router 暴露的客户端路由，全部回退到 index.html
CLIENT_ROUTES = ("/", "/login", "/chat", "/skills", "/mcp", "/memory")


class ImmutableStaticFiles(StaticFiles):
    """Vite 产物文件名带内容哈希，可长期不可变缓存，避免重复访问重新下载。"""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
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

    for route in CLIENT_ROUTES:
        app.add_api_route(route, spa_index, methods=["GET"], include_in_schema=False)

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return HTMLResponse("", status_code=204)

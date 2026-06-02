"""前端托管：单页应用（React SPA）。

构建产物位于 ``web/spa``（host 镜像多阶段构建在 Docker 内生成）。
鉴权完全交由前端 ``AuthProvider`` 处理：访问任意页面时前端拉取 ``/api/me``，401 自动跳转 ``/login``。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

WEB_DIR = Path(__file__).resolve().parent
SPA_DIR = WEB_DIR / "spa"
SPA_INDEX = SPA_DIR / "index.html"

# 后端保留前缀：这些路径不回退到 SPA，未匹配时返回 404
API_PREFIXES = ("api/", "internal/", "assets/")
# 禁止对外暴露的 SPA 旁路路径（误拷进 public/ 的依赖等）
SPA_BLOCKED_PREFIXES = ("node_modules/", "package.json", "package-lock.json")


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

    def _spa_static_file(relative_path: str) -> FileResponse | None:
        """favicon 等 SPA 根目录静态文件（构建产物）。"""
        candidate = (SPA_DIR / relative_path).resolve()
        if not candidate.is_file() or SPA_DIR.resolve() not in candidate.parents:
            return None
        return FileResponse(candidate, headers={"Cache-Control": "no-cache"})

    # 通用 history 回退：非后端前缀的 GET 一律返回 index.html，交由前端 Router 处理
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith(API_PREFIXES) or full_path.startswith(SPA_BLOCKED_PREFIXES):
            raise HTTPException(status_code=404)
        if full_path:
            static = _spa_static_file(full_path)
            if static is not None:
                return static
        return spa_index()

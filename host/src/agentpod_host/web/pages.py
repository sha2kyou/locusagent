"""前端页面：登录、Chat、Skills、MCP、Memory、Settings。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..auth.session import read_session

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


def install_pages(app: FastAPI) -> None:
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def root(request: Request):
        if read_session(request) is not None:
            return RedirectResponse("/chat", status_code=302)
        return templates.TemplateResponse(request, "login.html", {})

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard_redirect(request: Request):
        if read_session(request) is None:
            return RedirectResponse("/", status_code=302)
        return RedirectResponse("/chat", status_code=302)

    @app.get("/settings", include_in_schema=False)
    async def settings_redirect(request: Request):
        if read_session(request) is None:
            return RedirectResponse("/", status_code=302)
        return RedirectResponse("/chat?settings=1", status_code=302)

    @app.get("/skills", include_in_schema=False)
    async def skills_page(request: Request):
        if read_session(request) is None:
            return RedirectResponse("/", status_code=302)
        return templates.TemplateResponse(request, "app.html", {"page": "skills"})

    @app.get("/mcp", include_in_schema=False)
    async def mcp_page(request: Request):
        if read_session(request) is None:
            return RedirectResponse("/", status_code=302)
        return templates.TemplateResponse(request, "app.html", {"page": "mcp"})

    @app.get("/memory", include_in_schema=False)
    async def memory_page(request: Request):
        if read_session(request) is None:
            return RedirectResponse("/", status_code=302)
        return templates.TemplateResponse(request, "app.html", {"page": "memory"})

    @app.get("/workspace", include_in_schema=False)
    async def workspace_redirect(request: Request):
        if read_session(request) is None:
            return RedirectResponse("/", status_code=302)
        return RedirectResponse("/skills", status_code=302)

    @app.get("/chat", include_in_schema=False)
    async def chat_page(request: Request):
        if read_session(request) is None:
            return RedirectResponse("/", status_code=302)
        return templates.TemplateResponse(request, "app.html", {"page": "chat"})

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return HTMLResponse("", status_code=204)

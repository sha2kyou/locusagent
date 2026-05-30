"""容器内 Agent FastAPI 入口：lifespan、SQLite、Tools、路由、embedding worker。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import init_db
from .errors import WsError, ws_error_handler, ws_validation_handler
from .logging import configure_logging, get_logger
from .memory import start_embedding_worker, stop_embedding_worker
from .routers import internal as internal_router
from .routers import v1 as v1_router
from .routers import workspace as workspace_router
from .tool_settings import load_tool_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log = get_logger("agent")
    settings = get_settings()
    app.state.settings = settings
    log.info("agent_starting", user_id=settings.user_id, model=settings.llm_model)
    init_db()

    from .core.persistence import expire_stale_runs

    expired = await expire_stale_runs()
    if expired:
        log.info("stale_runs_expired", count=expired)

    from .skills import list_skills
    from .tools import registry as tool_registry

    skills = list_skills()
    tool_settings = load_tool_settings()
    for name, enabled in tool_settings.builtin_tools.items():
        tool_registry.set_enabled(name, enabled)
    app.state.tool_registry = tool_registry
    log.info("agent_ready", skills=len(skills), tools=len(tool_registry.list()))

    await start_embedding_worker()
    from .mcp_.client import start_mcp, stop_mcp

    try:
        await start_mcp()
    except Exception as exc:
        log.error("mcp_start_failed", error=str(exc))

    try:
        yield
    finally:
        from .core.run_manager import shutdown_run_manager
        from .routers.v1 import shutdown_v1_background_tasks

        await shutdown_v1_background_tasks()
        await shutdown_run_manager()
        try:
            await stop_mcp()
        except Exception as exc:
            log.warning("mcp_stop_error", error=str(exc))
        await stop_embedding_worker()
        log.info("agent_stopped")


app = FastAPI(title="AgentPod Agent", version="0.1.0", lifespan=lifespan)

app.add_exception_handler(WsError, ws_error_handler)
app.add_exception_handler(RequestValidationError, ws_validation_handler)

app.include_router(v1_router.router)
app.include_router(workspace_router.router)
app.include_router(internal_router.router)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})

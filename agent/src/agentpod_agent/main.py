"""容器内 Agent FastAPI 入口：lifespan、SQLite、Tools、路由、embedding worker。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import __version__
from .config import get_settings
from .errors import WsError, ws_error_handler, ws_validation_handler
from .logging import configure_logging, get_logger
from .memory import start_embedding_worker, stop_embedding_worker
from .routers import internal as internal_router
from .routers import v1 as v1_router
from .routers import workspace as workspace_router
from .workspace import ensure_workspace_storage_initialized, iter_workspace_ids, set_workspace_id
from .workspace_runtime import (
    mark_workspace_runtime_bootstrapped,
    start_mcp_reconnect_loop,
    stop_mcp_reconnect_loop,
    warm_mcp_runtime_background,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log = get_logger("agent")
    settings = get_settings()
    app.state.settings = settings
    log.info("agent_starting", user_id=settings.user_id, workspaces=len(iter_workspace_ids()))

    from .db import init_db
    from .core.persistence import expire_stale_runs, interrupt_running_runs_on_startup

    interrupt_stats = {"runs_interrupted": 0, "sessions_marked_interrupted": 0}
    for wid in iter_workspace_ids():
        set_workspace_id(wid)
        ensure_workspace_storage_initialized(wid)
        init_db()
        stats = await interrupt_running_runs_on_startup()
        interrupt_stats["runs_interrupted"] += stats["runs_interrupted"]
        interrupt_stats["sessions_marked_interrupted"] += stats["sessions_marked_interrupted"]

    if interrupt_stats["runs_interrupted"] > 0:
        log.info("startup_running_runs_interrupted", **interrupt_stats)

    expired_total = 0
    for wid in iter_workspace_ids():
        set_workspace_id(wid)
        expired_total += await expire_stale_runs()
    if expired_total:
        log.info("stale_runs_expired", count=expired_total)

    from .tools import registry as tool_registry

    app.state.tool_registry = tool_registry
    log.info("agent_ready", tools=len(tool_registry.list()))

    await start_embedding_worker()
    mark_workspace_runtime_bootstrapped()
    for wid in iter_workspace_ids():
        asyncio.create_task(warm_mcp_runtime_background(wid), name=f"mcp-warm-{wid}")
    start_mcp_reconnect_loop()

    try:
        yield
    finally:
        from .core.run_manager import shutdown_run_manager
        from .core.session_title import shutdown_session_title_tasks
        from .mcp_.client import stop_all_mcp
        from .routers.v1 import shutdown_v1_background_tasks

        await stop_mcp_reconnect_loop()
        await shutdown_v1_background_tasks()
        await shutdown_session_title_tasks()
        await shutdown_run_manager()
        try:
            await stop_all_mcp()
        except Exception as exc:
            log.warning("mcp_stop_error", error=str(exc))
        await stop_embedding_worker()
        log.info("agent_stopped")


app = FastAPI(title="AgentPod Agent", version=__version__, lifespan=lifespan)

app.add_exception_handler(WsError, ws_error_handler)
app.add_exception_handler(RequestValidationError, ws_validation_handler)

app.include_router(v1_router.router)
app.include_router(workspace_router.router)
app.include_router(internal_router.router)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})

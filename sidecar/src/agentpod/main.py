"""AgentPod 桌面单体：Host + Agent 单进程 FastAPI。"""

from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

os.environ.setdefault("AGENTPOD_MONOLITH", "1")

from agentpod_agent.errors import WsError, ws_error_handler, ws_validation_handler
from agentpod_agent.memory import start_embedding_worker, stop_embedding_worker
from agentpod_agent.routers import internal as agent_internal_router
from agentpod_agent.routers import v1 as agent_v1_router
from agentpod_agent.routers import workspace as agent_workspace_router
from agentpod_agent.workspace import ensure_workspace_storage_initialized, iter_workspace_ids, set_workspace_id
from agentpod_agent.workspace_runtime import (
    mark_workspace_runtime_bootstrapped,
    start_mcp_reconnect_loop,
    stop_mcp_reconnect_loop,
    warm_mcp_runtime_background,
)
from agentpod_host import __version__
from agentpod_host.config import get_settings
from agentpod_host.db import dispose_engine, init_engine
from agentpod_host.logging import configure_logging, get_logger
from agentpod_host.middleware import install_auth_isolation, install_auto_session, install_internal_network_guard
from agentpod_host.orchestrator import sync_shared_skills
from agentpod_host.bootstrap import ensure_host_ready
from agentpod_host.workspaces import ensure_default_workspace_row
from agentpod_host.app_cache import close_app_cache, init_app_cache
from agentpod_host.routers import attachments_proxy as attachments_proxy_router
from agentpod_host.routers import embedding_proxy as embedding_proxy_router
from agentpod_host.routers import internal_mcp_oauth as internal_mcp_oauth_router
from agentpod_host.routers import internal_notifications as internal_notifications_router
from agentpod_host.routers import internal_scheduled_tasks as internal_scheduled_tasks_router
from agentpod_host.routers import internal_settings as internal_settings_router
from agentpod_host.routers import internal_usage as internal_usage_router
from agentpod_host.routers import jina_proxy as jina_proxy_router
from agentpod_host.routers import llm_proxy as llm_proxy_router
from agentpod_host.routers import me as me_router
from agentpod_host.routers import notifications as notifications_router
from agentpod_host.routers import oauth_mcp as oauth_mcp_router
from agentpod_host.routers import scheduled_tasks as scheduled_tasks_router
from agentpod_host.routers import settings as settings_router
from agentpod_host.routers import tavily_proxy as tavily_proxy_router
from agentpod_host.routers import workspace as host_workspace_router
from agentpod_host.routers import workspaces as workspaces_router
from agentpod_host.scheduled_tasks.queue import scheduled_task_worker_context
from agentpod_host.storage.validate import validate_attachment_storage
from agentpod_shared.settings_store import ensure_agentpod_home, set_bundled_skills_dir, shared_skills_dir
from agentpod_shared.local_embeddings import warm_embedding_model


def _configure_runtime_paths() -> None:
    ensure_agentpod_home()
    bundled_skills = os.environ.get("AGENTPOD_BUNDLED_SKILLS_DIR", "").strip()
    if bundled_skills:
        path = Path(bundled_skills)
        if path.is_dir():
            set_bundled_skills_dir(path)
            return
    repo_root = Path(__file__).resolve().parents[3]
    skills = repo_root / "shared-skills"
    if skills.is_dir():
        set_bundled_skills_dir(skills)
    elif shared_skills_dir() is not None:
        set_bundled_skills_dir(shared_skills_dir())


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_runtime_paths()
    exit_stack = AsyncExitStack()
    configure_logging()
    log = get_logger("agentpod")
    settings = get_settings()
    app.state.settings = settings
    log.info("agentpod_starting", version=app.version)

    validate_attachment_storage(settings)
    await init_engine()
    log.info("db_ready")
    await ensure_host_ready()
    log.info("host_ready")
    await init_app_cache()
    log.info("cache_ready")
    await exit_stack.enter_async_context(scheduled_task_worker_context())

    try:
        seeded = sync_shared_skills()
        log.info("shared_skills_seed_done", count=seeded)
    except Exception as exc:
        log.warning("shared_skills_seed_failed", error=str(exc))

    try:
        from agentpod_host.scheduled_tasks.executor import (
            reconcile_interrupted_scheduled_tasks,
            recover_stale_running_tasks,
        )

        n = await reconcile_interrupted_scheduled_tasks()
        if n:
            log.info("scheduled_tasks_reconciled", count=n)
        n = await recover_stale_running_tasks()
        if n:
            log.info("scheduled_tasks_stale_recovered", count=n)
    except Exception as exc:
        log.warning("scheduled_tasks_startup_recover_failed", error=str(exc))

    from agentpod_agent.config import get_settings as get_agent_settings
    from agentpod_agent.db import init_db
    from agentpod_agent.core.persistence import expire_stale_runs, interrupt_running_runs_on_startup

    agent_settings = get_agent_settings()
    app.state.agent_settings = agent_settings
    log.info("agent_starting", workspaces=len(iter_workspace_ids()))

    interrupt_stats = {"runs_interrupted": 0, "sessions_marked_interrupted": 0}
    todo_stats = {"plans_updated": 0, "steps_interrupted": 0}
    for wid in iter_workspace_ids():
        set_workspace_id(wid)
        ensure_workspace_storage_initialized(wid)
        init_db()
        stats = await interrupt_running_runs_on_startup()
        interrupt_stats["runs_interrupted"] += stats["runs_interrupted"]
        interrupt_stats["sessions_marked_interrupted"] += stats["sessions_marked_interrupted"]
        from agentpod_agent.todos.store import interrupt_in_progress_on_startup

        tstats = await interrupt_in_progress_on_startup()
        todo_stats["plans_updated"] += tstats["plans_updated"]
        todo_stats["steps_interrupted"] += tstats["steps_interrupted"]

    expired_total = 0
    for wid in iter_workspace_ids():
        set_workspace_id(wid)
        expired_total += await expire_stale_runs()

    from agentpod_agent.tools import registry as tool_registry

    app.state.tool_registry = tool_registry
    log.info("agent_ready", tools=len(tool_registry.list()))

    try:
        await warm_embedding_model()
        log.info("embedding_model_ready")
    except Exception as exc:
        log.warning("embedding_model_warm_failed", error=str(exc))

    await start_embedding_worker()
    mark_workspace_runtime_bootstrapped()
    for wid in iter_workspace_ids():
        asyncio.create_task(warm_mcp_runtime_background(wid), name=f"mcp-warm-{wid}")
    start_mcp_reconnect_loop()

    try:
        yield
    finally:
        from agentpod_agent.core.run_manager import shutdown_run_manager
        from agentpod_agent.core.session_title import shutdown_session_title_tasks
        from agentpod_agent.mcp_.client import stop_all_mcp
        from agentpod_agent.routers.v1 import shutdown_v1_background_tasks

        await stop_mcp_reconnect_loop()
        await shutdown_v1_background_tasks()
        await shutdown_session_title_tasks()
        await shutdown_run_manager()
        try:
            await stop_all_mcp()
        except Exception as exc:
            log.warning("mcp_stop_error", error=str(exc))
        await stop_embedding_worker()
        await exit_stack.aclose()
        await close_app_cache()
        await dispose_engine()
        log.info("agentpod_stopped")


app = FastAPI(
    title="AgentPod",
    version=__version__,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_exception_handler(WsError, ws_error_handler)
app.add_exception_handler(RequestValidationError, ws_validation_handler)

install_auth_isolation(app)
install_internal_network_guard(app)
install_auto_session(app)

app.include_router(oauth_mcp_router.router)
app.include_router(me_router.router)
app.include_router(notifications_router.router)
app.include_router(settings_router.router)
app.include_router(scheduled_tasks_router.router)
app.include_router(internal_notifications_router.router)
app.include_router(internal_scheduled_tasks_router.router)
app.include_router(internal_settings_router.router)
app.include_router(internal_usage_router.router)
app.include_router(internal_mcp_oauth_router.router)
app.include_router(embedding_proxy_router.router)
app.include_router(llm_proxy_router.router)
app.include_router(tavily_proxy_router.router)
app.include_router(jina_proxy_router.router)
app.include_router(attachments_proxy_router.router)
app.include_router(host_workspace_router.router)
app.include_router(workspaces_router.router)

app.include_router(agent_v1_router.router)
app.include_router(agent_workspace_router.router)
app.include_router(agent_internal_router.router)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})

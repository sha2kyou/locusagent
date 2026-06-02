"""宿主 FastAPI 入口：lifespan、日志、DB 初始化、根路由、生命周期后台任务。"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import dispose_engine, init_engine
from .logging import configure_logging, get_logger
from .middleware import install_auth_isolation, install_internal_network_guard
from .redis_client import close_redis, init_redis
from .storage.validate import validate_attachment_storage
from .orchestrator import lifecycle_loop, reattach_self_to_user_networks, run_orphan_cleanup_once, sync_shared_skills
from .scheduled_tasks.queue import scheduled_task_worker_context
from .routers import api_v1 as api_v1_router
from .routers import embedding_proxy as embedding_proxy_router
from .routers import attachments_proxy as attachments_proxy_router
from .routers import llm_proxy as llm_proxy_router
from .routers import jina_proxy as jina_proxy_router
from .routers import tavily_proxy as tavily_proxy_router
from .routers import internal as internal_router
from .routers import internal_notifications as internal_notifications_router
from .routers import internal_scheduled_tasks as internal_scheduled_tasks_router
from .routers import internal_settings as internal_settings_router
from .routers import internal_usage as internal_usage_router
from .routers import me as me_router
from .routers import notifications as notifications_router
from .routers import oauth as oauth_router
from .routers import oauth_mcp as oauth_mcp_router
from .routers import internal_mcp_oauth as internal_mcp_oauth_router
from .routers import scheduled_tasks as scheduled_tasks_router
from .routers import settings as settings_router
from .routers import workspace as workspace_router
from .routers import workspaces as workspaces_router
from .web import install_pages


@asynccontextmanager
async def lifespan(app: FastAPI):
    exit_stack = AsyncExitStack()
    configure_logging()
    log = get_logger("host")
    settings = get_settings()
    app.state.settings = settings
    log.info("host_starting", version=app.version)
    validate_attachment_storage(settings)
    await init_engine()
    log.info("db_ready")
    await init_redis()
    log.info("redis_ready")
    await exit_stack.enter_async_context(scheduled_task_worker_context())

    try:
        seeded = sync_shared_skills()
        log.info("shared_skills_seed_done", count=seeded)
    except Exception as exc:
        log.warning("shared_skills_seed_failed", error=str(exc))

    try:
        attached = await reattach_self_to_user_networks()
        log.info("self_networks_reattached", count=attached)
    except Exception as exc:
        log.warning("self_networks_reattach_failed", error=str(exc))

    try:
        orphan_stats = await run_orphan_cleanup_once()
        log.info("startup_orphan_cleanup", **orphan_stats)
    except Exception as exc:
        log.warning("startup_orphan_cleanup_failed", error=str(exc))

    try:
        from .scheduled_tasks.executor import recover_stale_running_tasks

        n = await recover_stale_running_tasks()
        if n:
            log.info("scheduled_tasks_stale_recovered", count=n)
    except Exception as exc:
        log.warning("scheduled_tasks_startup_recover_failed", error=str(exc))

    stop_event = asyncio.Event()
    loop_task = asyncio.create_task(lifecycle_loop(stop_event), name="lifecycle-loop")
    try:
        yield
    finally:
        stop_event.set()
        try:
            await asyncio.wait_for(loop_task, timeout=2.0)
        except TimeoutError:
            loop_task.cancel()
            await asyncio.gather(loop_task, return_exceptions=True)
        await exit_stack.aclose()
        await close_redis()
        await dispose_engine()
        log.info("host_stopped")


app = FastAPI(
    title="AgentPod Host",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

install_auth_isolation(app)
install_internal_network_guard(app)

app.include_router(oauth_router.router)
app.include_router(oauth_mcp_router.router)
app.include_router(me_router.router)
app.include_router(notifications_router.router)
app.include_router(settings_router.router)
app.include_router(scheduled_tasks_router.router)
app.include_router(internal_router.router)
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
app.include_router(api_v1_router.router)
app.include_router(workspace_router.router)
app.include_router(workspaces_router.router)


@app.get("/health")
async def root_health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


install_pages(app)

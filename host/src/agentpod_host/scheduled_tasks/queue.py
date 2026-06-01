"""Procrastinate-backed scheduled task queue."""

from __future__ import annotations

import asyncio
import subprocess
from contextlib import asynccontextmanager
from urllib.parse import urlsplit, urlunsplit

from procrastinate import App, PsycopgConnector

from ..config import get_settings
from ..logging import get_logger

log = get_logger("scheduled_queue")
_WORKER_TASK_NAME = "scheduled-task-worker"


def _to_psycopg_conninfo(database_url: str) -> str:
    raw = database_url.strip()
    if not raw:
        raise RuntimeError("DATABASE_URL is required")
    if raw.startswith("postgresql+asyncpg://"):
        return "postgresql://" + raw[len("postgresql+asyncpg://") :]
    if raw.startswith("postgres+asyncpg://"):
        return "postgresql://" + raw[len("postgres+asyncpg://") :]
    if raw.startswith("postgres://"):
        return "postgresql://" + raw[len("postgres://") :]
    parsed = urlsplit(raw)
    if parsed.scheme in {"postgresql", "postgres"}:
        return urlunsplit(("postgresql", parsed.netloc, parsed.path, parsed.query, parsed.fragment))
    raise RuntimeError("DATABASE_URL must be a PostgreSQL DSN")


_CONNINFO = _to_psycopg_conninfo(get_settings().database_url)
task_queue = App(connector=PsycopgConnector(conninfo=_CONNINFO))


@task_queue.task(queue="scheduled_tasks")
async def run_scheduled_task(task_id: int) -> None:
    from .executor import execute_task_by_id

    await execute_task_by_id(int(task_id))


async def enqueue_scheduled_task(task_id: int) -> None:
    await run_scheduled_task.defer_async(task_id=int(task_id))


def _apply_schema_blocking() -> None:
    cmd = [
        "procrastinate",
        "--app=agentpod_host.scheduled_tasks.queue:task_queue",
        "schema",
        "--apply",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


async def ensure_queue_schema() -> None:
    try:
        await asyncio.to_thread(_apply_schema_blocking)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        detail = stderr or stdout or str(exc)
        raise RuntimeError(f"failed to apply procrastinate schema: {detail}") from exc


@asynccontextmanager
async def scheduled_task_worker_context():
    await ensure_queue_schema()
    async with task_queue.open_async():
        worker = asyncio.create_task(
            task_queue.run_worker_async(
                queues=["scheduled_tasks"],
                name=_WORKER_TASK_NAME,
                install_signal_handlers=False,
            ),
            name=_WORKER_TASK_NAME,
        )
        log.info("scheduled_task_worker_started")
        try:
            yield
        finally:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
            log.info("scheduled_task_worker_stopped")

"""容器生命周期状态机：absent → creating → running → paused → stopped → absent。

约束：
- 每用户一个网络（apod-net-{id}），宿主作为唯一可达通路。
- 容器以 uid=10001、cap_drop=ALL、no-new-privileges、read_only=true 启动。
- INTERNAL_TOKEN 持久保存在用户行（加密），重启复用，避免容器内已存配置失配。
- 同用户启动操作通过 per-user asyncio.Lock 串行化。
"""

from __future__ import annotations

import asyncio
import secrets
import socket
from collections.abc import Callable
from typing import Any, TypeVar

import httpx
from docker.errors import APIError, NotFound
from docker.models.containers import Container
from sqlalchemy import select

T = TypeVar("T")

from ..config import get_settings
from ..db import ContainerStatus, ProvisionStatus, User, get_session
from ..logging import get_logger
from ..security import decrypt_str, encrypt_str
from ..llm_url import host_llm_proxy_base_url
from .agent_env import build_agent_environment, require_llm_configured
from .docker_client import get_docker_client
from .naming import container_name_for, network_name_for, volume_name_for

log = get_logger("orchestrator")

HEALTH_TIMEOUT_COLD_START = 30.0
HEALTH_TIMEOUT_RESUME = 30.0
HEALTH_TIMEOUT_RUNNING = 5.0

_user_locks: dict[int, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()


async def user_lock(user_id: int) -> asyncio.Lock:
    async with _locks_guard:
        lock = _user_locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            _user_locks[user_id] = lock
        return lock


async def _run_blocking(func: Callable[[], T]) -> T:
    return await asyncio.to_thread(func)


def _get_self_container() -> Container | None:
    """获取宿主自身容器（基于 hostname=container short id）。"""
    try:
        return get_docker_client().containers.get(socket.gethostname())
    except (NotFound, APIError):
        return None


async def _set_user_status(
    user_id: int,
    *,
    container_status: ContainerStatus | None = None,
    provision_status: ProvisionStatus | None = None,
    container_id: str | None = None,
    network_name: str | None = None,
    volume_name: str | None = None,
    internal_token: str | None = None,
) -> None:
    async with get_session() as session:
        stmt = select(User).where(User.id == user_id)
        user = (await session.execute(stmt)).scalar_one()
        if container_status is not None:
            user.container_status = container_status.value
        if provision_status is not None:
            user.provision_status = provision_status.value
        if container_id is not None:
            user.container_id = container_id
        if network_name is not None:
            user.network_name = network_name
        if volume_name is not None:
            user.volume_name = volume_name
        if internal_token is not None:
            user.internal_token_enc = encrypt_str(internal_token)


async def _load_user(user_id: int) -> User:
    async with get_session() as session:
        stmt = select(User).where(User.id == user_id)
        return (await session.execute(stmt)).scalar_one()


async def touch_last_active(user_id: int) -> None:
    """更新用户最后活跃时间，驱动空闲暂停判定。"""
    from datetime import datetime, timezone

    async with get_session() as session:
        stmt = select(User).where(User.id == user_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user is not None:
            user.last_active = datetime.now(timezone.utc)


def _ensure_network(network: str):
    client = get_docker_client()
    try:
        return client.networks.get(network)
    except NotFound:
        return client.networks.create(network, driver="bridge", check_duplicate=True)


def _connect_self_to_network(network_name: str) -> bool:
    """确保 host 自身已加入指定 docker 网络（幂等）。返回是否做了实际 connect。

    host 容器重建后会丢失对历史用户网络的连接，需要重新加入才能 DNS 解析容器名。
    """
    client = get_docker_client()
    host_self = _get_self_container()
    if host_self is None:
        return False
    try:
        net = client.networks.get(network_name)
    except NotFound:
        return False
    try:
        net.reload()
    except APIError:
        return False
    containers = net.attrs.get("Containers") or {}
    if host_self.id in containers:
        return False
    try:
        net.connect(host_self)
        log.info("self_attached_to_network", network=network_name)
        return True
    except APIError as exc:
        log.warning("self_attach_failed", network=network_name, error=str(exc))
        return False


async def reattach_self_to_user_networks() -> int:
    """启动时调用：把 host 自己接回所有用户网络（host 重建后必须）。"""

    def _do() -> int:
        client = get_docker_client()
        attached = 0
        for net in client.networks.list():
            name = net.name
            if not name.startswith("apod-net-"):
                continue
            if _connect_self_to_network(name):
                attached += 1
        return attached

    return await _run_blocking(_do)


def _ensure_volume(volume: str, size_limit: str = ""):
    """幂等创建用户数据卷。size_limit 非空时附带磁盘配额（需宿主 FS 支持 project quota）。

    配额仅对新建卷生效；已存在的卷不会被重设配额（避免销毁用户数据）。
    """
    client = get_docker_client()
    try:
        return client.volumes.get(volume)
    except NotFound:
        driver_opts = {"size": size_limit} if size_limit else None
        return client.volumes.create(name=volume, driver="local", driver_opts=driver_opts)


def _find_container(name: str) -> Container | None:
    client = get_docker_client()
    try:
        return client.containers.get(name)
    except NotFound:
        return None


async def _wait_health(container_name: str, *, port: int = 8000, timeout: float = 5.0) -> bool:
    """通过用户网络从宿主探测容器 /health。

    宿主 web 容器与用户容器同处 apod-net-{id} 时可直接以容器名解析。
    """
    deadline = asyncio.get_running_loop().time() + timeout
    interval = 0.2
    url = f"http://{container_name}:{port}/health"
    async with httpx.AsyncClient(timeout=1.0) as client:
        while asyncio.get_running_loop().time() < deadline:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(interval)
    return False


def _host_internal_base_url() -> str:
    """用户容器经宿主网络别名访问 internal API（用户网络不可直达 TEI 等）。"""
    host_self = _get_self_container()
    name = host_self.name if host_self is not None else "host"
    return f"http://{name}:8080"


def _host_embedding_proxy_url() -> str:
    return f"{_host_internal_base_url()}/internal/embedding"


def _host_llm_proxy_url(settings: Any | None = None) -> str:
    s = settings or get_settings()
    return host_llm_proxy_base_url(
        host_internal_base=_host_internal_base_url(),
        llm_base_url=s.llm_base_url,
    )


async def _create_container(user: User) -> str:
    settings = get_settings()
    require_llm_configured(settings)

    container_name = container_name_for(user.id)
    network = network_name_for(user.id)
    volume = volume_name_for(user.id)

    internal_token = secrets.token_urlsafe(32)
    agent_env = build_agent_environment(
        user_id=user.id,
        internal_token=internal_token,
        llm_proxy_base_url=_host_llm_proxy_url(settings),
        embedding_base_url=_host_embedding_proxy_url(),
        embedding_model=settings.embedding_model,
        host_internal_url=_host_internal_base_url(),
        attachment_storage=settings.attachment_storage,
        enable_terminal=settings.enable_terminal,
        terminal_whitelist=settings.terminal_whitelist,
        settings=settings,
    )

    def _do_create() -> str:
        _ensure_network(network)
        _ensure_volume(volume, settings.agent_disk_limit)

        existing = _find_container(container_name)
        if existing is not None:
            existing.remove(force=True)

        client = get_docker_client()
        container = client.containers.run(
            image=settings.agent_image,
            name=container_name,
            user="10001:10001",
            read_only=True,
            tmpfs={"/tmp": "size=128m"},
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            volumes={
                volume: {"bind": "/data", "mode": "rw"},
                "agentpod_shared-skills": {"bind": "/app/skills", "mode": "ro"},
            },
            environment=agent_env,
            mem_limit=settings.agent_memory_limit,
            cpu_quota=settings.agent_cpu_quota,
            pids_limit=settings.agent_pids_limit,
            detach=True,
            network=network,
            restart_policy={"Name": "unless-stopped"},
            labels={
                "agentpod.user_id": str(user.id),
                "agentpod.role": "agent",
            },
        )

        host_self = _get_self_container()
        if host_self is not None:
            try:
                client.networks.get(network).connect(host_self)
            except APIError:
                pass

        return container.id

    container_id = await _run_blocking(_do_create)
    await _set_user_status(
        user.id,
        container_id=container_id,
        network_name=network,
        volume_name=volume,
        internal_token=internal_token,
    )
    return container_id


async def ensure_user_container(user_id: int, *, force_recreate: bool = False) -> ContainerStatus:
    """absent/failed → creating → running。

    幂等：若已 running 且未 force_recreate 直接返回；creating 期间并发请求复用同锁。
    force_recreate：销毁现有容器并按宿主环境变量重建（running/paused/stopped）。
    """
    lock = await user_lock(user_id)
    async with lock:
        user = await _load_user(user_id)
        status = ContainerStatus(user.container_status)

        if status == ContainerStatus.RUNNING and not force_recreate:
            return status
        if status == ContainerStatus.CREATING and not force_recreate:
            return status

        await _set_user_status(
            user_id,
            container_status=ContainerStatus.CREATING,
            provision_status=ProvisionStatus.PENDING,
        )
        try:
            await _create_container(user)
            container_name = container_name_for(user_id)
            ok = await _wait_health(container_name, timeout=HEALTH_TIMEOUT_COLD_START)
            if not ok:
                raise RuntimeError("容器启动后健康探测超时")
            await _set_user_status(
                user_id,
                container_status=ContainerStatus.RUNNING,
                provision_status=ProvisionStatus.READY,
            )
            log.info("container_running", user_id=user_id)
            return ContainerStatus.RUNNING
        except Exception as exc:
            try:
                await _teardown_container_unlocked(user_id, remove_volume=False)
            except Exception as cleanup_exc:
                log.warning(
                    "provision_failed_cleanup",
                    user_id=user_id,
                    error=str(cleanup_exc),
                )
            await _set_user_status(
                user_id,
                container_status=ContainerStatus.ABSENT,
                provision_status=ProvisionStatus.FAILED,
            )
            log.error("container_create_failed", user_id=user_id, error=str(exc))
            raise


async def pause_container(user_id: int) -> None:
    lock = await user_lock(user_id)
    async with lock:
        name = container_name_for(user_id)

        def _do() -> None:
            c = _find_container(name)
            if c is not None and c.status == "running":
                c.pause()

        await _run_blocking(_do)
        await _set_user_status(user_id, container_status=ContainerStatus.PAUSED)
        log.info("container_paused", user_id=user_id)


async def stop_container(user_id: int) -> None:
    lock = await user_lock(user_id)
    async with lock:
        name = container_name_for(user_id)

        def _do() -> None:
            c = _find_container(name)
            if c is None:
                return
            if c.status == "paused":
                c.unpause()
            c.stop(timeout=10)

        await _run_blocking(_do)
        await _set_user_status(user_id, container_status=ContainerStatus.STOPPED)
        log.info("container_stopped", user_id=user_id)


async def _teardown_container_unlocked(user_id: int, *, remove_volume: bool = False) -> None:
    name = container_name_for(user_id)
    network = network_name_for(user_id)
    volume = volume_name_for(user_id)

    def _do() -> None:
        client = get_docker_client()
        c = _find_container(name)
        if c is not None:
            try:
                c.remove(force=True)
            except APIError as exc:
                log.warning("container_remove_failed", user_id=user_id, error=str(exc))
        try:
            net = client.networks.get(network)
            host_self = _get_self_container()
            if host_self is not None:
                try:
                    net.disconnect(host_self, force=True)
                except APIError:
                    pass
            net.remove()
        except (NotFound, APIError):
            pass
        if remove_volume:
            try:
                client.volumes.get(volume).remove(force=True)
            except (NotFound, APIError):
                pass

    await _run_blocking(_do)
    await _set_user_status(
        user_id,
        container_status=ContainerStatus.ABSENT,
        provision_status=ProvisionStatus.PENDING,
    )
    log.info("container_torn_down", user_id=user_id, removed_volume=remove_volume)


async def teardown_container(user_id: int, *, remove_volume: bool = False) -> None:
    lock = await user_lock(user_id)
    async with lock:
        await _teardown_container_unlocked(user_id, remove_volume=remove_volume)


def _inspect_container(name: str) -> str:
    """返回 Docker 容器状态；missing 表示不存在。"""
    c = _find_container(name)
    if c is None:
        return "missing"
    c.reload()
    return c.status


async def _notify_agent_resumed(user_id: int) -> None:
    user = await _load_user(user_id)
    if user.internal_token_enc is None:
        return
    token = decrypt_str(user.internal_token_enc)
    container_name = container_name_for(user_id)
    url = f"http://{container_name}:8000/internal/resume"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers={"X-Internal-Token": token})
            if resp.status_code >= 400:
                log.warning(
                    "agent_resume_notify_failed",
                    user_id=user_id,
                    status=resp.status_code,
                    body=resp.text[:200],
                )
    except httpx.HTTPError as exc:
        log.warning("agent_resume_notify_failed", user_id=user_id, error=str(exc))


async def reconcile_container_state(user_id: int) -> ContainerStatus:
    """对照 Docker 校正 DB 中的容器状态。"""
    name = container_name_for(user_id)
    docker_status = await _run_blocking(lambda: _inspect_container(name))
    user = await _load_user(user_id)
    db_status = ContainerStatus(user.container_status)

    if docker_status == "missing":
        if db_status != ContainerStatus.ABSENT:
            await _set_user_status(
                user_id,
                container_status=ContainerStatus.ABSENT,
                provision_status=ProvisionStatus.PENDING,
            )
        return ContainerStatus.ABSENT

    if docker_status == "running":
        if db_status != ContainerStatus.RUNNING:
            await _set_user_status(user_id, container_status=ContainerStatus.RUNNING)
        return ContainerStatus.RUNNING

    if docker_status == "paused":
        if db_status != ContainerStatus.PAUSED:
            await _set_user_status(user_id, container_status=ContainerStatus.PAUSED)
        return ContainerStatus.PAUSED

    if docker_status in ("exited", "dead", "created"):
        if db_status != ContainerStatus.STOPPED:
            await _set_user_status(user_id, container_status=ContainerStatus.STOPPED)
        return ContainerStatus.STOPPED

    return db_status


async def _try_auto_reprovision(
    user_id: int,
    name: str,
) -> tuple[ContainerStatus, dict[str, Any]] | None:
    try:
        require_llm_configured()
    except RuntimeError:
        return None
    try:
        await ensure_user_container(user_id)
        log.info("container_auto_reprovisioned", user_id=user_id)
        return ContainerStatus.RUNNING, {"container_name": name, "reprovisioned": True}
    except Exception as exc:
        log.error("auto_reprovision_failed", user_id=user_id, error=str(exc))
        return None


async def ensure_container_ready(user_id: int) -> tuple[ContainerStatus, dict[str, Any]]:
    """代理调用前置：处理 running/paused/stopped/creating 四种状态。

    返回 (最终状态, 元信息)；调用方据状态决定 503/转发。
    """
    user = await _load_user(user_id)
    status = ContainerStatus(user.container_status)
    name = container_name_for(user_id)
    network = network_name_for(user_id)

    if status == ContainerStatus.RUNNING:
        docker_status = await _run_blocking(lambda: _inspect_container(name))
        if docker_status == "missing":
            await _set_user_status(
                user_id,
                container_status=ContainerStatus.ABSENT,
                provision_status=ProvisionStatus.PENDING,
            )
            status = ContainerStatus.ABSENT
        elif docker_status == "running":
            await _run_blocking(lambda: _connect_self_to_network(network))
            ok = await _wait_health(name, timeout=HEALTH_TIMEOUT_RUNNING)
            if not ok:
                log.warning("container_health_degraded", user_id=user_id, container=name)
            return ContainerStatus.RUNNING, {"container_name": name}
        if docker_status == "paused":
            await _set_user_status(user_id, container_status=ContainerStatus.PAUSED)
            status = ContainerStatus.PAUSED
        elif docker_status in ("exited", "dead", "created"):
            await _set_user_status(user_id, container_status=ContainerStatus.STOPPED)
            status = ContainerStatus.STOPPED

    if status == ContainerStatus.CREATING:
        return status, {"container_name": name}

    if status == ContainerStatus.ABSENT:
        reprovisioned = await _try_auto_reprovision(user_id, name)
        if reprovisioned is not None:
            return reprovisioned
        return status, {"container_name": name}

    if status not in (ContainerStatus.PAUSED, ContainerStatus.STOPPED):
        return status, {"container_name": name}

    lock = await user_lock(user_id)
    async with lock:
        user = await _load_user(user_id)
        status = ContainerStatus(user.container_status)
        if status == ContainerStatus.RUNNING:
            await _run_blocking(lambda: _connect_self_to_network(network))
            return ContainerStatus.RUNNING, {"container_name": name}

        def _ensure_running_blocking() -> str:
            c = _find_container(name)
            if c is None:
                raise RuntimeError("容器不存在，需要先 ensure_user_container")
            c.reload()
            if c.status == "paused":
                c.unpause()
            elif c.status in ("exited", "created", "dead"):
                c.start()
            return c.status

        from_state = status.value
        await _run_blocking(_ensure_running_blocking)
        ok = await _wait_health(name, timeout=HEALTH_TIMEOUT_RESUME)
        if not ok:
            await _set_user_status(user_id, container_status=ContainerStatus.STOPPED)
            raise RuntimeError("容器恢复后健康探测失败")
        await _set_user_status(user_id, container_status=ContainerStatus.RUNNING)
        await _run_blocking(lambda: _connect_self_to_network(network))
        await _notify_agent_resumed(user_id)
        log.info("container_resumed", user_id=user_id, from_state=from_state)
        return ContainerStatus.RUNNING, {"container_name": name, "resumed": True}

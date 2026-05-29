"""孤儿 Docker 资源回收：软删用户、provision 失败、无 DB 用户的 apod 资源。"""

from __future__ import annotations

from typing import Any

from docker.errors import NotFound
from sqlalchemy import select

from ..db import ContainerStatus, ProvisionStatus, User, get_session
from ..logging import get_logger
from .docker_client import get_docker_client
from .lifecycle import _run_blocking, teardown_container
from .naming import container_name_for, network_name_for, volume_name_for

log = get_logger("cleanup")

_RESOURCE_PREFIXES = (
    "apod-user-",
    "apod-net-",
    "apod-data-",
)


def _user_id_from_resource_name(name: str) -> int | None:
    for prefix in _RESOURCE_PREFIXES:
        if name.startswith(prefix):
            try:
                return int(name[len(prefix) :])
            except ValueError:
                return None
    return None


def _collect_docker_user_ids() -> set[int]:
    client = get_docker_client()
    ids: set[int] = set()
    for container in client.containers.list(all=True):
        uid = _user_id_from_resource_name(container.name)
        if uid is not None:
            ids.add(uid)
    for network in client.networks.list():
        uid = _user_id_from_resource_name(network.name)
        if uid is not None:
            ids.add(uid)
    for volume in client.volumes.list():
        vol_name = volume.name
        if not vol_name:
            continue
        uid = _user_id_from_resource_name(vol_name)
        if uid is not None:
            ids.add(uid)
    return ids


def _has_docker_resources(user_id: int) -> bool:
    client = get_docker_client()
    name = container_name_for(user_id)
    network = network_name_for(user_id)
    volume = volume_name_for(user_id)
    try:
        client.containers.get(name)
        return True
    except NotFound:
        pass
    try:
        client.networks.get(network)
        return True
    except NotFound:
        pass
    try:
        client.volumes.get(volume)
        return True
    except NotFound:
        pass
    return False


async def _load_all_users() -> dict[int, User]:
    async with get_session() as session:
        rows = (await session.execute(select(User))).scalars().all()
    return {u.id: u for u in rows}


async def cleanup_deleted_users() -> int:
    """软删用户：清理 container/network/volume。"""
    async with get_session() as session:
        user_ids = (
            await session.execute(select(User.id).where(User.deleted_at.isnot(None)))
        ).scalars().all()

    cleaned = 0
    for user_id in user_ids:
        if not await _run_blocking(lambda uid=user_id: _has_docker_resources(uid)):
            continue
        try:
            await teardown_container(user_id, remove_volume=True)
            cleaned += 1
            log.info("orphan_cleanup_deleted_user", user_id=user_id)
        except Exception as exc:
            log.warning("orphan_cleanup_deleted_user_failed", user_id=user_id, error=str(exc))
    return cleaned


async def cleanup_failed_provision_users() -> int:
    """provision 失败且容器 absent：清理可能残留的 container/network（保留 volume 便于重试）。"""
    async with get_session() as session:
        user_ids = (
            await session.execute(
                select(User.id).where(
                    User.deleted_at.is_(None),
                    User.provision_status == ProvisionStatus.FAILED.value,
                    User.container_status == ContainerStatus.ABSENT.value,
                )
            )
        ).scalars().all()

    cleaned = 0
    for user_id in user_ids:
        if not await _run_blocking(lambda uid=user_id: _has_docker_resources(uid)):
            continue
        try:
            await teardown_container(user_id, remove_volume=False)
            cleaned += 1
            log.info("orphan_cleanup_failed_provision", user_id=user_id)
        except Exception as exc:
            log.warning("orphan_cleanup_failed_provision_error", user_id=user_id, error=str(exc))
    return cleaned


async def reconcile_orphan_docker_resources() -> int:
    """Docker 中存在 apod 资源但 DB 无对应有效用户时清理。"""
    users = await _load_all_users()
    docker_ids = await _run_blocking(_collect_docker_user_ids)

    cleaned = 0
    for user_id in sorted(docker_ids):
        user = users.get(user_id)
        remove_volume = False
        should_clean = False

        if user is None or user.deleted_at is not None:
            should_clean = True
            remove_volume = True
        elif (
            user.provision_status == ProvisionStatus.FAILED.value
            and user.container_status == ContainerStatus.ABSENT.value
        ):
            should_clean = True
            remove_volume = False

        if not should_clean:
            continue
        try:
            await teardown_container(user_id, remove_volume=remove_volume)
            cleaned += 1
            log.info(
                "orphan_cleanup_reconciled",
                user_id=user_id,
                remove_volume=remove_volume,
                reason="missing_user" if user is None else "deleted_or_failed",
            )
        except Exception as exc:
            log.warning("orphan_cleanup_reconcile_failed", user_id=user_id, error=str(exc))
    return cleaned


async def run_orphan_cleanup_once() -> dict[str, Any]:
    deleted = await cleanup_deleted_users()
    failed = await cleanup_failed_provision_users()
    reconciled = await reconcile_orphan_docker_resources()
    if deleted or failed or reconciled:
        log.info(
            "orphan_cleanup_done",
            deleted_users=deleted,
            failed_provision=failed,
            reconciled=reconciled,
        )
    return {
        "deleted_users": deleted,
        "failed_provision": failed,
        "reconciled": reconciled,
    }

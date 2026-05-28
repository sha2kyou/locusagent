"""Orchestrator：Docker 容器生命周期管理。"""

from .cleanup import run_orphan_cleanup_once
from .docker_client import get_docker_client
from .jobs import lifecycle_loop
from .lifecycle import (
    ensure_container_ready,
    ensure_user_container,
    pause_container,
    reattach_self_to_user_networks,
    reconcile_container_state,
    stop_container,
    teardown_container,
    touch_last_active,
)
from .naming import container_name_for, network_name_for, volume_name_for
from .seed import sync_shared_skills

__all__ = [
    "container_name_for",
    "ensure_container_ready",
    "ensure_user_container",
    "get_docker_client",
    "lifecycle_loop",
    "network_name_for",
    "pause_container",
    "reattach_self_to_user_networks",
    "reconcile_container_state",
    "run_orphan_cleanup_once",
    "stop_container",
    "sync_shared_skills",
    "teardown_container",
    "touch_last_active",
    "volume_name_for",
]

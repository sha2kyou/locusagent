"""容器/网络/volume 命名规范，集中管理避免散落硬编码。"""

from __future__ import annotations


def container_name_for(user_id: int) -> str:
    return f"apod-user-{user_id}"


def network_name_for(user_id: int) -> str:
    return f"apod-net-{user_id}"


def volume_name_for(user_id: int) -> str:
    return f"apod-data-{user_id}"

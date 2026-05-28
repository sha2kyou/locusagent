"""Docker SDK 客户端：通过 DOCKER_HOST（docker-socket-proxy）访问。

业务容器**严禁**直挂 docker.sock，所有 Docker API 调用走 proxy 的 TCP 端口。
"""

from __future__ import annotations

from functools import lru_cache

import docker
from docker.client import DockerClient

from ..config import get_settings


@lru_cache
def get_docker_client() -> DockerClient:
    settings = get_settings()
    return docker.DockerClient(base_url=settings.docker_host, timeout=30)

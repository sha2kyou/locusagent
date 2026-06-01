"""出站 URL 格式校验（无 DNS 解析）。

Jina 在远端抓取，Host 不直连目标站。DNS 校验在 TUN/代理环境下易误判（如 198.18.0.0/15 假 IP）。
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from fastapi import HTTPException

_BLOCKED_HOSTS = frozenset({"localhost", "metadata.google.internal"})


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def assert_extractable_http_url(url: str) -> None:
    raw = url.strip()
    if not raw.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="only http(s) urls allowed")
    host = (urlparse(raw).hostname or "").strip().lower()
    if not host:
        raise HTTPException(status_code=400, detail="invalid url host")
    if host in _BLOCKED_HOSTS or host.endswith(".localhost"):
        raise HTTPException(status_code=400, detail=f"blocked host: {host}")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if _is_blocked_ip(ip):
        raise HTTPException(status_code=400, detail=f"blocked non-public address: {host}")

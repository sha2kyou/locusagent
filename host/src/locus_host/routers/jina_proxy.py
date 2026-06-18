"""Jina Reader 提取代理：API Key 仅留在 Host。"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from ..auth.agent_internal import require_agent_internal
from ..config import get_settings
from ..internal_proxy_limits import enforce_internal_rate_limit
from ..logging import get_logger
from ..url_guard import assert_extractable_http_url
from ..usage import record_usage_event

router = APIRouter(prefix="/internal/jina", tags=["jina-proxy"])
log = get_logger("jina_proxy")

JINA_READER_URL = "https://r.jina.ai/"
USER_AGENT = "Mozilla/5.0 (compatible; AgentPodHost/0.1)"
TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0)
MAX_URLS = 5
MAX_CONTENT_CHARS = 12_000


class JinaExtractIn(BaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=MAX_URLS)


async def _extract_one(
    client: httpx.AsyncClient,
    *,
    url: str,
    api_key: str,
) -> tuple[dict[str, Any], int]:
    try:
        assert_extractable_http_url(url)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return {"url": url, "title": "", "content": "", "error": detail}, 0
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-Respond-With": "markdown",
        "User-Agent": USER_AGENT,
    }
    try:
        resp = await client.post(JINA_READER_URL, headers=headers, json={"url": url.strip()})
    except httpx.HTTPError as exc:
        return (
            {"url": url, "title": "", "content": "", "error": f"jina upstream unreachable: {exc}"},
            0,
        )
    try:
        data = resp.json()
    except Exception:
        return (
            {
                "url": url,
                "title": "",
                "content": "",
                "error": f"jina http {resp.status_code}: {(resp.text or '').strip()[:200]}",
            },
            0,
        )
    if resp.status_code >= 400 or not isinstance(data, dict) or data.get("code") != 200:
        message = str(data.get("readableMessage") or data.get("message") or f"jina http {resp.status_code}")
        return {"url": url, "title": "", "content": "", "error": message}, 0
    payload = data.get("data")
    if not isinstance(payload, dict):
        return {"url": url, "title": "", "content": "", "error": "jina returned empty data"}, 0
    title = str(payload.get("title") or "").strip()
    final_url = str(payload.get("url") or url).strip()
    content = str(payload.get("content") or "").strip()
    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS] + "\n…(truncated)"
    usage = payload.get("usage")
    tokens = 0
    if isinstance(usage, dict):
        tokens = int(usage.get("tokens") or 0)
    return {"url": final_url, "title": title, "content": content, "error": None}, tokens


@router.post("/extract")
async def jina_extract(
    payload: JinaExtractIn,
    _auth: None = Depends(require_agent_internal),
    x_workspace_id: str = Header(default="", alias="X-Workspace-Id"),
) -> dict:
    ws = (x_workspace_id or "").strip() or None
    await enforce_internal_rate_limit(bucket="jina", workspace_id=ws)
    settings = get_settings()
    api_key = settings.jina_api_key.strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="JINA_API_KEY not configured on host")

    urls = [u.strip() for u in payload.urls if u.strip()][:MAX_URLS]
    if not urls:
        raise HTTPException(status_code=400, detail="urls is required")

    out: list[dict[str, Any]] = []
    total_tokens = 0
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        pairs = await asyncio.gather(*[_extract_one(client, url=u, api_key=api_key) for u in urls])
    for item, tokens in pairs:
        out.append(item)
        total_tokens += tokens

    ok = sum(1 for item in out if not item.get("error"))
    log.info("jina_proxied", count=ok, total=len(out))
    await record_usage_event(
        workspace_id=ws,
        scenario="jina",
        model="jina-reader",
        api_calls=len(urls),
        total_tokens=total_tokens,
    )
    return {"results": out, "source": "jina"}

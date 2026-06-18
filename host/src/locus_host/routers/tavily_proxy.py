"""Tavily 搜索代理：API Key 仅留在 Host。"""

from __future__ import annotations

import re

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from ..auth.agent_internal import require_agent_internal
from ..config import get_settings
from ..internal_proxy_limits import enforce_internal_rate_limit
from ..usage import record_usage_event
from ..logging import get_logger

router = APIRouter(prefix="/internal/tavily", tags=["tavily-proxy"])
log = get_logger("tavily_proxy")

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
USER_AGENT = "Mozilla/5.0 (compatible; Locus AgentHost/0.1)"
TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)


class TavilySearchIn(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(default=5, ge=1, le=100)


@router.post("/search")
async def tavily_search(
    payload: TavilySearchIn,
    _auth: None = Depends(require_agent_internal),
    x_workspace_id: str = Header(default="", alias="X-Workspace-Id"),
) -> dict:
    ws = (x_workspace_id or "").strip() or None
    await enforce_internal_rate_limit(bucket="tavily", workspace_id=ws)
    settings = get_settings()
    api_key = settings.tavily_api_key.strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="TAVILY_API_KEY not configured on host")

    body = {
        "query": payload.query.strip(),
        "search_depth": "basic",
        "max_results": payload.limit,
        "include_answer": False,
        "include_raw_content": False,
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(TAVILY_SEARCH_URL, json=body, headers=headers)
    except httpx.HTTPError as exc:
        log.warning("tavily_upstream_failed", error=str(exc))
        raise HTTPException(status_code=502, detail="tavily upstream unreachable") from exc

    if resp.status_code != 200:
        log.warning("tavily_upstream_error", status=resp.status_code)
        raise HTTPException(status_code=502, detail=f"tavily http {resp.status_code}")

    data = resp.json()
    raw_results = data.get("results")
    if not isinstance(raw_results, list):
        return {"results": [], "source": "tavily"}

    out: list[dict[str, str]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(item.get("content") or "").strip()
        snippet = re.sub(r"\s+", " ", snippet)
        out.append({"title": title, "url": url, "snippet": snippet})
        if len(out) >= payload.limit:
            break

    log.info("tavily_proxied", count=len(out))
    await record_usage_event(
        workspace_id=ws,
        scenario="tavily",
        model="tavily-search",
        api_calls=1,
    )
    return {"results": out, "source": "tavily"}

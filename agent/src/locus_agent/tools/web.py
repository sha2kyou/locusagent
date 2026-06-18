"""网页类工具：web_search / web_extract。"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ..host_internal import HostInternalError, error_detail, internal_base_and_headers
from .base import Tool, ToolError, ToolResult, register_builtin

USER_AGENT = "Mozilla/5.0 (compatible; Locus AgentAgent/0.1)"
TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
JINA_TIMEOUT = httpx.Timeout(connect=5.0, read=65.0, write=5.0, pool=5.0)
TAVILY_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)


async def _ddg_search(query: str, top_k: int) -> list[dict[str, str]]:
    url = "https://html.duckduckgo.com/html/"
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.post(url, data={"q": query, "kl": "us-en"})
        if resp.status_code != 200:
            raise ToolError(f"duckduckgo http {resp.status_code}")
        html = resp.text

    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
        r'.*?<a[^>]+class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
        re.DOTALL,
    )
    results: list[dict[str, str]] = []
    for m in pattern.finditer(html):
        href = re.sub(r"/l/\?(?:.*?&)?uddg=([^&]+).*", lambda mm: mm.group(1), m.group("href"))
        href = str(httpx.URL(href)) if href.startswith("http") else m.group("href")
        title = re.sub(r"<.*?>", "", m.group("title")).strip()
        snippet = re.sub(r"<.*?>", "", m.group("snippet")).strip()
        results.append({"title": title, "url": href, "snippet": snippet})
        if len(results) >= top_k:
            break
    return results


async def _tavily_search_via_host(query: str, top_k: int) -> list[dict[str, str]] | None:
    """经 Host 代理搜索；不可用时返回 None 以降级 DuckDuckGo。"""
    try:
        base, headers = internal_base_and_headers()
    except HostInternalError:
        return None
    try:
        async with httpx.AsyncClient(timeout=TAVILY_TIMEOUT) as client:
            resp = await client.post(
                f"{base}/internal/tavily/search",
                headers=headers,
                json={"query": query, "limit": top_k},
            )
    except httpx.HTTPError:
        return None
    if resp.status_code in (502, 503):
        return None
    if resp.status_code >= 400:
        raise ToolError(error_detail(resp))
    data = resp.json()
    raw_results = data.get("results")
    if not isinstance(raw_results, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "title": str(item.get("title") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "snippet": str(item.get("snippet") or "").strip(),
            }
        )
        if len(out) >= top_k:
            break
    return out


async def _web_search(args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query", "")).strip()
    top_k = int(args.get("limit", args.get("top_k", 5)) or 5)
    top_k = max(1, min(100, top_k))
    if not query:
        raise ToolError("query is required")
    results = await _tavily_search_via_host(query, top_k)
    if results is not None:
        search_source = "tavily"
    else:
        results = await _ddg_search(query, top_k)
        search_source = "duckduckgo"
        from ..usage_report import schedule_api_call

        schedule_api_call(scenario="duckduckgo", model="duckduckgo-html", api_calls=1)
    if not results:
        return ToolResult(content="no results")
    lines = [f"{i+1}. {r['title']}\n   {r['url']}\n   {r['snippet']}" for i, r in enumerate(results)]
    return ToolResult(content="\n\n".join(lines), metadata={"results": results, "source": search_source})


async def _jina_extract_via_host(urls: list[str]) -> list[dict[str, Any]]:
    try:
        base, headers = internal_base_and_headers()
    except HostInternalError as exc:
        raise ToolError("host internal auth not configured") from exc
    async with httpx.AsyncClient(timeout=JINA_TIMEOUT) as client:
        resp = await client.post(
            f"{base}/internal/jina/extract",
            headers=headers,
            json={"urls": urls},
        )
    if resp.status_code >= 400:
        raise ToolError(error_detail(resp))
    data = resp.json()
    raw_results = data.get("results")
    if not isinstance(raw_results, list):
        raise ToolError("invalid jina extract response")
    return raw_results


async def _web_extract(args: dict[str, Any]) -> ToolResult:
    urls_arg = args.get("urls")
    if isinstance(urls_arg, list):
        urls = [str(u).strip() for u in urls_arg if str(u).strip()]
    else:
        single = str(args.get("url", "")).strip()
        urls = [single] if single else []
    if not urls:
        raise ToolError("urls is required")
    urls = urls[:5]
    out = await _jina_extract_via_host(urls)
    return ToolResult(content=json.dumps({"results": out}, ensure_ascii=False), metadata={"results": out, "source": "jina"})


register_builtin(
    Tool(
        name="web_search",
        description=(
            "Web search returning title/URL/snippet. Uses internal proxy first; falls back to DuckDuckGo."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 5},
            },
            "required": ["query"],
        },
        handler=_web_search,
    )
)

register_builtin(
    Tool(
        name="web_extract",
        description=(
            "Extract page body via Jina Reader (Markdown); returns results list"
            "(each with url/title/content/error). Max 5 URLs per call."
            "For more than 5, emit multiple web_extract tool_calls in parallel in the same turn,"
            "Do not wait one URL per ReAct turn."
        ),
        parameters={
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 5,
                    "description": "URLs to extract (max 5)",
                }
            },
            "required": ["urls"],
        },
        handler=_web_extract,
    )
)

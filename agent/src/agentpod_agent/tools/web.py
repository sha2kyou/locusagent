"""网页类工具：web_search / web_extract。

P0 简化：
- web_search：默认 DuckDuckGo HTML 端点；如配置 BRAVE_API_KEY 走 Brave Search API。
- web_extract：httpx 拉 HTML，用 stdlib html.parser 提纯文本（保留段落分隔）。
"""

from __future__ import annotations

import os
import re
from html.parser import HTMLParser
from typing import Any

import httpx

from .base import Tool, ToolError, ToolResult, register_builtin

USER_AGENT = "Mozilla/5.0 (compatible; AgentPodAgent/0.1)"
TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
MAX_HTML_BYTES = 1 * 1024 * 1024
MAX_TEXT_CHARS = 12_000


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


async def _brave_search(query: str, top_k: int, key: str) -> list[dict[str, str]]:
    url = "https://api.search.brave.com/res/v1/web/search"
    params = {"q": query, "count": str(top_k), "country": "us"}
    headers = {"X-Subscription-Token": key, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as client:
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            raise ToolError(f"brave http {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
    items = (data.get("web") or {}).get("results") or []
    return [
        {
            "title": i.get("title", ""),
            "url": i.get("url", ""),
            "snippet": i.get("description", ""),
        }
        for i in items[:top_k]
    ]


async def _web_search(args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query", "")).strip()
    top_k = int(args.get("top_k", 5) or 5)
    if not query:
        raise ToolError("query is required")
    brave_key = os.environ.get("BRAVE_API_KEY")
    if brave_key:
        results = await _brave_search(query, top_k, brave_key)
    else:
        results = await _ddg_search(query, top_k)
    if not results:
        return ToolResult(content="no results")
    lines = [f"{i+1}. {r['title']}\n   {r['url']}\n   {r['snippet']}" for i, r in enumerate(results)]
    return ToolResult(content="\n\n".join(lines), metadata={"results": results})


class _TextExtractor(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "head", "meta", "link"}
    BLOCK_TAGS = {"p", "br", "li", "tr", "div", "section", "article", "h1", "h2", "h3", "h4", "h5"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._buf: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, _attrs: list) -> None:
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self.BLOCK_TAGS:
            self._buf.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in self.BLOCK_TAGS:
            self._buf.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._buf.append(data)

    def text(self) -> str:
        raw = "".join(self._buf)
        cleaned = re.sub(r"[ \t]+", " ", raw)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()


async def _web_extract(args: dict[str, Any]) -> ToolResult:
    url = str(args.get("url", "")).strip()
    if not url or not url.startswith(("http://", "https://")):
        raise ToolError("url must start with http(s)://")
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.get(url, follow_redirects=True)
    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype.lower():
        raise ToolError(f"non-HTML content-type: {ctype}")
    if len(resp.content) > MAX_HTML_BYTES:
        raise ToolError(f"page too large: {len(resp.content)} bytes")
    parser = _TextExtractor()
    parser.feed(resp.text)
    text = parser.text()
    truncated = text[:MAX_TEXT_CHARS]
    note = "\n…(truncated)" if len(text) > MAX_TEXT_CHARS else ""
    return ToolResult(
        content=f"# {url}\n\n{truncated}{note}",
        metadata={"final_url": str(resp.url), "length": len(text)},
    )


register_builtin(
    Tool(
        name="web_search",
        description="网页搜索（DuckDuckGo 默认；配置 BRAVE_API_KEY 后走 Brave）。",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
            },
            "required": ["query"],
        },
        handler=_web_search,
    )
)

register_builtin(
    Tool(
        name="web_extract",
        description="提取网页正文为纯文本。",
        parameters={
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
        handler=_web_extract,
    )
)

"""网页类工具：web_search / web_extract。"""

from __future__ import annotations

import asyncio
import json
import ipaddress
import os
import re
import socket
from html.parser import HTMLParser
from typing import Any

import httpx

from .base import Tool, ToolError, ToolResult, register_builtin

USER_AGENT = "Mozilla/5.0 (compatible; AgentPodAgent/0.1)"
TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
MAX_HTML_BYTES = 1 * 1024 * 1024
MAX_TEXT_CHARS = 12_000
MAX_REDIRECTS = 5
TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """拒绝非公网地址：私有/回环/链路本地/保留/多播/未指定（含等价 IPv6 段）。"""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def _assert_public_host(host: str) -> None:
    """解析主机的全部 IP，任一落入非公网段即拒绝（防 SSRF / 云元数据探测）。"""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ToolError(f"cannot resolve host: {host}") from exc
    addrs = {info[4][0] for info in infos}
    if not addrs:
        raise ToolError(f"cannot resolve host: {host}")
    for addr in addrs:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError as exc:
            raise ToolError(f"invalid resolved address: {addr}") from exc
        if _is_blocked_ip(ip):
            raise ToolError(f"blocked non-public address for host {host}: {addr}")


async def _guarded_get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """逐跳校验后 GET：禁用自动重定向，对每一跳目标重新解析并校验，防重定向绕过。"""
    current = httpx.URL(url)
    for _ in range(MAX_REDIRECTS + 1):
        if current.scheme not in ("http", "https"):
            raise ToolError("only http(s) urls allowed")
        host = current.host
        if not host:
            raise ToolError("invalid url host")
        await _assert_public_host(host)
        resp = await client.get(current)
        if resp.is_redirect and "location" in resp.headers:
            current = current.join(resp.headers["location"])
            continue
        return resp
    raise ToolError("too many redirects")


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


async def _tavily_search(query: str, top_k: int, api_key: str) -> list[dict[str, str]]:
    payload = {
        "query": query,
        "search_depth": "basic",
        "max_results": top_k,
        "include_answer": False,
        "include_raw_content": False,
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as client:
        resp = await client.post(TAVILY_SEARCH_URL, json=payload)
    if resp.status_code != 200:
        raise ToolError(f"tavily http {resp.status_code}")
    data = resp.json()
    raw_results = data.get("results")
    if not isinstance(raw_results, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(item.get("content") or "").strip()
        snippet = re.sub(r"\s+", " ", snippet)
        out.append({"title": title, "url": url, "snippet": snippet})
        if len(out) >= top_k:
            break
    return out


async def _web_search(args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query", "")).strip()
    top_k = int(args.get("limit", args.get("top_k", 5)) or 5)
    top_k = max(1, min(100, top_k))
    if not query:
        raise ToolError("query is required")
    tavily_api_key = str(os.getenv("TAVILY_API_KEY", "")).strip()
    if tavily_api_key:
        results = await _tavily_search(query, top_k, tavily_api_key)
        search_source = "tavily"
    else:
        results = await _ddg_search(query, top_k)
        search_source = "duckduckgo"
    if not results:
        return ToolResult(content="no results")
    lines = [f"{i+1}. {r['title']}\n   {r['url']}\n   {r['snippet']}" for i, r in enumerate(results)]
    return ToolResult(content="\n\n".join(lines), metadata={"results": results, "source": search_source})


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
    urls_arg = args.get("urls")
    if isinstance(urls_arg, list):
        urls = [str(u).strip() for u in urls_arg if str(u).strip()]
    else:
        single = str(args.get("url", "")).strip()
        urls = [single] if single else []
    if not urls:
        raise ToolError("urls is required")
    urls = urls[:5]
    out: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=False
    ) as client:
        for url in urls:
            if not url.startswith(("http://", "https://")):
                out.append({"url": url, "title": "", "content": "", "error": "invalid url scheme"})
                continue
            try:
                resp = await _guarded_get(client, url)
                ctype = resp.headers.get("content-type", "")
                if "html" not in ctype.lower():
                    out.append({"url": url, "title": "", "content": "", "error": f"non-HTML content-type: {ctype}"})
                    continue
                if len(resp.content) > MAX_HTML_BYTES:
                    out.append({"url": url, "title": "", "content": "", "error": f"page too large: {len(resp.content)} bytes"})
                    continue
                parser = _TextExtractor()
                parser.feed(resp.text)
                text = parser.text()
                title_m = re.search(r"<title[^>]*>(.*?)</title>", resp.text, flags=re.IGNORECASE | re.DOTALL)
                title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else ""
                truncated = text[:MAX_TEXT_CHARS]
                if len(text) > MAX_TEXT_CHARS:
                    truncated += "\n…(truncated)"
                out.append({"url": str(resp.url), "title": title, "content": truncated, "error": None})
            except Exception as exc:
                out.append({"url": url, "title": "", "content": "", "error": str(exc)})
    return ToolResult(content=json.dumps({"results": out}, ensure_ascii=False), metadata={"results": out})


register_builtin(
    Tool(
        name="web_search",
        description=(
            "网页搜索，返回标题/URL/摘要。配置了 TAVILY_API_KEY 时使用 Tavily；未配置时使用 DuckDuckGo。"
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
            "提取网页 URL 内容，返回 results 列表（每项含 url/title/content/error）。"
            "支持最多 5 个 URL。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 5,
                    "description": "要提取的 URL 列表（最多 5 个）",
                }
            },
            "required": ["urls"],
        },
        handler=_web_extract,
    )
)

"""Tool A — Internet capability.

Search engines:
  * Tavily (preferred) when TAVILY_API_KEY is set.
  * DuckDuckGo (ddgs) as a no-key fallback.

Page fetching uses httpx + BeautifulSoup with disk caching at data/cache/.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup

from mcp_server.logging_setup import setup_logging, tool_call_log, tool_result_log
from mcp_server.schemas import PageContent, SearchHit

logger = setup_logging("competitor_mcp.web")

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HTTP_TIMEOUT = 20.0
MAX_PAGE_BYTES = 1_500_000

PRICING_RX = re.compile(
    r"(?:\$|USD|EUR|INR|₹|€|£)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:/|per)\s?(?:mo|month|yr|year|user|seat))?"
    r"|free\s+(?:tier|plan|trial)|enterprise\s+pricing|contact\s+sales",
    re.IGNORECASE,
)
FEATURE_KEYWORDS = (
    "ai",
    "3d",
    "2d",
    "visualiz",
    "render",
    "augmented reality",
    "ar",
    "vr",
    "virtual reality",
    "room",
    "tile",
    "wall",
    "floor",
    "designer",
    "homeowner",
    "retailer",
    "catalog",
    "computer vision",
    "generative",
    "upload",
    "photo",
    "preview",
    "mockup",
    "cloud",
    "api",
    "integration",
    "mobile app",
    "web app",
)


def _cache_key(url: str) -> Path:
    h = hashlib.sha256(url.encode()).hexdigest()[:24]
    return CACHE_DIR / f"{h}.json"


def _load_cached(url: str) -> PageContent | None:
    p = _cache_key(url)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        data["cached"] = True
        return PageContent(**data)
    except Exception as exc:  # pragma: no cover
        logger.warning("Cache read failed for %s: %s", url, exc)
        return None


def _store_cached(content: PageContent) -> None:
    try:
        _cache_key(content.url).write_text(content.model_dump_json())
    except Exception as exc:  # pragma: no cover
        logger.warning("Cache write failed: %s", exc)


def search_competitors(
    product_name: str,
    product_description: str,
    category: str,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Find candidate competitors. Returns list of {name, url, snippet, source}."""
    tool_call_log(
        logger,
        "search_competitors",
        product=product_name,
        category=category,
        max_results=max_results,
    )

    queries = [
        f"{product_name} competitors",
        f"alternatives to {product_name}",
        f"best {category} tools 2025",
        f"{category} {product_description[:60]}",
    ]

    hits: list[SearchHit] = []
    seen_urls: set[str] = set()
    tavily_key = os.environ.get("TAVILY_API_KEY")

    if tavily_key:
        try:
            from tavily import TavilyClient

            client = TavilyClient(api_key=tavily_key)
            for q in queries:
                resp = client.search(query=q, max_results=max(3, max_results // len(queries)))
                for r in resp.get("results", []):
                    url = r.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    hits.append(
                        SearchHit(
                            name=r.get("title", url),
                            url=url,
                            snippet=r.get("content", "")[:400],
                            source="tavily",
                        )
                    )
                if len(hits) >= max_results:
                    break
        except Exception as exc:
            logger.warning("Tavily search failed, falling back to DDG: %s", exc)

    if len(hits) < max_results:
        try:
            from ddgs import DDGS

            with DDGS() as ddg:
                for q in queries:
                    for r in ddg.text(q, max_results=max(3, max_results // len(queries))):
                        url = r.get("href") or r.get("url") or ""
                        if not url or url in seen_urls:
                            continue
                        seen_urls.add(url)
                        hits.append(
                            SearchHit(
                                name=r.get("title", url),
                                url=url,
                                snippet=r.get("body", "")[:400],
                                source="duckduckgo",
                            )
                        )
                    if len(hits) >= max_results:
                        break
        except Exception as exc:
            logger.error("DuckDuckGo search failed: %s", exc)

    hits = hits[:max_results]
    tool_result_log(logger, "search_competitors", ok=bool(hits), count=len(hits))
    return [h.model_dump() for h in hits]


def fetch_competitor_page(url: str, force_refresh: bool = False) -> dict[str, Any]:
    """Fetch + clean a competitor page. Returns PageContent dict.

    Caches in data/cache/. On 404/5xx, raises with a useful message so the
    agent can pick a different source.
    """
    tool_call_log(logger, "fetch_competitor_page", url=url, force_refresh=force_refresh)

    if not force_refresh:
        cached = _load_cached(url)
        if cached:
            tool_result_log(logger, "fetch_competitor_page", ok=True, cached=True, url=url)
            return cached.model_dump()

    try:
        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            html = resp.text[:MAX_PAGE_BYTES]
    except httpx.HTTPStatusError as exc:
        msg = f"HTTP {exc.response.status_code} for {url}; try a different source."
        tool_result_log(logger, "fetch_competitor_page", ok=False, url=url, error=msg)
        raise RuntimeError(msg) from exc
    except httpx.HTTPError as exc:
        msg = f"Network error fetching {url}: {exc}; try a different source."
        tool_result_log(logger, "fetch_competitor_page", ok=False, url=url, error=msg)
        raise RuntimeError(msg) from exc

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    title = (soup.title.get_text(strip=True) if soup.title else url)[:200]
    text = " ".join(soup.get_text(" ").split())[:6000]

    pricing_hints = sorted({m.strip() for m in PRICING_RX.findall(html)})[:8]
    lower = text.lower()
    feature_mentions = sorted({kw for kw in FEATURE_KEYWORDS if kw in lower})

    content = PageContent(
        url=url,
        title=title,
        cleaned_text=text,
        pricing_hints=pricing_hints,
        feature_mentions=feature_mentions,
        cached=False,
    )
    _store_cached(content)
    tool_result_log(logger, "fetch_competitor_page", ok=True, cached=False, url=url, chars=len(text))
    return content.model_dump()

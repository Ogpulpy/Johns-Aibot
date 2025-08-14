import asyncio
from typing import Any, Dict, List

import httpx
from duckduckgo_search import DDGS
import trafilatura

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0 Safari/537.36"
    )
}


def _ddg_text(query: str, max_results: int, backend: str | None = None) -> List[Dict[str, Any]]:
    """Call DDG text search with optional backend and normalize results."""
    results: List[Dict[str, Any]] = []
    kwargs: Dict[str, Any] = {
        "max_results": max_results,
        "region": "wt-wt",
        "safesearch": "moderate",
    }
    if backend:
        kwargs["backend"] = backend
    with DDGS() as ddgs:
        for r in ddgs.text(query, **kwargs):
            url = r.get("href")
            if not url:
                continue
            title = r.get("title") or "Untitled"
            results.append({"title": title, "url": url})
    return results


def search_web(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search DuckDuckGo with resilient fallbacks to avoid rate limits."""
    # Try API backend first
    for backend in [None, "html", "lite"]:
        try:
            results = _ddg_text(query, max_results=max_results, backend=backend)
            if results:
                return results
        except Exception:
            # Try next backend on any failure
            continue
    return []


async def fetch_url_text(client: httpx.AsyncClient, url: str) -> str:
    try:
        resp = await client.get(url, timeout=15)
        resp.raise_for_status()
        html = resp.text
        text = trafilatura.extract(html, url=url, favor_precision=True)
        return text or ""
    except Exception:
        return ""


async def wikipedia_fallback(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Try Wikipedia search and summaries as a lightweight fallback."""
    docs: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, follow_redirects=True) as client:
        # 1) Try legacy opensearch
        try:
            params = {
                "action": "opensearch",
                "search": query,
                "limit": str(limit),
                "namespace": "0",
                "format": "json",
            }
            r = await client.get("https://en.wikipedia.org/w/api.php", params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            titles = data[1] if len(data) > 1 else []
            urls = data[3] if len(data) > 3 else []
            for i, title in enumerate(titles):
                url = urls[i] if i < len(urls) else f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                try:
                    s = await client.get(
                        f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}",
                        timeout=10,
                    )
                    if s.status_code == 200:
                        extract = (s.json().get("extract") or "").strip()
                    else:
                        extract = ""
                except Exception:
                    extract = ""
                if extract:
                    docs.append({"title": title, "url": url, "text": extract})
        except Exception:
            pass

        if docs:
            return docs

        # 2) Try REST v1 search/page as a fallback
        try:
            r = await client.get(
                "https://en.wikipedia.org/w/rest.php/v1/search/page",
                params={"q": query, "limit": str(limit)},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            pages = (data or {}).get("pages") or []
            for p in pages:
                key = p.get("key") or p.get("title")
                title = p.get("title") or key or "Untitled"
                if not key:
                    continue
                url = f"https://en.wikipedia.org/wiki/{key}"
                try:
                    s = await client.get(
                        f"https://en.wikipedia.org/api/rest_v1/page/summary/{key}",
                        timeout=10,
                    )
                    if s.status_code == 200:
                        extract = (s.json().get("extract") or "").strip()
                    else:
                        extract = ""
                except Exception:
                    extract = ""
                if extract:
                    docs.append({"title": title, "url": url, "text": extract})
        except Exception:
            return []
    return docs


async def search_and_fetch(query: str, max_results: int = 5, max_concurrent: int = 5) -> List[Dict[str, Any]]:
    """Search the web and fetch contents of results concurrently."""
    results = search_web(query, max_results=max_results)
    if not results:
        # Try Wikipedia summaries as a final fallback
        wiki_docs = await wikipedia_fallback(query, limit=max_results)
        if wiki_docs:
            return wiki_docs[:max_results]
        return []

    semaphore = asyncio.Semaphore(max_concurrent)

    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, follow_redirects=True) as client:
        async def _task(item: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                text = await fetch_url_text(client, item["url"])
                return {"title": item["title"], "url": item["url"], "text": text}

        docs = await asyncio.gather(*[_task(r) for r in results])

    # Filter out empty texts and keep top N non-empty
    filtered = [d for d in docs if d.get("text")]
    return filtered[:max_results]
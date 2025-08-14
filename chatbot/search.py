import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from duckduckgo_search import DDGS
import trafilatura
from langdetect import detect as detect_lang

from cache import get_cache

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0 Safari/537.36"
    )
}

SEARCH_TTL_SECONDS = 60 * 60 * 12  # 12h
FETCH_TTL_SECONDS = 60 * 60 * 24   # 24h


def _ddg_text(query: str, max_results: int, backend: Optional[str] = None, region: str = "wt-wt") -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    kwargs: Dict[str, Any] = {
        "max_results": max_results,
        "region": region,
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


def _region_for_lang(lang: str) -> str:
    lang = (lang or "en").lower()
    mapping = {
        "en": "us-en",
        "es": "es-es",
        "fr": "fr-fr",
        "de": "de-de",
        "it": "it-it",
        "pt": "pt-pt",
        "zh": "cn-zh",
        "ja": "jp-ja",
        "ko": "kr-ko",
    }
    return mapping.get(lang, "wt-wt")


def search_duckduckgo(query: str, max_results: int = 5, lang: str = "en") -> List[Dict[str, Any]]:
    cache = get_cache()
    cache_key = ("ddg", query, max_results, lang)
    cached = cache.get(cache_key)
    if cached:
        return cached
    region = _region_for_lang(lang)
    for backend in [None, "html", "lite"]:
        try:
            results = _ddg_text(query, max_results=max_results, backend=backend, region=region)
            if results:
                cache.set(cache_key, results, expire=SEARCH_TTL_SECONDS)
                return results
        except Exception:
            continue
    cache.set(cache_key, [], expire=SEARCH_TTL_SECONDS)
    return []


async def wikipedia_fallback(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    cache = get_cache()
    cache_key = ("wikipedia", query, limit)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, follow_redirects=True) as client:
        # opensearch
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
                    extract = (s.json().get("extract") or "").strip() if s.status_code == 200 else ""
                except Exception:
                    extract = ""
                if extract:
                    docs.append({"title": title, "url": url, "text": extract})
        except Exception:
            pass
        if not docs:
            # REST v1 search/page
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
                        extract = (s.json().get("extract") or "").strip() if s.status_code == 200 else ""
                    except Exception:
                        extract = ""
                    if extract:
                        docs.append({"title": title, "url": url, "text": extract})
            except Exception:
                pass
    cache.set(cache_key, docs, expire=SEARCH_TTL_SECONDS)
    return docs


async def search_stackoverflow(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    cache = get_cache()
    cache_key = ("so", query, max_results)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    items: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(headers=DEFAULT_HEADERS, follow_redirects=True) as client:
            r = await client.get(
                "https://api.stackexchange.com/2.3/search/advanced",
                params={
                    "order": "desc",
                    "sort": "relevance",
                    "q": query,
                    "site": "stackoverflow",
                    "pagesize": str(max_results),
                },
                timeout=10,
            )
            if r.status_code == 200:
                for it in (r.json().get("items") or []):
                    title = it.get("title") or "StackOverflow Question"
                    url = it.get("link")
                    if url:
                        items.append({"title": title, "url": url})
    except Exception:
        pass
    cache.set(cache_key, items, expire=SEARCH_TTL_SECONDS)
    return items


async def search_mdn(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    cache = get_cache()
    cache_key = ("mdn", query, max_results)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    items: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(headers=DEFAULT_HEADERS, follow_redirects=True) as client:
            r = await client.get(
                "https://developer.mozilla.org/api/v1/search",
                params={"q": query, "locale": "en-US", "highlight": "false", "size": str(max_results)},
                timeout=10,
            )
            if r.status_code == 200:
                for doc in (r.json().get("documents") or [])[:max_results]:
                    title = doc.get("title") or "MDN"
                    url = doc.get("mdn_url")
                    if url and not url.startswith("http"):
                        url = f"https://developer.mozilla.org{url}"
                    if url:
                        items.append({"title": title, "url": url})
    except Exception:
        pass
    cache.set(cache_key, items, expire=SEARCH_TTL_SECONDS)
    return items


async def search_github_repos(query: str, max_results: int = 2) -> List[Dict[str, Any]]:
    cache = get_cache()
    cache_key = ("gh", query, max_results)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    items: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(headers=DEFAULT_HEADERS, follow_redirects=True) as client:
            r = await client.get(
                "https://api.github.com/search/repositories",
                params={"q": query, "sort": "stars", "order": "desc", "per_page": str(max_results)},
                timeout=10,
            )
            if r.status_code == 200:
                for repo in (r.json().get("items") or [])[:max_results]:
                    title = repo.get("full_name") or repo.get("name") or "GitHub Repo"
                    url = repo.get("html_url")
                    if url:
                        items.append({"title": title, "url": url})
    except Exception:
        pass
    cache.set(cache_key, items, expire=SEARCH_TTL_SECONDS)
    return items


def _shingle_set(text: str, size: int = 3) -> set:
    tokens = [t for t in (text or "").lower().split() if t]
    return {" ".join(tokens[i:i+size]) for i in range(max(0, len(tokens) - size + 1))}


def deduplicate_docs(docs: List[Dict[str, Any]], threshold: float = 0.9) -> List[Dict[str, Any]]:
    seen_urls = set()
    kept: List[Dict[str, Any]] = []
    shingle_sets: List[set] = []
    for d in docs:
        url = d.get("url")
        if url and url in seen_urls:
            continue
        text = (d.get("text") or "").strip()
        if text:
            sset = _shingle_set(text)
            is_dup = False
            for other in shingle_sets:
                inter = len(sset & other)
                union = len(sset | other) or 1
                if inter / union >= threshold:
                    is_dup = True
                    break
            if is_dup:
                continue
            shingle_sets.append(sset)
        kept.append(d)
        if url:
            seen_urls.add(url)
    return kept


async def fetch_url_text(client: httpx.AsyncClient, url: str) -> str:
    cache = get_cache()
    cache_key = ("fetch", url)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        resp = await client.get(url, timeout=15)
        resp.raise_for_status()
        html = resp.text
        text = trafilatura.extract(html, url=url, favor_precision=True)
        text = text or ""
    except Exception:
        text = ""
    cache.set(cache_key, text, expire=FETCH_TTL_SECONDS)
    return text


async def aggregate_search(query: str, max_results: int = 6) -> List[Dict[str, Any]]:
    lang = "en"
    try:
        lang = detect_lang(query)
    except Exception:
        pass
    primary = search_duckduckgo(query, max_results=max_results, lang=lang)
    extras: List[Dict[str, Any]] = []
    # Launch extra sources concurrently
    tasks = [
        wikipedia_fallback(query, limit=3),
        search_stackoverflow(query, max_results=2),
        search_mdn(query, max_results=2),
        search_github_repos(query, max_results=1),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, list):
            extras.extend(r)
    # Prefer primary, then extras, dedup by URL
    combined: List[Dict[str, Any]] = []
    seen = set()
    for item in primary + extras:
        url = item.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        combined.append({"title": item.get("title") or "Untitled", "url": url, "text": item.get("text", "")})
    return combined[:max_results]


async def search_and_fetch(query: str, max_results: int = 5, max_concurrent: int = 5, budget_seconds: float = 7.0) -> List[Dict[str, Any]]:
    start = time.monotonic()
    items = await aggregate_search(query, max_results=max_results)
    # If some already have text (e.g., wikipedia), keep them
    docs: List[Dict[str, Any]] = [d for d in items if (d.get("text") or "").strip()]
    to_fetch = [d for d in items if not (d.get("text") or "").strip()]
    if not to_fetch:
        return deduplicate_docs(docs)[:max_results]

    semaphore = asyncio.Semaphore(max_concurrent)
    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, follow_redirects=True) as client:
        async def _task(item: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                text = await fetch_url_text(client, item["url"])
                return {"title": item["title"], "url": item["url"], "text": text}
        remaining = max(0.1, budget_seconds - (time.monotonic() - start))
        tasks = [asyncio.create_task(_task(r)) for r in to_fetch]
        done, pending = await asyncio.wait(tasks, timeout=remaining)
        fetched = [t.result() for t in done if not t.cancelled() and not t.exception()]
        for p in pending:
            p.cancel()
    all_docs = docs + fetched
    filtered = [d for d in all_docs if (d.get("text") or "").strip()]
    return deduplicate_docs(filtered)[:max_results]
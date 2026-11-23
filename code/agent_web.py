# -*- coding: utf-8 -*-
"""Optional web search for OpenECRS.

Web results are deliberately kept separate from the evidence base: they are
useful for *current* news / competitors / regulation, but they are not part of
the audited dataset and must be labelled as external in answers.

Provider: Bing HTML results (no API key required). The query is sent to Bing.
"""
from __future__ import annotations

import base64
import html
import re
import urllib.parse
import urllib.request

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

SETLANG = {"en": "en", "zh": "zh-Hans", "ja": "ja", "es": "es"}


class WebSearchError(RuntimeError):
    pass


def _clean(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(re.sub(r"\s+", " ", value)).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", value)


def _real_url(href: str) -> str:
    href = html.unescape(href or "")
    try:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        encoded = (query.get("u") or [""])[0]
        if encoded.startswith("a1"):
            padded = encoded[2:] + "=" * (-len(encoded[2:]) % 4)
            return base64.urlsafe_b64decode(padded).decode("utf-8", "ignore")
    except Exception:
        pass
    return href


def parse_results(page: str, max_results: int = 5) -> list[dict]:
    """Parse Bing's HTML result list (kept small and deterministic)."""
    results = []
    seen = set()
    for block in re.split(r'<li class="b_algo"', page or "")[1:]:
        title_match = re.search(r"<h2[^>]*>\s*<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", block, re.S)
        if not title_match:
            continue
        title = _clean(title_match.group(2))
        snippet_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        snippet = _clean(snippet_match.group(1)) if snippet_match else ""
        url = _real_url(title_match.group(1))
        if not title or not url.startswith(("http://", "https://")):
            continue
        key = urllib.parse.urlparse(url).netloc.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append({"title": title[:240], "url": url[:500], "snippet": snippet[:360], "source": "web"})
        if len(results) >= max_results:
            break
    return results


def search(query: str, max_results: int = 5, lang: str = "en", timeout: int = 20) -> dict:
    query = (query or "").strip()
    if not query:
        raise WebSearchError("Empty query")
    url = ("https://www.bing.com/search?q=" + urllib.parse.quote(query)
           + "&count=" + str(max(1, min(10, int(max_results))))
           + "&setlang=" + SETLANG.get(lang, "en"))
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept-Language": {"zh": "zh-CN,zh;q=0.9,en;q=0.8", "ja": "ja,en;q=0.8",
                            "es": "es,en;q=0.8"}.get(lang, "en-US,en;q=0.9"),
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            page = response.read().decode("utf-8", "ignore")
    except Exception as exc:
        raise WebSearchError("Web search is unavailable: " + str(exc)[:160])
    results = parse_results(page, max_results)
    if not results:
        raise WebSearchError("Web search returned no results (the provider may be rate-limiting).")
    return {
        "query": query,
        "provider": "bing",
        "results": results,
        "note": "External web results, not part of the audited evidence base. Verify before citing.",
    }

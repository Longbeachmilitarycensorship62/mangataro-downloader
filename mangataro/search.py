"""MangaTaro search API."""

import json
import ssl
from urllib.request import Request, urlopen

from mangataro.models import SearchResult, SearchResponse

BASE = "https://mangataro.org"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_ctx = ssl.create_default_context()


def search_manga(query: str, limit: int = 24) -> SearchResponse:
    """Search manga by name.

    Returns SearchResponse with results list.
    """
    url = f"{BASE}/auth/search"
    body = json.dumps({"query": query, "limit": limit}).encode()
    req = Request(url, data=body, headers={
        "User-Agent": UA,
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    with urlopen(req, context=_ctx) as r:
        data = json.loads(r.read())

    results = [SearchResult(**m) for m in data.get("results", [])]
    return SearchResponse(
        success=data.get("success", True),
        count=data.get("count", len(results)),
        query=data.get("query", query),
        results=results,
    )

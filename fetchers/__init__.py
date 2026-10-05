"""The source registry, plus `run_all()`, which fetches every source in parallel.

To add a source, add one `Source(...)` line to SOURCES. Each `fetch`
function only has to return a list of Items; timing, error handling,
de-duplication, sorting and the 10-item cap all happen here, once.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from typing import Callable

import requests

from .anthropic_news import fetch_anthropic_news
from .common import TIMEOUT_SECONDS, Item, SourceResult
from .rss import fetch_feed
from .social import fetch_linkedin, fetch_x

MAX_ITEMS_PER_SOURCE = 10
# Hard ceiling for the whole pull, so one slow site can't hold the page past ~10s.
DEADLINE_SECONDS = 8.5

YOUTUBE_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"


@dataclass(frozen=True)
class Source:
    """One place we pull updates from."""

    source_id: str
    company: str
    source_type: str
    fetch: Callable[..., list[Item]]  # called as fetch(company=..., source_type=...)
    bonus: bool = False


SOURCES: list[Source] = [
    Source("openai-news", "OpenAI", "Blog RSS",
           partial(fetch_feed, "https://openai.com/news/rss.xml")),
    Source("anthropic-news", "Anthropic", "Web scrape",
           fetch_anthropic_news),
    # Channel IDs come from the canonical <link> on each channel's page
    # (youtube.com/@anthropic-ai and youtube.com/user/QualtricsSoftware).
    Source("anthropic-youtube", "Anthropic", "YouTube",
           partial(fetch_feed, YOUTUBE_FEED.format("UCrDwWp7EBBv4NwvScIpBDOA"))),
    # Qualtrics has no blog RSS feed (checked: /blog/feed/ and variants are 404),
    # so its YouTube channel is the primary source.
    Source("qualtrics-youtube", "Qualtrics", "YouTube",
           partial(fetch_feed, YOUTUBE_FEED.format("UCYZGKyf7DygMlsU0sFQ0AkQ"))),
    Source("anthropic-linkedin", "Anthropic", "LinkedIn", fetch_linkedin, bonus=True),
    Source("anthropic-x", "Anthropic", "X", fetch_x, bonus=True),
]

COMPANIES: list[str] = list(dict.fromkeys(s.company for s in SOURCES))


# ---- Running sources -------------------------------------------------------

def run_all() -> dict:
    """Fetch every source in parallel and merge the results into one feed."""
    started = time.perf_counter()
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Each source runs in its own thread: the work is waiting on the network,
    # so threads overlap those waits and the total time is roughly that of the
    # slowest source rather than the sum of all of them.
    pool = ThreadPoolExecutor(max_workers=len(SOURCES))
    futures = {source: pool.submit(run_source, source) for source in SOURCES}
    wait(futures.values(), timeout=DEADLINE_SECONDS)
    pool.shutdown(wait=False, cancel_futures=True)  # don't wait on stragglers

    results = [
        future.result() if future.done() else _deadline_result(source)
        for source, future in futures.items()  # keeps registry order for the status panel
    ]

    return {
        "fetched_at": fetched_at,
        "total_ms": _ms_since(started),
        "sources": results,
        "items": newest_first(dedupe_by_url(item for r in results for item in r["items"])),
    }


def run_source(source: Source) -> SourceResult:
    """Run one fetcher. Never raises: a failure becomes this source's status row."""
    started = time.perf_counter()
    try:
        items = source.fetch(company=source.company, source_type=source.source_type)
        items = newest_first(dedupe_by_url(items))[:MAX_ITEMS_PER_SOURCE]
        if not items:
            raise ValueError("Request succeeded but returned no items")
        status, error = "ok", None
    except Exception as exc:  # deliberately broad: any failure is reported, not raised
        items, status, error = [], "error", describe_error(exc)

    return _result(source, status, error, items, _ms_since(started))


# ---- Helpers ---------------------------------------------------------------

def newest_first(items: list[Item]) -> list[Item]:
    """Sort newest first; items without a date go to the bottom.

    Dates are ISO-8601 UTC strings in one fixed format, so sorting them as text
    is the same as sorting chronologically. A missing date becomes "", which
    sorts last when reversed.
    """
    return sorted(items, key=lambda item: item["published"] or "", reverse=True)


def dedupe_by_url(items) -> list[Item]:
    """Drop items whose URL we've already seen (and items with no URL)."""
    seen: set[str] = set()
    unique = []
    for item in items:
        if item["url"] and item["url"] not in seen:
            seen.add(item["url"])
            unique.append(item)
    return unique


def describe_error(exc: Exception) -> str:
    """Turn an exception into a short reason a person can read in the status panel."""
    if isinstance(exc, requests.Timeout):
        return f"Timed out after {TIMEOUT_SECONDS}s"
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        r = exc.response
        return f"HTTP {r.status_code} {r.reason} from {r.url}"
    if isinstance(exc, requests.ConnectionError):
        return f"Could not connect: {str(exc)[:160]}"
    return str(exc)[:240] or type(exc).__name__


def _deadline_result(source: Source) -> SourceResult:
    ms = int(DEADLINE_SECONDS * 1000)
    return _result(source, "error", f"Gave up after the {DEADLINE_SECONDS}s page deadline", [], ms)


def _result(source: Source, status: str, error, items: list[Item], fetch_ms: int) -> SourceResult:
    return {
        "source_id": source.source_id,
        "company": source.company,
        "source_type": source.source_type,
        "bonus": source.bonus,
        "status": status,
        "error": error,
        "items": items,
        "fetch_ms": fetch_ms,
    }


def _ms_since(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)

"""Shared building blocks for every fetcher.

Everything that touches the network goes through `http_get`, so the
User-Agent and the 6-second timeout are defined in exactly one place.
"""

from __future__ import annotations

import calendar
import time
from datetime import datetime, timezone
from typing import Optional, TypedDict, Union

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

TIMEOUT_SECONDS = 6
SUMMARY_MAX_CHARS = 200

# A realistic desktop-browser User-Agent. Several sites return 403 to the
# default "python-requests/x.y" agent.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
}


class Item(TypedDict):
    """One update, normalised to the same shape regardless of source."""

    company: str
    title: str
    url: str
    published: Optional[str]  # ISO-8601 UTC, e.g. "2026-10-01T14:00:00Z"
    source_type: str
    summary: Optional[str]


class SourceResult(TypedDict):
    """The outcome of fetching one source: its items, or why it failed."""

    source_id: str
    company: str
    source_type: str
    bonus: bool
    status: str  # "ok" | "error"
    error: Optional[str]
    items: list[Item]
    fetch_ms: int


def http_get(url: str, **kwargs) -> requests.Response:
    """GET a URL with our headers and timeout; raise on 4xx/5xx."""
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS, **kwargs)
    response.raise_for_status()
    return response


DateInput = Union[str, datetime, time.struct_time, None]


def to_utc_iso(value: DateInput) -> Optional[str]:
    """Normalise any date we meet into an ISO-8601 UTC string, or None.

    Feeds give us `time.struct_time` (already UTC, via feedparser), HTML
    pages give us free-text strings like "Sep 30, 2025".
    """
    if value is None or value == "":
        return None
    try:
        if isinstance(value, time.struct_time):
            dt = datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
        elif isinstance(value, datetime):
            dt = value
        else:
            dt = date_parser.parse(value)
    except (ValueError, OverflowError, TypeError):
        return None

    # A date without a timezone (e.g. "Sep 30, 2025") is treated as UTC.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_summary(raw: Optional[str]) -> Optional[str]:
    """Strip HTML, collapse whitespace and trim to ~200 characters."""
    if not raw:
        return None
    text = BeautifulSoup(raw, "html.parser").get_text(" ")
    text = " ".join(text.split())
    if not text:
        return None
    if len(text) > SUMMARY_MAX_CHARS:
        text = text[:SUMMARY_MAX_CHARS].rsplit(" ", 1)[0] + "…"
    return text


def make_item(
    *,
    company: str,
    source_type: str,
    title: str,
    url: str,
    published: DateInput = None,
    summary: Optional[str] = None,
) -> Item:
    """Build an Item, normalising the date and summary on the way in."""
    return {
        "company": company,
        "title": " ".join(title.split()),
        "url": url,
        "published": to_utc_iso(published),
        "source_type": source_type,
        "summary": clean_summary(summary),
    }

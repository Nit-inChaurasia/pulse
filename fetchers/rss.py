"""Generic RSS / Atom fetcher, reused by every feed-based source.

Blog feeds (RSS 2.0) and YouTube channel feeds (Atom) both go through
here: feedparser understands both formats, so one function covers them.
"""

from __future__ import annotations

import feedparser

from .common import Item, http_get, make_item


def fetch_feed(url: str, *, company: str, source_type: str) -> list[Item]:
    """Download a feed and turn each entry into an Item."""
    # We download with `requests` instead of letting feedparser fetch the URL,
    # because feedparser has no timeout and sends its own User-Agent.
    response = http_get(url)
    feed = feedparser.parse(response.content)

    # `bozo` means feedparser hit a parse problem. Small problems still yield
    # entries, so we only fail when nothing usable came back.
    if feed.bozo and not feed.entries:
        raise ValueError(f"Response was not a valid RSS/Atom feed ({feed.bozo_exception})")

    return [_entry_to_item(entry, company, source_type) for entry in feed.entries]


def _entry_to_item(entry: feedparser.FeedParserDict, company: str, source_type: str) -> Item:
    """Map one feed entry onto our Item shape."""
    # feedparser exposes dates as UTC struct_time; YouTube uses `published`,
    # some blogs only provide `updated`.
    published = entry.get("published_parsed") or entry.get("updated_parsed")
    # YouTube puts the video description in <media:description>.
    summary = entry.get("summary") or entry.get("media_description")

    return make_item(
        company=company,
        source_type=source_type,
        title=entry.get("title", "(untitled)"),
        url=entry.get("link", ""),
        published=published,
        summary=summary,
    )

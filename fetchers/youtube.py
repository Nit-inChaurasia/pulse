"""YouTube channel fetcher: the official RSS feed first, the channel page as a fallback.

Why two methods:
  * The official feed (youtube.com/feeds/videos.xml?channel_id=...) has exact
    dates, but it is unreliable: it returns 404 intermittently, and always
    from cloud IPs such as Vercel's.
  * The channel's /videos page loads from anywhere, but only says "3 days ago".

So we try the feed a few times, and only if it keeps failing do we read the
channel page and turn "3 days ago" into an approximate date (flagged as such).
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from .common import Item, http_get, make_item
from .rss import fetch_feed

FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
CHANNEL_VIDEOS_URL = "https://www.youtube.com/{handle}/videos"
FEED_ATTEMPTS = 3

# The channel page embeds its data as JSON: `var ytInitialData = {...};`
INITIAL_DATA = re.compile(r"(?:var ytInitialData|window\[\"ytInitialData\"\])\s*=\s*(\{.*?\});\s*</script>", re.S)
RELATIVE_AGE = re.compile(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago")
UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400,
                "week": 604800, "month": 2592000, "year": 31536000}


def fetch_youtube(*, handle: str, channel_id: str, company: str, source_type: str) -> list[Item]:
    """Return the channel's latest videos, preferring the official feed."""
    feed_url = FEED_URL.format(channel_id=channel_id)
    for attempt in range(FEED_ATTEMPTS):
        try:
            return fetch_feed(feed_url, company=company, source_type=source_type)
        except requests.HTTPError:
            if attempt < FEED_ATTEMPTS - 1:
                time.sleep(0.3 * (attempt + 1))  # the feed flaps; a short pause often helps

    # The feed kept failing: fall back to the channel page. It occasionally
    # comes back without its video data too, so it gets one retry.
    try:
        return _fetch_channel_page(handle, company, source_type)
    except ValueError:
        return _fetch_channel_page(handle, company, source_type)


def _fetch_channel_page(handle: str, company: str, source_type: str) -> list[Item]:
    """Read video titles and "N days ago" labels from the channel's /videos page."""
    html = http_get(CHANNEL_VIDEOS_URL.format(handle=handle)).text
    match = INITIAL_DATA.search(html)
    if not match:
        raise ValueError("RSS feed returned 404 and the channel page had no video data")

    items = []
    for video in _find_videos(json.loads(match.group(1))):
        metadata = video["metadata"]["lockupMetadataViewModel"]
        items.append(make_item(
            company=company,
            source_type=source_type,
            title=metadata["title"]["content"],
            url=f"https://www.youtube.com/watch?v={video['contentId']}",
            published=_approximate_date(json.dumps(metadata)),
            date_approx=True,
        ))
    return items


def _find_videos(node) -> list[dict]:
    """Walk YouTube's nested JSON and collect every video "lockup" (a video tile)."""
    found = []
    if isinstance(node, dict):
        lockup = node.get("lockupViewModel")
        if lockup and lockup.get("contentType") == "LOCKUP_CONTENT_TYPE_VIDEO":
            found.append(lockup)
        for value in node.values():
            found.extend(_find_videos(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_find_videos(value))
    return found


def _approximate_date(metadata_json: str) -> Optional[datetime]:
    """Turn the first "3 days ago" found in a video's metadata into a datetime."""
    match = RELATIVE_AGE.search(metadata_json)
    if not match:
        return None
    count, unit = int(match.group(1)), match.group(2)
    return datetime.now(timezone.utc) - timedelta(seconds=count * UNIT_SECONDS[unit])

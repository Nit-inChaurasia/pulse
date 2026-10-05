"""Bonus: Anthropic's public LinkedIn page and X profile, via a plain HTTP GET.

The rules here are strict: no login, no cookies, no paid APIs, no scraping
services. We request the same URL a logged-out visitor would open. If the
platform blocks us, we report exactly how (status code, login redirect,
JS-only shell) instead of hiding the failure.

Neither page shows exact post dates in its HTML (LinkedIn says "1w"). Both
platforms, however, encode the creation time inside the post ID itself,
so we decode the date from the ID instead of guessing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag

from .common import HEADERS, TIMEOUT_SECONDS, Item, make_item

LINKEDIN_URL = "https://www.linkedin.com/company/anthropicresearch/"
X_HANDLE = "AnthropicAI"
X_URL = f"https://x.com/{X_HANDLE}"

TITLE_MAX_CHARS = 110
X_EPOCH_MS = 1288834974657  # X ("Twitter") snowflake IDs count from 2010-11-04.


# ---- Shared ----------------------------------------------------------------

def _get_public_page(url: str) -> BeautifulSoup:
    """GET a logged-out page; raise a precise, human-readable reason if blocked."""
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)

    if response.status_code == 999:
        raise PermissionError("HTTP 999: LinkedIn's bot-detection response (request refused)")
    if any(word in response.url for word in ("authwall", "/login", "/i/flow/login")):
        raise PermissionError(f"Redirected to a login wall ({response.url})")
    if response.status_code != 200:
        raise PermissionError(f"HTTP {response.status_code} {response.reason}")
    if not response.text.strip():
        raise ValueError("HTTP 200 but the response body was empty")

    return BeautifulSoup(response.text, "html.parser")


def _ms_to_datetime(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _split_post_text(text: str) -> tuple[str, Optional[str]]:
    """Split a post into (title, summary): its first line, then the rest.

    If the first line is too long to be a title, it's cut short and the
    full text becomes the summary instead.
    """
    first_line, _, rest = text.strip().partition("\n")
    if len(first_line) > TITLE_MAX_CHARS:
        return first_line[:TITLE_MAX_CHARS].rsplit(" ", 1)[0] + "…", text
    return first_line or "(post without text)", rest or None


# ---- LinkedIn --------------------------------------------------------------

def fetch_linkedin(*, company: str, source_type: str) -> list[Item]:
    """Read the posts LinkedIn includes in its logged-out company page."""
    soup = _get_public_page(LINKEDIN_URL)
    cards = soup.select('article[data-activity-urn^="urn:li:activity:"]')
    if not cards:
        raise ValueError("HTTP 200 but no posts in the HTML (login wall or JS-only rendering)")

    items = [item for card in cards if (item := _linkedin_card_to_item(card, company, source_type))]
    if not items:
        raise ValueError("Found post cards, but none had readable text")
    return items


def _linkedin_card_to_item(card: Tag, company: str, source_type: str) -> Optional[Item]:
    commentary = card.select_one('[data-test-id="main-feed-activity-card__commentary"]')
    if commentary is None:
        return None
    text = commentary.get_text("\n", strip=True)
    urn = card["data-activity-urn"]           # "urn:li:activity:7508595648250728448"
    activity_id = int(urn.rsplit(":", 1)[1])

    # The top 41 bits of a LinkedIn activity ID are its creation time in ms.
    published = _ms_to_datetime(activity_id >> 22)

    title, summary = _split_post_text(text)
    return make_item(
        company=company,
        source_type=source_type,
        title=title,
        url=f"https://www.linkedin.com/feed/update/{urn}/",
        published=published,
        summary=summary,
    )


# ---- X ---------------------------------------------------------------------

def fetch_x(*, company: str, source_type: str) -> list[Item]:
    """Read the posts X includes in its logged-out profile page."""
    soup = _get_public_page(X_URL)

    # Quoted posts are <article>s nested inside another <article>;
    # we only want the top-level ones.
    posts = [a for a in soup.find_all("article") if a.find_parent("article") is None]
    items = [item for post in posts if (item := _x_post_to_item(post, company, source_type))]
    if not items:
        raise ValueError("HTTP 200 but no posts in the HTML (login wall or JS-only rendering)")
    return items


def _x_post_to_item(post: Tag, company: str, source_type: str) -> Optional[Item]:
    link = post.find("a", href=lambda h: h is not None and h.startswith(f"/{X_HANDLE}/status/"))
    text_div = post.find("div", class_="whitespace-pre-wrap")
    if link is None or text_div is None:
        return None  # e.g. a repost of another account's post
    text = text_div.get_text("\n", strip=True)
    status_id = int(link["href"].rsplit("/", 1)[1])

    # X "snowflake" IDs: the top 42 bits are ms since X's own epoch.
    published = _ms_to_datetime((status_id >> 22) + X_EPOCH_MS)

    title, summary = _split_post_text(text)
    return make_item(
        company=company,
        source_type=source_type,
        title=title,
        url=f"https://x.com{link['href']}",
        published=published,
        summary=summary,
    )

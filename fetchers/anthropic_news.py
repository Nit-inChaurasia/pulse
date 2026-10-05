"""Scraper for the news listing at https://www.anthropic.com/news.

Anthropic doesn't publish a news RSS feed, so we read the HTML instead.
Each post on the listing page is a link card shaped like this:

    <a href="/news/some-post">
      <time>Oct 2, 2026</time>
      <span class="...__subject">Announcements</span>
      <span class="...__title">Post title</span>
    </a>

The CSS class names carry build hashes (e.g. "__KxYrHG__title") that change
on redeploys, so we match on stable things only: the href prefix, the
<time> tag, and "title" appearing somewhere in the class name.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .common import Item, http_get, make_item

NEWS_URL = "https://www.anthropic.com/news"


def fetch_anthropic_news(*, company: str, source_type: str) -> list[Item]:
    """Download the news listing page and extract every post card."""
    html = http_get(NEWS_URL).text
    soup = BeautifulSoup(html, "html.parser")

    items = []
    for card in soup.select('a[href^="/news/"]'):
        item = _card_to_item(card, company, source_type)
        if item:
            items.append(item)

    if not items:
        raise ValueError("Page loaded, but no news cards matched; the page layout may have changed")
    return items


def _card_to_item(card: Tag, company: str, source_type: str) -> Optional[Item]:
    """Turn one <a href="/news/..."> card into an Item, or None if it isn't a post."""
    time_tag = card.find("time")
    if time_tag is None:  # Nav links and "see all" links have no date.
        return None

    title_tag = card.find(class_=lambda c: c is not None and "title" in c)
    title = (title_tag or card).get_text(" ", strip=True)

    return make_item(
        company=company,
        source_type=source_type,
        title=title,
        url=urljoin(NEWS_URL, card["href"]),
        published=time_tag.get("datetime") or time_tag.get_text(strip=True),
    )

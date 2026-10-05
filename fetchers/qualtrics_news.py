"""Scraper for the Qualtrics newsroom at https://www.qualtrics.com/news/.

Why this exists: Qualtrics has no blog RSS feed, and YouTube refuses its
feeds to cloud IPs (so the YouTube source fails on Vercel). The newsroom
works from anywhere.

The catch: the listing page shows titles but no dates. So this is a
two-step scrape:
  1. GET the listing page and collect the article links.
  2. GET each article page (in parallel) and read its date and summary.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from .common import Item, http_get, make_item

NEWSROOM_URL = "https://www.qualtrics.com/news/"
MAX_ARTICLES = 10


def fetch_qualtrics_news(*, company: str, source_type: str) -> list[Item]:
    """Collect article links from the newsroom, then fetch each article."""
    urls = _article_urls(http_get(NEWSROOM_URL).text)[:MAX_ARTICLES]
    if not urls:
        raise ValueError("Newsroom loaded, but no article links matched; the layout may have changed")

    # Step 2 runs in parallel, so 10 article pages take about as long as one.
    with ThreadPoolExecutor(max_workers=len(urls)) as pool:
        articles = list(pool.map(_fetch_article, urls))

    return [
        make_item(company=company, source_type=source_type, **article)
        for article in articles
        if article is not None
    ]


def _article_urls(listing_html: str) -> list[str]:
    """All unique on-site /news/<slug>/ links, in page order, without tracking params."""
    soup = BeautifulSoup(listing_html, "html.parser")
    urls: list[str] = []
    for link in soup.select('a[href^="/news/"]'):
        path = urlsplit(link["href"]).path      # drops "?utm_lp=..." tracking params
        url = urljoin(NEWSROOM_URL, path)
        if path.strip("/") != "news" and url not in urls:
            urls.append(url)
    return urls


def _fetch_article(url: str) -> Optional[dict]:
    """Read one article's title, date and summary. Returns None if the page fails."""
    try:
        soup = BeautifulSoup(http_get(url).text, "html.parser")
    except Exception:
        return None  # one broken article shouldn't sink the other nine

    title = soup.find("h1")
    description = soup.find("meta", attrs={"name": "description"})
    return {
        "title": title.get_text(" ", strip=True) if title else url,
        "url": url,
        "published": _find_date(soup),
        "summary": description.get("content") if description else None,
    }


def _find_date(soup: BeautifulSoup) -> Optional[str]:
    """The date sits in a small "eyebrow" label near the title, e.g. "Sep 23, 2026".

    Other eyebrow labels hold author names, so we take the first one that
    actually parses as a date.
    """
    for label in soup.select("div.text-eyebrow"):
        text = label.get_text(strip=True)
        try:
            date_parser.parse(text)
            return text
        except (ValueError, OverflowError):
            continue
    return None

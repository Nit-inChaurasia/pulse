# Pulse

Pulse shows the latest public updates from **OpenAI**, **Anthropic** and **Gartner** in one timeline, newest first, each linking back to its source.
Open the page and press **Fetch now**: the server pulls every source live at that moment. Nothing is cached, stored, pasted in or generated.

**Live:** https://pulse.3minbite.online  ·  raw data: [`/api/updates`](https://pulse.3minbite.online/api/updates)

<!-- Screenshot of the hosted page after "Fetch now", 5 Oct 2026. Replace docs/screenshot.png any time. -->
![Pulse screenshot](docs/screenshot.png)

---

## 1. Run it locally

```bash
git clone https://github.com/Nit-inChaurasia/pulse.git
cd pulse
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                    # → http://localhost:5000
```

Python 3.10+ works (Vercel runs 3.12). There are no API keys, environment variables or database.

## 2. How it works

1. `GET /` renders the landing page straight from the source registry: the three companies, their sources, and a **Fetch now** button. No outside requests happen yet.
2. **Fetch now** calls `GET /api/updates`. The server fetches every source in parallel and returns JSON.
3. `public/static/app.js` fills in each source's result (item count and time, or the exact error) and renders the merged timeline with filter tabs.

### Sources

| Company | Source | Method | URL | Local | Vercel |
|---|---|---|---|---|---|
| OpenAI | News feed | RSS via `feedparser` | `https://openai.com/news/rss.xml` | ✅ 10 | ✅ 10 |
| Anthropic | News page | HTML scrape (`requests` + BeautifulSoup) | `https://www.anthropic.com/news` | ✅ 10 | ✅ 10 |
| Anthropic | YouTube | RSS feed, falling back to the channel page | [`@anthropic-ai`](https://www.youtube.com/@anthropic-ai) · `UCrDwWp7EBBv4NwvScIpBDOA` | ✅ 10 (feed) | ✅ 10 (fallback) |
| Gartner | YouTube | RSS feed, falling back to the channel page | [`@Gartnervideo`](https://www.youtube.com/@Gartnervideo) · `UCSNX50LYGXWV_e5UWZGPGbw` | ✅ 10 (usually feed) | ✅ 10 (fallback) |
| Anthropic *(bonus)* | LinkedIn | Plain GET, logged out | `https://www.linkedin.com/company/anthropicresearch/` | ✅ 10 | ✅ 10 |
| Anthropic *(bonus)* | X | Plain GET, logged out | `https://x.com/AnthropicAI` | ✅ 5 | ✅ 5 |

Statuses were checked on 5 Oct 2026 against http://localhost:5000 and https://pulse.3minbite.online. The page shows the live result on every fetch.

### What I found while checking each source

Every URL was requested and its response inspected before any fetcher was written.

- **Gartner's own site is unreachable by plain HTTP.** Every gartner.com URL I tried returned **HTTP 403 with a Cloudflare "Just a moment…" JavaScript challenge**: the newsroom, `/en/newsroom/rss`, `blogs.gartner.com/feed/`, even `robots.txt`. This happened from both a cloud server and a home connection. Passing it would need a headless browser or a scraping service, which are out of scope. So Gartner's YouTube channel is its source.
- **YouTube's RSS feeds are unreliable.** From a home connection, `feeds/videos.xml` returns 404 intermittently; a retry usually works. From cloud IPs (including Vercel) it fails every time (404/500). The channel's `/videos` page, however, loads everywhere.
- **The fallback** reads that page's embedded JSON (`ytInitialData`) for titles and video IDs. The page only says "3 days ago", so those dates are **approximate**. They're flagged `date_approx` in the JSON, shown with a `~` in the UI, and the source is marked "fallback".
- **Channel IDs** come from the `<link rel="canonical">` on each channel page.

## 3. Walkthrough of the fetch code

Everything lives in [`fetchers/`](fetchers):

| File | What it does |
|---|---|
| [`__init__.py`](fetchers/__init__.py) | The `COMPANIES` and `SOURCES` registry, plus `run_all()`, which fetches everything in parallel and merges the results |
| [`common.py`](fetchers/common.py) | `http_get()` (the one place the User-Agent and 6s timeout are set), plus date and summary normalisation |
| [`rss.py`](fetchers/rss.py) | `fetch_feed()`: one generic RSS/Atom fetcher |
| [`youtube.py`](fetchers/youtube.py) | `fetch_youtube()`: tries the feed up to 3 times, then falls back to the channel page |
| [`anthropic_news.py`](fetchers/anthropic_news.py) | `fetch_anthropic_news()`: scrapes the `<a href="/news/…">` cards |
| [`social.py`](fetchers/social.py) | `fetch_linkedin()` / `fetch_x()`: the bonus attempts |

**Where the HTTP requests happen:**

- `common.http_get()` makes every feed, scrape and YouTube request: one `requests.get(url, headers=…, timeout=6)`.
- `social._get_public_page()` makes the LinkedIn and X requests. It calls `requests.get` itself so it can report *why* a platform blocked it (999, login redirect, empty body).

**How results are merged and sorted (`fetchers/__init__.py`):**

1. `run_all()` submits one `run_source()` per source to a `ThreadPoolExecutor` and waits at most 8.5s overall.
2. `run_source()` calls the fetcher inside `try/except`. A failure becomes `status: "error"` with a readable reason, so one broken site never breaks the page. On success it de-duplicates by URL, sorts newest first and keeps the top 10.
3. `run_all()` flattens every source's items, de-duplicates again and sorts.
4. `newest_first()` sorts by the ISO-8601 UTC string. One fixed format means text order equals time order, and items with no date sort as `""`, so they land at the bottom.

## 4. LinkedIn & X: what I tried and what happened

These were attempted for Anthropic with a single plain `GET`, a browser User-Agent and **no cookies, login, API or scraping service**.

- **LinkedIn.** `GET /company/anthropicresearch/` returned **HTTP 200** with about 345 KB of HTML that already contains the 10 latest posts as `<article data-activity-urn="urn:li:activity:…">`. Posts only show relative dates ("1w"), so the exact date is decoded from the activity ID, whose top 41 bits are the creation time in ms. I checked this against the Anthropic enzyme post: the ID decodes to 23 Sep 2026, the same day as the news article. The code still handles the usual blocks (HTTP 999, `authwall` redirect), which LinkedIn often serves to datacenter IPs.
- **X.** `GET /AnthropicAI` returned **HTTP 200** with server-rendered HTML holding the latest posts, followed by a "Log in or sign up" wall. The fetcher keeps top-level posts by @AnthropicAI only and decodes each date from the snowflake ID (`(id >> 22) + 1288834974657` ms).

Both are best-effort and labelled **Bonus** in the UI. If either platform changes its logged-out HTML, the source row shows the precise reason instead.

## 5. Design decisions and trade-offs

- **Fetch on demand.** The landing page loads instantly and shows *what* will be fetched. The button makes the live pull explicit: you watch every source spin, then turn green or red with its timing. It also means opening the link costs the sources nothing.
- **RSS first, scraping second.** Feeds are stable, dated and cheap to parse. Scrapers depend on markup, so they match only stable hooks (`href` prefixes, `<time>`, embedded JSON keys) and never hashed CSS class names.
- **Honest fallbacks.** When YouTube's feed fails, a fallback keeps the source alive, but approximate dates are labelled, never passed off as exact.
- **Parallel fetching.** The work is almost all waiting on the network. Threads overlap those waits, so a fetch takes about as long as the slowest source (around 1.5–3s) rather than the sum. A hard 8.5s deadline caps it.
- **No caching.** The brief was "genuinely fetched at request time". Responses send `Cache-Control: no-store`, so Vercel's CDN never serves a stale copy. The cost is slower fetches and more load on sources under real traffic.
- **No framework.** Jinja for the page and about 150 lines of vanilla JS for the button and timeline. All fetched text goes in through `textContent`, so a malicious title can't inject HTML.
- **Zero-config Vercel.** Vercel's current Flask support auto-detects the `app` in `app.py`, so there's no `api/index.py` shim or legacy `builds`/`routes` config. `vercel.json` only sets `maxDuration`. CSS and JS sit in `public/static/`, because Vercel serves `public/` from its CDN while Flask serves the same path locally. It's one codebase for both.

## 6. How this was built

Directed with Claude Code: I wrote the brief, approved the plan, and approved each step that touched my accounts (GitHub, Vercel, DNS). Claude verified every source URL with live requests before writing the fetcher for it.

**What I reviewed and corrected:**

<!-- Add your notes here: what you checked, what you changed, what you'd push back on. -->
- _…_

## 7. What I'd add next

- **Scheduling.** A Vercel Cron job (or GitHub Action) that pulls every 15 minutes.
- **Change tracking.** Store seen URLs (e.g. Vercel KV / Postgres) so the page can highlight what's new since your last visit.
- **Alerts.** Email or Slack when a tracked company posts.
- **More sources.** Gartner via a source that isn't behind Cloudflare (e.g. its press releases on a wire service), GitHub releases and podcast feeds.
- **Short caching.** A 2–5 minute cache to be polite to sources under real traffic.
- **Streaming results.** Show each source the moment it finishes, instead of all at once.

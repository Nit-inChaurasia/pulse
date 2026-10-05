"""Pulse: live public updates from OpenAI, Anthropic and Qualtrics on one page.

Run locally with `python app.py`, then open http://localhost:5000.
On Vercel, the same `app` object is served by the Python runtime.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from flask import Flask, Response, jsonify, render_template

from fetchers import COMPANIES, run_all

GITHUB_URL = "https://github.com/rebelbhai701/pulse"

app = Flask(__name__)


@app.get("/")
def index() -> str:
    """Fetch every source live and render the page."""
    data = run_all()
    return render_template("index.html", companies=COMPANIES, github_url=GITHUB_URL, **data)


@app.get("/api/updates")
def api_updates() -> Response:
    """The same live data as JSON: every SourceResult plus the merged feed."""
    return jsonify(run_all())


@app.after_request
def disable_caching(response: Response) -> Response:
    """Tell browsers and Vercel's CDN never to cache: every load is a fresh pull."""
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


# ---- Template helpers ------------------------------------------------------

def _parse_iso(iso: Optional[str]) -> Optional[datetime]:
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) if iso else None


@app.template_filter("timeago")
def timeago(iso: Optional[str]) -> str:
    """'3 days ago' style label for an ISO-8601 UTC timestamp."""
    dt = _parse_iso(iso)
    if dt is None:
        return "Date unknown"
    seconds = int((datetime.now(timezone.utc) - dt).total_seconds())
    if seconds < 0:
        return "just now"
    for unit, size in (("year", 31_536_000), ("month", 2_592_000), ("week", 604_800),
                       ("day", 86_400), ("hour", 3_600), ("minute", 60)):
        if seconds >= size:
            count = seconds // size
            return f"{count} {unit}{'s' if count > 1 else ''} ago"
    return "just now"


@app.template_filter("fulldate")
def fulldate(iso: Optional[str]) -> str:
    """Full, unambiguous date for the hover tooltip."""
    dt = _parse_iso(iso)
    return dt.strftime("%a %d %b %Y, %H:%M UTC") if dt else "No date published"


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)

"""Pulse: live public updates from OpenAI, Anthropic and Gartner, fetched on demand.

Run locally with `python app.py`, then open http://localhost:5000.
On Vercel, the same `app` object is served by the Python runtime.

Two routes:
  /              the landing page: the three companies and their sources, plus
                 a "Fetch now" button. Nothing is fetched until it's clicked.
  /api/updates   does the live fetch (every source, in parallel) and returns
                 JSON. The button calls this; you can also open it directly.
"""

from __future__ import annotations

from flask import Flask, Response, jsonify, render_template

from fetchers import COMPANIES, SOURCES, run_all

GITHUB_URL = "https://github.com/Nit-inChaurasia/pulse"

# CSS and JS live in public/static/. On Vercel, files under public/ are served
# straight from the CDN (Flask's static route is not used there); locally,
# Flask serves the same folder at the same /static/ URL. One codebase, both places.
app = Flask(__name__, static_folder="public/static", static_url_path="/static")


@app.get("/")
def index() -> str:
    """Render the landing page from the source registry (no fetching here)."""
    sources_by_company = {
        company: [s for s in SOURCES if s.company == company] for company in COMPANIES
    }
    return render_template(
        "index.html",
        companies=COMPANIES,
        sources_by_company=sources_by_company,
        github_url=GITHUB_URL,
    )


@app.get("/api/updates")
def api_updates() -> Response:
    """Fetch every source live and return all SourceResults plus the merged feed."""
    return jsonify(run_all())


@app.after_request
def disable_caching(response: Response) -> Response:
    """Tell browsers and Vercel's CDN never to cache: every fetch is a fresh pull."""
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)

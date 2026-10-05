// Pulse front end: one button, one request to /api/updates, then render.
// All fetching happens on the server; this file only shows progress and results.
// Every piece of fetched text goes in via textContent, never innerHTML.

const button = document.getElementById("fetch-btn");
const buttonLabel = button.querySelector(".btn-label");
const summary = document.getElementById("run-summary");
const results = document.getElementById("results");
const feed = document.getElementById("feed");
const cardTemplate = document.getElementById("card-template");
const sourceRows = document.querySelectorAll(".source");
const tabs = document.querySelectorAll(".tab");

let activeFilter = "all";

button.addEventListener("click", fetchUpdates);
tabs.forEach((tab) => tab.addEventListener("click", () => applyFilter(tab.dataset.filter)));

async function fetchUpdates() {
  setLoading(true);
  const started = performance.now();
  const ticker = setInterval(() => {
    summary.textContent = `Fetching from ${sourceRows.length} sources… ${seconds(performance.now() - started)}`;
  }, 100);

  try {
    const response = await fetch("/api/updates", { cache: "no-store" });
    if (!response.ok) throw new Error(`Server returned HTTP ${response.status}`);
    const data = await response.json();
    renderSources(data.sources);
    renderFeed(data.items);
    renderSummary(data);
  } catch (error) {
    summary.textContent = `Couldn't reach the server: ${error.message}. Try again.`;
    summary.classList.add("is-error");
    sourceRows.forEach((row) => setRow(row, "idle", "Ready"));
  } finally {
    clearInterval(ticker);
    setLoading(false);
  }
}

function setLoading(isLoading) {
  button.disabled = isLoading;
  button.classList.toggle("is-loading", isLoading);
  buttonLabel.textContent = isLoading ? "Fetching…" : "Fetch again";
  summary.hidden = false;
  summary.classList.remove("is-error");
  if (isLoading) sourceRows.forEach((row) => setRow(row, "loading", "Fetching…"));
}

// ---- Rendering -------------------------------------------------------------

function renderSources(sources) {
  for (const source of sources) {
    const row = document.querySelector(`.source[data-source-id="${source.source_id}"]`);
    if (!row) continue;
    if (source.status === "ok") {
      setRow(row, "ok", `${source.items.length} items · ${seconds(source.fetch_ms)}`, source.note);
    } else {
      setRow(row, "error", source.error);
    }
  }
}

function setRow(row, state, text, note = null) {
  row.dataset.state = state;
  const result = row.querySelector(".source-result");
  result.textContent = note ? `${text} · fallback` : text;
  result.title = note || (state === "error" ? text : "");
}

function renderFeed(items) {
  feed.replaceChildren(...items.map(buildCard));
  if (items.length === 0) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "No updates could be fetched. Each source above shows why.";
    feed.append(empty);
  }
  updateCounts(items);
  applyFilter(activeFilter);
  const firstReveal = results.hidden;
  results.hidden = false;
  // On the first fetch, bring the results into view if they landed below the fold.
  if (firstReveal && results.getBoundingClientRect().top > window.innerHeight) {
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function buildCard(item) {
  const card = cardTemplate.content.firstElementChild.cloneNode(true);
  card.dataset.company = item.company;
  card.classList.add(`card-${item.company.toLowerCase()}`);

  card.querySelector(".badge").textContent = item.company;
  card.querySelector(".tag").textContent = item.source_type;

  const time = card.querySelector("time");
  if (item.published) {
    const date = new Date(item.published);
    time.dateTime = item.published;
    time.textContent = (item.date_approx ? "~" : "") + timeAgo(date);
    time.title = item.date_approx
      ? "Approximate: YouTube's feed was unavailable, so this comes from the channel page's \"days ago\" label"
      : date.toLocaleString(undefined, { dateStyle: "full", timeStyle: "short" });
  } else {
    time.textContent = "Date unknown";
  }

  const link = card.querySelector(".card-title a");
  link.href = item.url;
  link.textContent = item.title;

  const summaryEl = card.querySelector(".card-summary");
  if (item.summary) summaryEl.textContent = item.summary;
  else summaryEl.remove();

  return card;
}

function renderSummary(data) {
  const fetchedAt = new Date(data.fetched_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const ok = data.sources.filter((s) => s.status === "ok").length;
  summary.textContent =
    `Fetched live at ${fetchedAt} in ${seconds(data.total_ms)} · ` +
    `${data.items.length} updates from ${ok} of ${data.sources.length} sources`;
}

// ---- Filter tabs -----------------------------------------------------------

function applyFilter(filter) {
  activeFilter = filter;
  tabs.forEach((tab) => tab.setAttribute("aria-pressed", String(tab.dataset.filter === filter)));
  feed.querySelectorAll(".card").forEach((card) => {
    card.hidden = filter !== "all" && card.dataset.company !== filter;
  });
}

function updateCounts(items) {
  tabs.forEach((tab) => {
    const filter = tab.dataset.filter;
    const count = filter === "all" ? items.length : items.filter((i) => i.company === filter).length;
    tab.querySelector(".count").textContent = count;
  });
}

// ---- Formatting helpers ----------------------------------------------------

const relative = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
const UNITS = [["year", 31536e3], ["month", 2592e3], ["week", 604800], ["day", 86400], ["hour", 3600], ["minute", 60]];

function timeAgo(date) {
  const secondsAgo = (Date.now() - date.getTime()) / 1000;
  for (const [unit, size] of UNITS) {
    if (secondsAgo >= size) return relative.format(-Math.floor(secondsAgo / size), unit);
  }
  return "just now";
}

function seconds(ms) {
  return `${(ms / 1000).toFixed(1)}s`;
}

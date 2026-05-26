# Phase 13 Research: StackCT Data & Persistence Layer

**Researched:** 2026-05-26  
**Answers user questions from planning request**

---

## 1. Cost model: StackCT scrape vs Claude vs hypothetical StackCT API

| Approach | Dollar cost | Time cost | Reliability | Ops burden |
|----------|-------------|-----------|-------------|------------|
| **Playwright DOM scrape** (current) | **$0** StackCT API fees — no paid StackCT REST integration | **High:** ~15–45s Auth0 login + navigation per browser session; **~30–60s** per project plan preview (`get_all_page_ids`); full project list refresh similar | **Medium–Low:** Auth0 redirect races, concurrent login conflicts, Angular virtual scroll, `[data-page-id]` DOM changes | Headless Chromium on VPS, `_browser_lock`, memory/CPU per session |
| **Anthropic Claude Vision** (analysis) | **Paid:** per input/output token (Haiku ~$1/$5 per MTok in app pricing table) | ~5–15s per sheet analyzed | API-stable; model routing in `claude_analyzer.py` | API key in `.env` only |
| **Hypothetical official StackCT REST API** | Unknown — **not used today**; no API key in `.env.example` | Would likely be seconds per request if documented | Would depend on SLA and versioning | API keys, rate limits, contract |
| **Undocumented internal HTTP** (`agent.stackct`, SignalR) | No direct fee if same auth session | Potentially faster than full DOM walk | **High breakage risk** — undocumented, may require bearer tokens from SPA | Discovery via HAR/network capture; legal/ToS ambiguity |

**User clarification:** The app does **not** use a paid StackCT REST API. “Free” in dollars means Playwright automation. The real costs are **latency**, **login reliability**, and **operational complexity** — not StackCT invoices.

**Paid spend today:** Almost entirely **Claude** during take-off runs, not StackCT data fetch.

---

## 2. Current architecture gaps

### File-based cache (`project_cache.py`)

| File | Role | Gap |
|------|------|-----|
| `output/projects_cache.json` | All projects + `fetched_at` | No query/index; stale fallback opaque; not relational to plans |
| `output/plans_cache/{project_id}.json` | Plans per project | **Sheet counts only exist after preview** — `get_all_sheet_counts()` scans disk |
| `output/plans_cache/_index.json` | Denormalized counts | Rebuilt opportunistically; drifts if JSON files edited manually |

### Behavioral gaps

1. **Sheet counts on project list:** UI shows “Preview for count” until `plans_cache/{id}.json` exists (`static/app.js` `loadSheetCounts` → `/api/projects/sheet-counts`).
2. **Preview login failures:** Each preview can spawn a **new** browser login (`_fetch_pages_for_project`); concurrent UI actions hit `_browser_lock` → long waits or timeouts; login errors surface only on preview click.
3. **No systematic warm-up:** `prefetch_in_background()` only refreshes **projects**, not per-project plans.
4. **JSON as database:** No sync history, no “last successful sync”, no partial updates, no TTL per entity type in one place.
5. **Run metadata:** Take-off runs live in `output/{folder}/` — separate from StackCT catalog data (acceptable) but no link table `run ↔ project_id`.

### Existing mitigations (keep)

- `_browser_lock` in `project_cache.py` — **must move with sync layer**, not removed.
- 24h TTL (`CACHE_TTL_HOURS`, `PLANS_CACHE_TTL_HOURS`).
- Stale cache fallback on live fetch failure.

---

## 3. DB schema proposal (SQLite v1.1)

**Location:** `{OUTPUT_DIR}/stackct.db` (beside reports, gitignored via `output/`)

**stdlib `sqlite3`** recommended for v1.1 — zero new infra, no Redis, no Celery. Optional SQLAlchemy in v2 if ORM needed.

```sql
-- Canonical StackCT project catalog
CREATE TABLE projects (
    stackct_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    sheet_count INTEGER,              -- denormalized; updated when plans sync
    plans_synced_at TEXT,             -- ISO8601
    projects_synced_at TEXT,          -- from last full list sync (same for all rows)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Drawing pages / sheets per project
CREATE TABLE project_plans (
    stackct_id INTEGER NOT NULL,      -- project id
    page_id INTEGER NOT NULL,
    sheet_name TEXT NOT NULL DEFAULT '',
    sheet_type TEXT,                  -- optional: arch/electrical/mechanical/schedule (future)
    synced_at TEXT NOT NULL,
    PRIMARY KEY (stackct_id, page_id),
    FOREIGN KEY (stackct_id) REFERENCES projects(stackct_id) ON DELETE CASCADE
);

-- Audit trail for sync jobs
CREATE TABLE sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_type TEXT NOT NULL,          -- 'projects' | 'plans' | 'plans_bulk'
    project_id INTEGER,               -- NULL for full project list sync
    status TEXT NOT NULL,             -- 'running' | 'success' | 'error'
    started_at TEXT NOT NULL,
    finished_at TEXT,
    records_written INTEGER DEFAULT 0,
    error_message TEXT,
    from_cache_fallback INTEGER DEFAULT 0
);

-- Key-value metadata (TTL overrides, schema version, last full sync)
CREATE TABLE cache_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

**Indexes:** `CREATE INDEX idx_plans_project ON project_plans(stackct_id);`

---

## 4. Sync strategies

| Strategy | When | Implementation |
|----------|------|----------------|
| **TTL (default 24h)** | Serve DB if `plans_synced_at` / projects row fresh | Match existing `CACHE_TTL_HOURS`; store in `cache_metadata` |
| **Manual refresh** | User clicks Refresh on Projects | `POST /api/projects/refresh`, `POST /api/projects/sync-plans` (new) |
| **Background cron** | App startup + interval | **APScheduler** already in `requirements.txt` — `sync_projects_if_stale()` every N hours |
| **Stale-while-revalidate** | API returns DB immediately; trigger background sync if stale | `from_cache: true`, `syncing: true` in JSON response |
| **Bulk plans prefetch** (optional 13-02 follow-up) | After project sync, queue top-N or all projects | Rate-limited; one browser session per batch under lock |

**Locking:** Single global `threading.Lock` for Playwright (existing `_browser_lock`). Document in README: do not run scrape job + manual refresh concurrently.

---

## 5. Options comparison

### Option A: SQLite only (recommended v1.1)

- **Pros:** No new services; queryable sheet counts; sync audit; easy backup (one file); fits Flask monolith.
- **Cons:** Write contention minimal at single-operator scale; not multi-host without shared FS.

### Option B: Discover StackCT internal HTTP APIs

`browser.py` already logs requests matching `agent.stackct`, `api/`, `signalr`:

```52:56:browser.py
    def _on_request(self, request):
        url = request.url
        if any(x in url for x in ["agent.stackct", "api/", "/takeoff/", "/pages/", "signalr"]):
            logger.debug(f"API call: {request.method} {url[:120]}")
```

- **Pros:** Could cut plan-list time from 30–60s to sub-second if JSON endpoint found.
- **Cons:** Undocumented; auth headers from SPA; breaks on deploy; **defer to Phase 13 spike task or v2** — do not block DB layer.
- **Spike (optional):** Playwright `page.on("response")` capture during `get_all_page_ids`; save redacted HAR to `output/api_discovery/` — **not in critical path for 13-01–04**.

### Option C: Redis (defer v2)

- Aligns with ARCH-02 Celery/Redis queue — overkill for catalog cache.

---

## 6. Migration path from JSON caches

1. On first app start after deploy: if `stackct.db` missing and `projects_cache.json` exists → import projects + `fetched_at`.
2. Scan `plans_cache/*.json` (skip `_index.json`) → upsert `project_plans` + set `projects.sheet_count`.
3. Keep JSON files read-only for one release; write **only to DB** after migration.
4. Optional CLI: `python -m stackct_store migrate` idempotent.

---

## 7. Security

- **Credentials:** Remain in `.env` only (`STACKCT_EMAIL`, `STACKCT_PASSWORD`). **DB stores no secrets.**
- **DB file:** Under `OUTPUT_DIR`; same permissions as report folders.
- **API responses:** Continue sanitized errors (Phase 1); sync errors in `sync_runs.error_message` logged server-side.

---

## 8. How this fixes user pain points

| Pain | Root cause | Phase 13 fix |
|------|------------|--------------|
| Sheet counts only after preview | Counts derived from `plans_cache/*.json` | `projects.sheet_count` populated by sync job; `/api/projects/sheet-counts` reads DB; bulk sync can warm counts |
| Preview login failures | New browser session per fetch; lock queue | Stale-while-revalidate: preview reads DB if fresh; background sync on miss; single lock documented |
| Concurrent browser logins | Multiple code paths spawn browsers | All sync through `stackct_sync.py` + shared lock; UI shows `syncing` state |
| JSON caches in output | No index | Replace with `stackct.db`; JSON deprecated |

---

## 9. Module layout (recommended)

```
stackct_store.py    # sqlite connection, schema, CRUD, migration
stackct_sync.py     # browser ingest orchestration (uses project_cache patterns)
project_cache.py    # thin facade: get_projects/get_project_plans → store + sync
config.py           # STACKCT_DB_PATH, TTL env vars
```

---

## 10. References

- `project_cache.py` — TTL, lock, JSON paths
- `browser.py` — `get_all_projects`, `get_all_page_ids`
- `app.py` — `/api/projects`, `/api/projects/sheet-counts`, `/api/projects/<id>/plans`
- `static/app.js` — `loadSheetCounts`, `fetchPlans`
- Master.md §3.8, §7–8 (Projects workspace, sheet counts)
- `.planning/research/PITFALLS.md` — XHR intercept alternative for project list

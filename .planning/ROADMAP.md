# Roadmap: Bobby Tailor — StackCT Estimation Automation

## Overview

Brownfield upgrade of the Flask + Playwright take-off monolith to a shippable estimator tool: fix deployment and browser reliability first, add cost transparency and Master Phase 1 critical UX (plan selection, report preview), then layer settings, live job monitoring, and the industrial UI shell. v1 extends Flask in place; FastAPI migration (ARCH-01) stays in v2.

**Depth:** comprehensive (11 phases)  
**Stack:** Python, Flask, Playwright, Anthropic Claude Vision — per PROJECT.md  
**Source of truth:** `Master.md` v2.0 (implementation order §7, UI spec §8, agent steps §9)

## Phases

- [x] **Phase 1: Config & Safe Operations** — Portable `.env`, sanitized API errors, dependency docs
- [x] **Phase 2: Browser Reliability** — Canvas stability, full project list, VPS Chromium
- [x] **Phase 3: API Cost Transparency** — Per-sheet and per-run token/USD tracking in reports
- [x] **Phase 4: StackCT Plan Selection** — Preview sheets, filter, run selected `page_ids` only
- [x] **Phase 5: Report Preview APIs** — In-browser summary, tables, JSON with safe paths
- [x] **Phase 6: Settings Management** — Credentials and preferences editable in UI
- [x] **Phase 7: Live Job Monitoring** — Per-sheet progress, logs, sidebar mini-card
- [x] **Phase 8: UI Shell Foundation** — Sidebar layout, dark theme, static JS/CSS
- [ ] **Phase 9: Projects Workspace** — Scope toggle and plan-selection workflow in UI
- [ ] **Phase 10: Reports & Monitor UI** — Report cards with preview tabs; live monitor page
- [ ] **Phase 11: PDF Selection & Production Docs** — PDF page picker; VPS README
- [x] **Phase 12: Application Authentication** — Login sessions, protected routes/APIs, seeded admin for production deploy
- [x] **Phase 13: StackCT Data & Persistence Layer** — SQLite catalog, sync service, DB-first APIs, sheet counts without per-preview scrape

## Phase Details

### Phase 1: Config & Safe Operations

**Goal:** Operators can install and run the app on any machine without editing source code; API failures never leak stack traces to the UI.

**Depends on:** Nothing (first phase)

**Requirements:** FOUND-01, FOUND-02, DEPLOY-01, DEPLOY-03

**Success Criteria** (what must be TRUE):

1. Starting the app on a fresh clone with only `.env` beside the project root loads StackCT and Anthropic credentials successfully
2. A failed job or API error shows a short, human-readable message in the UI while full details appear only in server logs
3. `.env.example` lists every required variable with brief descriptions
4. `pip install -r requirements.txt` installs Pillow and all runtime deps without extra manual packages

**Plans:** 3 plans in 2 waves

Plans:

- [x] 01-01-PLAN.md — Config validation & fail-fast env (wave 1)
- [x] 01-02-PLAN.md — Flask error sanitization & safe job errors (wave 2)
- [x] 01-03-PLAN.md — `.env.example` audit & requirements verify (wave 1)

---

### Phase 2: Browser Reliability

**Goal:** StackCT automation reliably discovers all projects and captures sharp, complete drawing screenshots on VPS hardware.

**Depends on:** Phase 1

**Requirements:** FOUND-03, FOUND-04, FOUND-05

**Success Criteria** (what must be TRUE):

1. Screenshots are taken only after the drawing canvas pixels stop changing (not after a fixed sleep alone)
2. Project dropdown includes projects that appear only after scrolling a long StackCT list (no silent truncation)
3. A StackCT scrape completes on a Linux VPS with headless Chromium using documented launch flags (e.g. `--disable-dev-shm-usage`)
4. Failed canvas capture retries or logs clearly instead of saving blank or partial images

**Plans:** 3 plans in 2 waves

| Wave | Plans | Parallel | Description |
|------|-------|----------|-------------|
| 1 | 02-01 | — | Canvas stability + screenshot retry (browser.py core) |
| 2 | 02-02, 02-03 | yes | Project scroll + VPS docs (after 02-01 lands) |

Plans:

- [x] 02-01-PLAN.md — Pixel-hash canvas stability detection with retry (browser.py)
- [x] 02-02-PLAN.md — Virtual scroll handling in get_all_projects() (browser.py)
- [x] 02-03-PLAN.md — VPS Chromium docs and Pillow dependency (README, requirements.txt)

---

### Phase 3: API Cost Transparency

**Goal:** Estimators see exactly what each run cost in tokens and USD before exporting take-offs.

**Depends on:** Phase 1

**Requirements:** COST-01, COST-02, COST-03, COST-04

**Success Criteria** (what must be TRUE):

1. Each analyzed sheet records input/output tokens and the Claude model used
2. Completed runs show a single aggregated USD total for API usage
3. Report list cards and `summary.txt` display cost for that run
4. `takeoff.json` contains an `api_usage` block with token and cost totals

**Plans:** 3 plans in 3 waves

| Wave | Plans | Parallel | Description |
|------|-------|----------|-------------|
| 1 | 03-01 | — | Per-sheet usage capture (claude_analyzer.py) |
| 2 | 03-02 | — | Run-level aggregation + summary.txt (reporter.py) |
| 3 | 03-03 | — | Cost display in UI report cards (app.py + index.html) |

Plans:

- [x] 03-01-PLAN.md — Per-sheet token/cost capture in analyze_drawing()
- [x] 03-02-PLAN.md — Run-level aggregation + api_usage in takeoff.json + summary.txt cost section
- [x] 03-03-PLAN.md — Display cost in report list cards via list_reports() API

---

### Phase 4: StackCT Plan Selection

**Goal:** Users choose which drawing sheets to analyze before spending API credits — no forced full-project runs.

**Depends on:** Phase 2 (reliable page discovery)

**Requirements:** PLAN-01, PLAN-02, PLAN-03, PLAN-04, PLAN-05

**Success Criteria** (what must be TRUE):

1. User can load the drawing page list for a selected project without starting analysis
2. User sees sheet names with checkboxes plus Select All / Select None
3. User can filter the plan list by sheet type (architectural, electrical, mechanical, schedule)
4. User can start a run that processes only checked sheets
5. `/api/run/stackct` accepts optional `page_ids` and the scraper analyzes only those pages

**Plans:** 3 plans (2 waves)

Plans:

- [ ] 04-01-PLAN.md — Plans fetching API endpoint (Wave 1)
- [ ] 04-02-PLAN.md — page_ids filter on run endpoint and scraper (Wave 1)
- [ ] 04-03-PLAN.md — Plan-selection UI panel with checkboxes and type filter (Wave 2)

---

### Phase 5: Report Preview APIs

**Goal:** Users inspect take-off outputs in the browser without downloading files first.

**Depends on:** Phase 1 (path sanitization patterns)

**Requirements:** PREV-01, PREV-02, PREV-03, PREV-04, PREV-05, PREV-06

**Success Criteria** (what must be TRUE):

1. User can view `summary.txt` rendered as styled HTML in the app
2. User can view `calculations.csv` and `raw_items.csv` as sortable, filterable tables
3. User can browse `takeoff.json` as a collapsible tree
4. Preview requests reject `../` and other path traversal attempts
5. Large CSV previews show a clear “showing N of M rows” cap with pagination or row limit

**Plans:** 3 plans (2 waves)

Plans:

- [ ] 05-01-PLAN.md — Preview endpoint with path validation (Wave 1)
- [ ] 05-02-PLAN.md — CSV pagination with row cap and total count (Wave 2)
- [ ] 05-03-PLAN.md — Security logging and error handling polish (Wave 2)

---

### Phase 6: Settings Management

**Goal:** Operators manage StackCT credentials, API keys, and output preferences through the app — not by SSH-editing `.env` alone.

**Depends on:** Phase 1

**Requirements:** SET-01, SET-02, SET-03, SET-04

**Success Criteria** (what must be TRUE):

1. User can view and update StackCT email/password in Settings
2. User can view and update Anthropic API key and default models
3. User can set output directory and screenshot retention preference
4. Saving settings persists to `.env` or config store; API never returns secret values in responses

**Plans:** Defined

Plans:

- [ ] 06-01: Settings read/write API with secret redaction (`settings.py` module + API routes)
- [ ] 06-02: Settings page form (`templates/settings.html` + `static/settings.js`, wired in Phase 8 shell)

---

### Phase 7: Live Job Monitoring

**Goal:** Users see exactly which sheet is running and what was extracted, without reading server logs.

**Depends on:** Phase 4 (selective runs); benefits from Phase 3 cost lines in log

**Requirements:** JOB-01, JOB-02, JOB-03, JOB-04

**Success Criteria** (what must be TRUE):

1. During a run, progress shows overall percentage and sheet index (e.g. 8/12)
2. Current sheet name updates while that sheet is processing
3. Per-sheet log lines appear (measurements, rooms, components found)
4. Sidebar shows an active-job mini-card whenever a job is running

**Plans:** Planned 2026-05-26

Plans:

- [ ] 07-01: Enrich scraper `progress_callback` / `log_callback` payloads
- [ ] 07-02: Job status API fields for current sheet and structured log
- [ ] 07-03: Sidebar mini-card component (Master §8.7)

---

### Phase 8: UI Shell Foundation

**Goal:** The app feels like a precision industrial tool with consistent navigation and maintainable front-end assets.

**Depends on:** Phase 1

**Requirements:** UI-01, UI-02, UI-03

**Success Criteria** (what must be TRUE):

1. Fixed sidebar navigation lists Projects, PDF Upload, Reports, and Settings
2. Visual design matches Master.md dark palette (DM Mono, Inter, JetBrains Mono)
3. Inline scripts and styles from `index.html` live in `static/app.js` and `static/style.css`

**Plans:** TBD

Plans:

- [ ] 08-01: Base layout template + sidebar (Master §8.2)
- [ ] 08-02: Theme tokens and typography (Master §8.1)
- [ ] 08-03: Extract and wire static assets (Master §10)

---

### Phase 9: Projects Workspace

**Goal:** The Projects page delivers the full StackCT workflow: pick scope, preview plans, select sheets, run.

**Depends on:** Phase 4, Phase 8

**Requirements:** UI-04

**Success Criteria** (what must be TRUE):

1. User toggles between “All Projects” and “Specific Project” scope modes
2. Specific-project mode shows searchable project list with sheet counts
3. “Preview Plans” opens the plan-selection panel integrated with Phase 4 APIs
4. “Run Selected” starts analysis only for checked `page_ids` from this page

**Plans:** Complete (2/2)

Plans:

- [x] 09-01: Projects page layout (Master §8.3) — depends on 08-01, 08-02, 08-03, 04-01
- [x] 09-02: Wire plan selection + run to Phase 4 backend — depends on 09-01, 04-01, 04-02

---

### Phase 10: Reports & Job Monitor UI

**Goal:** Reports and active jobs match Master layouts with in-browser preview and live monitor.

**Depends on:** Phase 5, Phase 7, Phase 8

**Requirements:** UI-05, UI-06

**Success Criteria** (what must be TRUE):

1. Reports page lists runs as expandable cards with Summary / Calculations / Raw / JSON tabs
2. Each preview tab uses Phase 5 APIs (sort, filter, search where specified in Master §7.1.2)
3. Dedicated job monitor view shows progress bar, current sheet, and scrollable per-sheet log (Master §8.4)
4. User can download CSV/JSON/TXT from report cards without losing preview context

**Plans:** DEFINED

Plans:

- [x] 10-01: Reports page + preview tabs (Master §8.5) → `.planning/phases/10-reports-job-monitor-ui/10-01-PLAN.md`
- [x] 10-02: Job monitor page/panel (Master §8.4) → `.planning/phases/10-reports-job-monitor-ui/10-02-PLAN.md`

---

### Phase 11: PDF Selection & Production Docs

**Goal:** PDF mode matches StackCT selectivity; production deployment is documented end-to-end.

**Depends on:** Phase 8 (PDF page in shell); Phase 4 pattern for page selection UX

**Requirements:** PDF-01, PDF-02, PDF-03, DEPLOY-02

**Success Criteria** (what must be TRUE):

1. User can upload a construction PDF and start analysis from the PDF Upload page
2. After upload, user selects specific pages before analysis starts (not all pages only)
3. UI shows page count and file size immediately after upload
4. README documents Hostinger VPS setup: gunicorn, Playwright system deps, `.env`, and headless Chrome flags

**Plans:** 11-01, 11-02, 11-03

Plans:

- [x] 11-01: PDF upload metadata + page checkbox UI (Master §8.6)
- [x] 11-02: Pass selected pages to `pdf_analyzer` / run endpoint
- [x] 11-03: README VPS deployment section (Master §11)

---

### Phase 12: Application Authentication

**Goal:** Every page and API endpoint requires authentication before use on a public VPS; operators sign in with seeded admin credentials using industry-standard session security.

**Depends on:** Phase 1 (config/env patterns), Phase 8 (UI shell for login page)

**Requirements:** AUTH-01 (promoted from v2)

**Success Criteria** (what must be TRUE):

1. Unauthenticated requests to any app route or `/api/*` receive 401/redirect to login (no anonymous access)
2. User can log in with seeded admin (`admin@bobbytailor.com`) and receive a secure server-side session
3. Passwords are stored only as bcrypt hashes; plaintext passwords never appear in logs or API responses
4. Session cookies use `HttpOnly`, `Secure` (when HTTPS), and `SameSite` protections; `SECRET_KEY` comes from environment
5. CSRF protection on state-changing forms and API calls from the browser
6. Failed login attempts are rate-limited; generic error messages (no user enumeration)
7. Logout invalidates the session; README documents auth env vars and production checklist

**Plans:** 3 plans in 3 waves

| Wave | Plans | Parallel | Description |
|------|-------|----------|-------------|
| 1 | 12-01 | — | Auth dependencies + seed_admin.py + env docs |
| 2 | 12-02 | — | Core auth module + app.py integration + login.html |
| 3 | 12-03 | — | Frontend CSRF, POST logout form, README auth section |

Plans:

- [x] 12-01-PLAN.md — Auth dependencies, seed_admin.py, .env.example, config.py validation
- [x] 12-02-PLAN.md — auth.py module, before_request guard, login/logout (POST), login.html
- [x] 12-03-PLAN.md — CSRF meta tags, apiFetch helper, sidebar logout, README auth docs

---

### Phase 13: StackCT Data & Persistence Layer

**Goal:** StackCT project and plan metadata lives in a queryable SQLite database with TTL sync and a single browser lock — so the UI serves project lists, sheet counts, and plan previews from cache without launching Playwright on every interaction.

**Depends on:** Phase 2 (reliable `get_all_projects` / `get_all_page_ids`), Phase 4 (plan selection APIs and UI patterns)

**Requirements:** DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, DATA-07, DATA-08, DATA-09

| ID | Requirement |
|----|-------------|
| DATA-01 | Projects catalog persisted in SQLite (`output/stackct.db`) |
| DATA-02 | Per-project plans (`page_id`, `sheet_name`) persisted with TTL |
| DATA-03 | Sheet counts available on project list without per-project preview scrape |
| DATA-04 | Sync operations recorded in `sync_runs` audit table |
| DATA-05 | Single global browser lock for all catalog sync (documented) |
| DATA-06 | Background stale refresh via startup prefetch + APScheduler interval |
| DATA-07 | One-time migration from `projects_cache.json` and `plans_cache/` |
| DATA-08 | APIs expose `from_cache`, `stale`, `syncing` metadata |
| DATA-09 | UI loads counts on project list; preview uses DB when fresh |

**Success Criteria** (what must be TRUE):

1. `GET /api/projects` serves from SQLite when TTL fresh; browser runs only on refresh/stale sync
2. `GET /api/projects/sheet-counts` returns counts from DB for all projects with synced plans (not only after UI preview)
3. `GET /api/projects/<id>/plans` returns cached plans from DB when fresh; preview does not require a new login if data exists
4. Manual refresh and background sync update `sync_runs` and `fetched_at` timestamps
5. Concurrent catalog operations serialize through one browser lock (no parallel Auth0 sessions)
6. JSON file caches migrated; normal code path does not read `output/projects_cache.json` for serving
7. SQLite contains no StackCT or Anthropic credentials

**Plans:** 4 plans in 4 waves

| Wave | Plans | Parallel | Description |
|------|-------|----------|-------------|
| 1 | 13-01 | — | SQLite schema + `stackct_store.py` + JSON migration |
| 2 | 13-02 | — | `stackct_sync.py` + browser lock + APScheduler |
| 3 | 13-03 | — | DB-first API routes + stale-while-revalidate |
| 4 | 13-04 | — | UI sheet counts + cached preview + human verify |

Plans:

- [x] 13-01-PLAN.md — SQLite schema, store module, migrate JSON caches
- [x] 13-02-PLAN.md — Sync service with locking, TTL, background refresh
- [x] 13-03-PLAN.md — Refactor `/api/projects`, sheet-counts, plans to DB-first
- [x] 13-04-PLAN.md — UI sheet counts on load; cached preview; sync controls

Research: `.planning/phases/13-stackct-data-persistence/13-RESEARCH.md`

---

## v2 (Out of Roadmap)

| Item | Notes |
|------|--------|
| ARCH-01 FastAPI migration | Deferred; Flask extensions for v1 |
| ARCH-02 Celery/Redis queue | Deferred |
| EST-*, AUTO-*, EXP-01 | See REQUIREMENTS.md v2 |

## Progress

**Execution order:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Config & Safe Operations | 3/3 | Complete | 2026-05-26 |
| 2. Browser Reliability | 3/3 | Complete | 2026-05-26 |
| 3. API Cost Transparency | 0/3 | Planned | — |
| 4. StackCT Plan Selection | 3/3 | Complete | 2026-05-26 |
| 5. Report Preview APIs | 3/3 | Complete | 2026-05-26 |
| 6. Settings Management | 2/2 | Complete | 2026-05-26 |
| 7. Live Job Monitoring | 3/3 | Complete | 2026-05-26 |
| 8. UI Shell Foundation | 3/3 | Complete | 2026-05-26 |
| 9. Projects Workspace | 0/TBD | Not started | — |
| 10. Reports & Monitor UI | 0/TBD | Not started | — |
| 11. PDF Selection & Production Docs | 0/TBD | Not started | — |
| 12. Application Authentication | 3/3 | Complete | 2026-05-26 |
| 13. StackCT Data & Persistence | 4/4 | Complete | 2026-05-26 |

---
*Roadmap created: 2026-05-26*  
*Aligned with Master.md Phase 1–3 ordering; Flask-in-place for v1*

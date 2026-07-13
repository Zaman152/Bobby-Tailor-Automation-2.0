# Roadmap: Bobby Tailor — StackCT Estimation Automation

## Overview

Brownfield upgrade of the Flask + Playwright take-off monolith to a shippable estimator tool: fix deployment and browser reliability first, add cost transparency and Master Phase 1 critical UX (plan selection, report preview), then layer settings, live job monitoring, and the industrial UI shell. v1 extends Flask in place; FastAPI migration (ARCH-01) stays in v2.

**Depth:** comprehensive (16 phases)  
**Stack:** Python, Flask, Playwright, Anthropic Claude Vision — per PROJECT.md  
**Source of truth:** `Masterv2.md` v2.0 + Addendum v2.1 (implementation order §7, UI spec §8, accuracy §C, agent steps §9)

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
- [ ] **Phase 14: StackCT Plan Sets** — Folder-first preview; plan set picker before sheets
- [ ] **Phase 15: Premium UI/UX Revamp** — Preview workspace, stepper, design system (Masterv2 §8)
- [ ] **Phase 16: Takeoff Accuracy (v2.1)** — Cross-refs, spec tables, consolidated summary (Masterv2 Addendum)
- [ ] **Phase 17: Production Takeoff Pipeline** — Screenshot reuse, two-phase capture/analyze, resume, demo-grade job UX
- [ ] **Phase 18: Linked Sheet Resolution** — Auto-follow drawing cross-refs; capture/analyze linked detail sheets
- [ ] **Phase 20: Takeoff Measurement Precision** — Plan-type-agnostic accurate take-offs; ≥97% golden regression; shared PDF+StackCT pipeline
- [ ] **Phase 21: Accuracy & Learning Engine (v3)** — Plans-only production accuracy: vector-first measurement, auto scale detection v2, ensemble vision, persistent human-verified learning loop replacing manifests, package restructure, live-testing readiness

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

### Phase 14: StackCT Plan Sets (Folder-First Preview)

**Goal:** Preview Plans follows StackCT’s real hierarchy: user picks a **plan set** (folder/version) inside the project, then sees and runs **only that set’s sheets** — never a flat merge of all folders.

**Depends on:** Phase 13 (SQLite catalog, browser lock), Phase 4 (plan selection + `page_ids` run filter)

**Requirements:** PLANSET-01, PLANSET-02, PLANSET-03, PLANSET-04, PLANSET-05, PLANSET-06, PLANSET-07, PLANSET-08

| ID | Requirement |
|----|-------------|
| PLANSET-01 | `browser.get_plan_sets` discovers deduplicated folders per project |
| PLANSET-02 | Pages synced and stored per `(project_id, folder_id, page_id)` |
| PLANSET-03 | API `GET .../plan-sets` and `GET .../plan-sets/<folder_id>/plans` |
| PLANSET-04 | UI shows plan set picker before sheet checklist |
| PLANSET-05 | Run API requires `folder_id` and validates `page_ids` |
| PLANSET-06 | Direct-grid fallback for projects without folder cards (e.g. ATL 081) |
| PLANSET-07 | Project list shows plan set count, not misleading merged sheet total |
| PLANSET-08 | Multi-project audit documented (`14-DISCOVERY.md`) |

**Success Criteria:**

1. Morehouse (7416168): Preview shows **2** sets (MSP3 v1 / v2); v2 loads **180** sheets, v1 loads **120**
2. Multi-set projects (6/7 in audit) show set picker; user cannot run mixed-folder `page_ids`
3. Single-set projects auto-select the only set and proceed to sheets
4. Cached catalog in SQLite includes `project_plan_sets` table; plans keyed by folder

**Plans:** 4 plans in 4 waves

| Wave | Plans | Parallel | Description |
|------|-------|----------|-------------|
| 1 | 14-01 | — | Browser plan-set discovery + folder-scoped pages + dedupe |
| 2 | 14-02 | — | SQLite schema v2 + sync |
| 3 | 14-03 | — | REST APIs + run validation |
| 4 | 14-04 | — | Two-step UI + human verify |

Plans:

- [ ] 14-01-PLAN.md — `get_plan_sets`, `get_page_ids_in_folder`, dedupe tests
- [ ] 14-02-PLAN.md — `project_plan_sets` table, folder-scoped sync
- [ ] 14-03-PLAN.md — `/plan-sets` APIs, `folder_id` on run
- [ ] 14-04-PLAN.md — Plan set picker UI, project list counts

Research: `.planning/phases/14-stackct-plan-sets/14-RESEARCH.md`  
Discovery: `.planning/phases/14-stackct-plan-sets/14-DISCOVERY.md` (7-project audit)

---

### Phase 15: Premium UI/UX Revamp

**Goal:** Transform the app into a premium estimator product — clear preview vs export actions, a full-screen **Report Preview Workspace** for analyzing calculations, guided plan-set workflow, polished monitor/settings, and Motion-driven interactions (vanilla JS; no React rewrite).

**Depends on:** Phase 8 (shell), Phase 5 (preview APIs), Phase 10 patterns (reports/monitor — superseded visually), Phase 14 (plan sets)

**Requirements:** UX-01, UX-02, UX-03, UX-04, UX-05, UX-06, UX-07, UX-08, UX-09, UX-10, UX-11, UX-12

| ID | Requirement |
|----|-------------|
| UX-01 | Design tokens v2 + dark industrial `design-system/bobby-tailor/MASTER.md` |
| UX-02 | Shared modal / drawer / toast primitives with a11y |
| UX-03 | Reports: preview CTA distinct from export/download |
| UX-04 | Full-screen report preview workspace (run list + tabs + export rail) |
| UX-05 | Calculations/raw: Grid.js-grade table (sort, filter, export selection) |
| UX-06 | URL deep-link for open report + tab |
| UX-07 | Projects: stepper Project → Plan set → Sheets → Run |
| UX-08 | Job monitor + sidebar mini-card polish |
| UX-09 | Motion system + `prefers-reduced-motion` |
| UX-10 | 21st.dev MCP components documented in execution |
| UX-11 | Responsive 375–1440 |
| UX-12 | Login / Settings / PDF visual parity |

**Success Criteria:**

1. User can instantly tell **Open preview** vs **Export/download** on every report card
2. Inside preview workspace, user switches Summary / Calculations / Raw / JSON **without losing context** and can switch runs from a side list
3. Calculations view supports sort, filter, confidence styling, formula visibility, export filtered CSV
4. Projects flow shows guided stepper for plan sets (Morehouse: 2 sets → pick → 180 sheets)
5. ui-ux-pro-max checklist + `15-UAT.md` signed off

**Plans:** 6 plans in 3 waves

| Wave | Plans | Parallel | Description |
|------|-------|----------|-------------|
| 1 | 15-01, 15-02 | yes | Design system + UI primitives |
| 2 | 15-03, 15-04 | yes | Report workspace + Projects stepper |
| 3 | 15-05, 15-06 | sequential | Shell pages polish → motion, 3D, UAT |

Plans:

- [ ] 15-01-PLAN.md — Design tokens, ui-polish.css, MASTER.md dark industrial
- [ ] 15-02-PLAN.md — Modal, drawer, toast, Motion extensions
- [ ] 15-03-PLAN.md — Report Preview Workspace + Grid.js analysis
- [ ] 15-04-PLAN.md — Projects stepper + plan-set UX
- [ ] 15-05-PLAN.md — Job monitor, login, settings, PDF polish
- [ ] 15-06-PLAN.md — Motion/3D, a11y, responsive, 15-UAT.md

Research: `.planning/phases/15-premium-ui-ux-revamp/15-RESEARCH.md`  
Design system: `design-system/bobby-tailor/MASTER.md`

**Tooling (execute phase):** ui-ux-pro-max skill, 21st.dev MCP (`21st_magic_component_builder`, `component_refiner`), Motion One CDN (existing `ui-motion.js`), optional Three.js on login only.

---

### Phase 16: Takeoff Accuracy (Masterv2 v2.1)

**Goal:** Production-accurate quantities — classify spec vs takeoff tables, resolve drawing cross-references, consolidate output to StackCT-style `takeoff_summary`, and handle civil/site items (pipe runs, structures, elevations) without false measurements.

**Depends on:** Phases 1–3 (calculator/reporter), Phase 5 (preview APIs; extended in 16-05). Best after Phase 15 for summary preview UX (can execute backend 16-01–04 in parallel with 15).

**Requirements:** ACCURACY-01 through ACCURACY-12

| ID | Requirement |
|----|-------------|
| ACCURACY-01 | Extraction prompt v2.1 (table_purpose, cross_references, pipe_runs, civil_structures) |
| ACCURACY-02 | Calculator skips non-takeoff schedule purposes |
| ACCURACY-03 | Specification tables stored as reference library in report |
| ACCURACY-04 | Cross-reference resolution pass for in-run sheets |
| ACCURACY-05 | `aggregator.py` consolidates calculated items by trade name |
| ACCURACY-06 | `takeoff_summary.csv` matches StackCT item/qty/unit format |
| ACCURACY-07 | Civil/site estimation tables in calculator |
| ACCURACY-08 | GL/INV/elevation values excluded from measurement math |
| ACCURACY-09 | Approximate (±) flag in calculations output |
| ACCURACY-10 | Pipe slope % not treated as quantity |
| ACCURACY-11 | Spec lookup enrichment for pipe/size matches |
| ACCURACY-12 | In-browser preview of consolidated takeoff summary |

**Success Criteria:**

1. Manufacturer/spec tables produce **zero** rows in `calculations.csv`
2. `takeoff_summary.csv` shows one row per trade item with **summed** quantity across sheets (e.g. total LF striping)
3. `takeoff.json` includes `cross_references` with `resolved_spec` or `target_sheet_not_found`
4. Civil drawing items (catch basin, pipe LF, trench drain) appear under correct item types — no GL=845 in calculations
5. `16-UAT.md` signed off against Masterv2 §C.7 matrix

**Plans:** 5 plans in 5 waves

| Wave | Plans | Parallel | Description |
|------|-------|----------|-------------|
| 1 | 16-01 | — | EXTRACTION_PROMPT v2.1 |
| 2 | 16-02 | — | Calculator guards + civil tables + numeric filters |
| 3 | 16-03 | — | Cross-reference resolver in scraper |
| 4 | 16-04 | — | aggregator.py + reporter outputs |
| 5 | 16-05 | — | Preview UI + 16-UAT.md |

Plans:

- [x] 16-01-PLAN.md — Replace extraction prompt (Masterv2 §C.8)
- [x] 16-02-PLAN.md — table_purpose guards, civil tables, elevation/slope filters
- [x] 16-03-PLAN.md — Cross-reference resolution pass
- [x] 16-04-PLAN.md — aggregate_takeoff + takeoff_summary.csv
- [x] 16-05-PLAN.md — Summary preview tab + accuracy UAT

Research: `.planning/phases/16-takeoff-accuracy-v21/16-RESEARCH.md`  
Gap analysis: `.planning/MASTERv2-GAP-ANALYSIS.md`

---

### Phase 17: Production Takeoff Pipeline

**Goal:** Takeoff runs are production-ready for client demos and VPS — reuse cached screenshots, capture all sheets before Claude analysis, survive per-sheet failures with partial reports, and resume from disk without re-login.

**Depends on:** Phase 2 (capture), Phase 4 (page selection), Phase 7 (job monitor), Phase 13 (catalog lock patterns), `sheet_preview.find_screenshot_paths`

**Requirements:** PIPE-01, PIPE-02, PIPE-03, PIPE-04, PIPE-05

| ID | Requirement |
|----|-------------|
| PIPE-01 | Reuse existing screenshots when `REUSE_SCREENSHOTS=true` (skip blob re-download) |
| PIPE-02 | Two-phase pipeline: bulk capture then analyze (browser closed before Claude) |
| PIPE-03 | `manifest.json` per run; analyze-only mode from manifest without browser |
| PIPE-04 | Phase-aware progress, cooperative cancel, partial report + UI warnings |
| PIPE-05 | Per-sheet resilience; sanitized filenames; user-facing job errors |

**Success Criteria:**

1. Re-run on a project with cached screenshots completes capture phase in under 30 seconds for 10 sheets
2. A 45-sheet job that fails on 3 sheets still produces `takeoff.json` and CSVs for the other 42
3. Sheet names with `/` or `\` never crash the job
4. Operator can re-analyze an interrupted run from disk without StackCT login
5. Job monitor shows Capturing / Analyzing / Reporting phases with accurate progress
6. `17-UAT.md` demo script signed off

**Plans:** 5 plans in 5 waves

| Wave | Plans | Parallel | Description |
|------|-------|----------|-------------|
| 1 | 17-01 | — | Screenshot reuse via find_screenshot_paths |
| 2 | 17-02 | — | Two-phase capture + manifest.json |
| 3 | 17-03 | — | Analyze-only / resume from manifest |
| 4 | 17-04 | — | Phase progress, cancel, monitor UX |
| 5 | 17-05 | — | Integration tests, README, UAT checkpoint |

Plans:

- [ ] 17-01-PLAN.md — REUSE_SCREENSHOTS + scraper cache integration
- [ ] 17-02-PLAN.md — capture_manifest.py + two-pass scraper
- [ ] 17-03-PLAN.md — analyze_only API + run_analyze_from_manifest
- [ ] 17-04-PLAN.md — Weighted progress, cancel, monitor polish
- [ ] 17-05-PLAN.md — Tests, README, 17-UAT.md human verify

Research: `.planning/phases/17-production-takeoff-pipeline/17-RESEARCH.md`  
Context: `.planning/phases/17-production-takeoff-pipeline/17-CONTEXT.md`  
Debug (demo failure): `.planning/debug/job-failure-slash-in-filename.md`

**Hotfix (pre-phase, landed):** Per-sheet error isolation, `_safe_sheet_filename`, partial reports, UI error messages — restart Flask to apply.

---

### Phase 18: Linked Sheet Resolution

**Goal:** Drawing cross-references (detail bubbles, civil structure refs) automatically pull in linked StackCT pages — capture, analyze, and resolve specs without the operator manually selecting every referenced sheet.

**Depends on:** Phase 16 (cross-ref extraction + resolver), Phase 17 (two-phase pipeline, manifest, reuse), Phase 13/14 (`stackct_store.get_plans`)

**Requirements:** LINK-01, LINK-02, LINK-03, LINK-04, LINK-05, LINK-06

| ID | Requirement |
|----|-------------|
| LINK-01 | Map `ref_sheet` codes to `page_id` via SQLite catalog + fuzzy sheet-name matching |
| LINK-02 | Collect refs from `cross_references[]` and `civil_structures[].detail_ref_sheet` |
| LINK-03 | `AUTO_INCLUDE_LINKED_SHEETS` + `MAX_LINKED_SHEETS` config (default include, cap cost) |
| LINK-04 | Linked capture/analyze pass in scraper before final cross-ref resolution |
| LINK-05 | Job + report metadata (`linked_sheets_added`); monitor notice |
| LINK-06 | Integration tests, README, `18-UAT.md` sign-off |

**Success Criteria:**

1. Run 5 sheets that reference C-4 detail → C-4 auto-captured/analyzed without manual selection
2. `takeoff.json` cross_references show `resolution_status: resolved` for in-catalog targets
3. `AUTO_INCLUDE_LINKED_SHEETS=false` → `linked_sheets_suggested[]` only, no extra Claude calls
4. `MAX_LINKED_SHEETS=2` truncates queue with log warning
5. Linked pass respects cancel and REUSE_SCREENSHOTS
6. `18-UAT.md` signed off

**Plans:** 5 plans in 5 waves

| Wave | Plans | Description |
|------|-------|-------------|
| 1 | 18-01 | `linked_sheets.py` matcher + collector + unit tests |
| 2 | 18-03 | Config flags + `PageEntry.source` on manifest |
| 3 | 18-02 | Scraper linked discover/capture/analyze pass |
| 4 | 18-04 | Reporter JSON, job API, monitor UI |
| 5 | 18-05 | Integration tests, README, UAT checkpoint |

Plans:

- [ ] 18-01-PLAN.md — ref_sheet → page_id matcher
- [ ] 18-02-PLAN.md — scraper linked pass (wave 3, after config)
- [ ] 18-03-PLAN.md — AUTO_INCLUDE_LINKED_SHEETS config (wave 2)
- [ ] 18-04-PLAN.md — report + monitor linked sheets UX
- [ ] 18-05-PLAN.md — tests, README, 18-UAT.md

Research: `.planning/phases/18-linked-sheet-resolution/18-RESEARCH.md`  
Context: `.planning/phases/18-linked-sheet-resolution/18-CONTEXT.md`

**Note:** Phase 17 UAT should complete first; Phase 18 builds on the production pipeline.

---

### Phase 18: Linked Sheet Auto-Follow

**Goal:** Production-ready handling of drawing cross-references — automatically discover linked detail sheets from Claude extraction, map ref_sheet codes to StackCT page_ids via catalog, capture/analyze linked pages, and resolve cross-references without requiring the operator to manually select every referenced sheet.

**Depends on:** Phase 16 (cross_references.py, prompt), Phase 17 (two-phase scraper, manifest, reuse, progress, cancel), Phase 13/14 (stackct_store.get_plans)

**Requirements:** LINK-01, LINK-02, LINK-03, LINK-04, LINK-05, LINK-06

**Success Criteria** (what must be TRUE):

1. `match_ref_to_page("C-4", catalog)` returns correct page_id via fuzzy normalization
2. After Pass 2 analyze, unresolved cross-ref targets are automatically captured and analyzed (Pass 2a/2b/2c)
3. `takeoff.json` contains `linked_sheets_added[]` and `linked_sheets_suggested[]`
4. `/api/status` exposes `linked_sheets_count`; monitor UI shows auto-add notice
5. `AUTO_INCLUDE_LINKED_SHEETS=false` surfaces suggestions only — no extra browser sessions
6. `MAX_LINKED_SHEETS` cap enforced; cancel/partial-report behavior unaffected
7. `18-UAT.md` sign-off

**Plans:** 5 plans in 5 waves

| Wave | Plans | Parallel | Description |
|------|-------|----------|-------------|
| 1 | 18-01 | — | linked_sheets.py matcher + collector + unit tests |
| 2 | 18-02 | — | Scraper Pass 2a/2b/2c integration (depends 18-01) |
| 3 | 18-03 | — | Config vars + PageEntry.source + .env.example (depends 18-02) |
| 4 | 18-04 | — | reporter JSON fields + /api/status + monitor UI (depends 18-02, 18-03) |
| 5 | 18-05 | — | Integration tests + README + 18-UAT.md human verify (depends 18-04) |

Plans:

- [ ] 18-01-PLAN.md — linked_sheets.py: match_ref_to_page + collect_unresolved_refs + unit tests
- [ ] 18-02-PLAN.md — scraper.py: _discover_and_add_linked_sheets + Pass 2a/2b/2c in run_project_scrape
- [ ] 18-03-PLAN.md — config.py AUTO_INCLUDE_LINKED_SHEETS/MAX_LINKED_SHEETS + PageEntry.source + .env.example
- [ ] 18-04-PLAN.md — reporter.py linked_sheets param + app.py job fields + static/app.js monitor notice
- [ ] 18-05-PLAN.md — Integration tests + README linked-sheet section + 18-UAT.md (human checkpoint)

Research: `.planning/phases/18-linked-sheet-resolution/18-RESEARCH.md`
Context: `.planning/phases/18-linked-sheet-resolution/18-CONTEXT.md`

---

### Phase 19: Job History & Run Archive

**Goal:** Persistent job history with a Job History tab — operators see past runs,
success/partial/failed/cancelled outcomes, errors/warnings, and links to reports; survives
Flask restart.

**Requirements:** HIST-01 through HIST-06

**Plans:** 5 plans in 5 sequential waves

Plans:

- [x] 19-01-PLAN.md — job_store.py (schema + outcome derivation + save/list/get) + config.py + app.py finalize hooks
- [x] 19-02-PLAN.md — app.py: GET /api/jobs/history list + GET /api/jobs/history/<job_id> detail endpoints
- [x] 19-03-PLAN.md — UI: Job History nav tab + list page + filter chips + table + detail expand panel + CSS badges
- [x] 19-04-PLAN.md — Polish: Open Report action, outcome summary line, row accent borders
- [~] 19-05-PLAN.md — Tests (test_job_store.py + test_job_history_api.py) + README.md + UAT checkpoint *(tests pass; UAT pending)*

Research: `.planning/phases/19-job-history/19-RESEARCH.md`
Context: `.planning/phases/19-job-history/19-CONTEXT.md`

---

### Phase 20: Takeoff Measurement Precision

**Goal:** Accurate quantity take-offs from **any** construction plan (PDF or StackCT) — industrial, retail, office, civil, MEP, residential, institutional — with ≥97% numeric accuracy on client golden regression fixtures (Crow Cass + Bob's Discount). No visual markup overlays required.

**Depends on:** Phase 16 (extraction prompt v2.1, aggregator, cross-refs), Phase 17 (PDF pipeline)

**Requirements:** ACCURACY-20-01 through ACCURACY-20-16

| ID | Requirement |
|----|-------------|
| ACCURACY-20-01 | Title-block sheet parsing (bottom-right region); generic code-reference noise filter (ASTM/NFPA/UL/IBC/ADA) |
| ACCURACY-20-02 | `takeoff_pipeline.py` + `sheet_pass_matrix.py` — shared orchestration for PDF and StackCT |
| ACCURACY-20-03 | PASS_MATRIX routes passes by `sheet_type` (8 types), not project name or `^[AS]\d` regex alone |
| ACCURACY-20-04 | Generalization test suite: synthetic JSON fixtures per sheet_type (CI, no API) |
| ACCURACY-20-05 | Golden CSV regression fixtures + GoldenValidator (Crow + Bob) |
| ACCURACY-20-06 | COUNT_PROMPT: discipline-agnostic EA counting; dimensions ≠ counts |
| ACCURACY-20-07 | SCHEDULE_PROMPT: any takeoff schedule (doors, equipment, panels, pipe sizing) |
| ACCURACY-20-08 | Content-first room mapping: notes/materials override project profile |
| ACCURACY-20-09 | PROJECT_TYPE_PROFILES: industrial, retail, office, civil, residential, institutional, mixed_use, auto |
| ACCURACY-20-10 | MEASURE_ADDENDUM: all linear run types (storm, gas, duct, conduit, striping, lintel, guard rail) |
| ACCURACY-20-11 | ITEM_NAME_MAP: full Masterv2 §C taxonomy (~70 entries) |
| ACCURACY-20-12 | StackCT scraper uses same TakeoffPipeline as pdf_analyzer (parity test) |
| ACCURACY-20-13 | MODEL_ROUTING by (sheet_type, pass) — Sonnet for elevation/detail/schedule |
| ACCURACY-20-14 | QuantityVerifier category sanity gate + optional VERIFY_PROMPT retry |
| ACCURACY-20-15 | title_sheet pages skipped (zero API cost) |
| ACCURACY-20-16 | No project-specific hardcoding (names, quantities, sheet numbers) in production code |

**Success Criteria** (what must be TRUE):

1. `pytest tests/test_takeoff_generalization.py -v` passes — all sheet_type synthetic fixtures
2. `pytest tests/test_golden_takeoff.py -v -m golden` ≥97% on Crow Cass and Bob's Discount (when PDFs present)
3. EA counts exact or ±1; SF/LF/CY within ±3%
4. Content-first: room tagged "sealed concrete" → Sealed Concrete regardless of profile
5. Civil site plans produce pipe/striping/basin items, not flooring
6. StackCT and PDF upload produce identical pass sequences for same sheet_type
7. `20-UAT.md` signed off: generalization matrix + golden regression matrix

**Plans:** 11 plans in 7 waves (8 core + 3 gap closure)

| Wave | Plans | Parallel | Description |
|------|-------|----------|-------------|
| 1 | 20-00, 20-01, 20-02 | yes | Shared pipeline + sheet ID fix + dual-layer tests |
| 2 | 20-03, 20-04 | yes | Generalized multi-pass prompts + content-first profiles |
| 3 | 20-05 | — | Full linear extraction + Masterv2 ITEM_NAME_MAP |
| 4 | 20-06 | — | Wire PDF + StackCT to TakeoffPipeline |
| 5 | 20-07 | — | Convergence: generalization 100% + golden ≥97% + UAT |
| 6 | 20-08, 20-09 | yes | **Gap:** scraper test parity + ITEM_NAME_MAP ≥68 entries |
| 7 | 20-10 | — | **Gap:** golden PDF regression ≥97% + UAT scores |
| 8 | 20-11, 20-12 | yes | **Gap:** companion take-off PDF + legend/verify high-accuracy passes |
| 9 | 20-13, 20-14 | yes | **Gap:** golden_convergence gate + auto-iterate to ≥97% |

Plans:

- [x] 20-00-PLAN.md — takeoff_pipeline.py + sheet_pass_matrix.py (shared orchestration)
- [x] 20-01-PLAN.md — Title-block parsing + generic noise patterns (pdf_analyzer.py)
- [x] 20-02-PLAN.md — GoldenValidator + generalization synthetic fixtures
- [x] 20-03-PLAN.md — COUNT/SCHEDULE prompts + merge_passes (claude_analyzer.py)
- [x] 20-04-PLAN.md — Content-first profiles (7 types + auto) (calculator.py)
- [x] 20-05-PLAN.md — MEASURE all linear types + full ITEM_NAME_MAP (aggregator.py)
- [x] 20-06-PLAN.md — PDF + StackCT pipeline wiring + QuantityVerifier
- [x] 20-07-PLAN.md — Both test layers pass + 20-UAT.md (human-verify checkpoint pending)
- [x] 20-08-PLAN.md — **Gap:** Scraper test parity + pytest isolation (ACCURACY-20-12)
- [x] 20-09-PLAN.md — **Gap:** ITEM_NAME_MAP ≥68 entries (ACCURACY-20-11)
- [x] 20-10-PLAN.md — **Gap:** Golden fixtures + UAT scores (human-verify: Crow 20%, Bob not run)
- [ ] 20-11-PLAN.md — **Gap:** Companion take-off PDF ingestion (generic)
- [ ] 20-12-PLAN.md — **Gap:** LEGEND pass + high-accuracy Sonnet routing
- [ ] 20-13-PLAN.md — **Gap:** golden_convergence.py automation gate
- [ ] 20-14-PLAN.md — **Gap:** Auto-iterate until ≥97% on golden fixtures

Research: `.planning/phases/20-takeoff-measurement-precision/20-RESEARCH.md` (§11–§13 generalization)
Context: `.planning/phases/20-takeoff-measurement-precision/20-CONTEXT.md`

---

### Phase 21: Accuracy & Learning Engine (v3)

**Goal:** In real client scenarios only the plan PDF exists — no companion take-off, no golden CSV, no hand-written manifest. Phase 21 makes plans-only runs production-accurate and self-improving: measurement moves from raster vision guessing to vector-geometry-first with vision as semantic labeler, drawing scale is auto-detected per viewport with confidence, EA counts use ensemble/tiled voting, and every human verification is persisted to a learning store that is retrieved on future runs — so the system learns item vocabularies, scales, wall heights, and correction patterns per project type and eventually replaces manifest files entirely. The codebase is restructured from 30 flat root modules into a proper package, and the app ships ready for live testing.

**Depends on:** Phase 16 (extraction prompts, aggregator), Phase 17 (two-phase pipeline), Phase 20 (shared TakeoffPipeline, scale modules, geometry_takeoff, benchmark harness)

**Requirements:** V3-ACC-01, V3-ACC-02, V3-ACC-03, V3-ACC-04, V3-ACC-05, V3-LEARN-01, V3-LEARN-02, V3-LEARN-03, V3-LEARN-04, V3-STRUCT-01, V3-STRUCT-02, V3-PROD-01, V3-PROD-02

| ID | Requirement |
|----|-------------|
| V3-ACC-01 | Vector-first measurement: SF/LF/areas computed from PDF vector geometry + text layer (dimension strings, room polygons, wall segments); vision labels semantics, never guesses numbers when geometry is available |
| V3-ACC-02 | Auto scale detection v2 with zero calibration: scale solved deterministically per viewport from dimension strings vs geometry, cross-validated against printed scale notation and known door widths; per-sheet scale confidence recorded and surfaced |
| V3-ACC-03 | Ensemble extraction: N-run self-consistency voting for EA counts and vision-measured quantities; tiled counting integrated with deduplication; disagreement lowers confidence and flags needs_review |
| V3-ACC-04 | Model upgrade & adaptive fidelity: strongest available Claude vision models routed by sheet complexity; adaptive DPI/tiling so dense sheets are analyzed at legible resolution within API limits |
| V3-ACC-05 | Verify-retry loop implemented (replaces ENABLE_VERIFY_RETRY stub): out-of-band quantities re-queried with targeted crops before flagging |
| V3-LEARN-01 | Correction store: human-verified overrides (quantities, names, scales, wall heights) persisted to SQLite keyed by project_type, sheet_type, item pattern — survives run deletion |
| V3-LEARN-02 | Learned vocabulary: canonical item names/units accumulated from verified runs replace static ITEM_NAME_MAP lookups over time; auto-generated project manifest from verified takeoffs |
| V3-LEARN-03 | Runtime feedback application: relevant learned corrections retrieved on new runs and injected into prompts, aggregation, and calculator assumptions (e.g. learned wall heights per project type) |
| V3-LEARN-04 | Manifest independence: companion take-off and manifest files become optional dev/benchmark inputs only; production plans-only path reaches target accuracy without them |
| V3-STRUCT-01 | Package restructure: root modules organized into src package (pipeline/, vision/, scale/, deterministic/, learning/, scrape/, web/) with Flask blueprints; all tests green after move |
| V3-STRUCT-02 | Entry-point parity: PDF upload and StackCT paths share identical pipeline behavior (deterministic legends, learning retrieval, ensemble settings) with a parity test |
| V3-PROD-01 | Plans-only accuracy gate: vision_only_benchmark integrated as CI-invocable gate; item-found ≥95% and quantity accuracy measurably improved per release; zero silent misses (every expected-category item present or flagged) |
| V3-PROD-02 | Live-testing readiness: reviewed-items workflow (human verifies only flagged subset), API cost budget guard per run, structured error recovery, deployment docs updated |

**Success Criteria** (what must be TRUE):

1. Uploading a plans-only PDF (no companion, no manifest, no calibration input) produces a complete takeoff where every detectable item, count, and measurement is extracted automatically — zero silent misses; anything genuinely indeterminable is explicitly flagged, and flagged items approach zero on vector CAD PDFs
2. On the Crow Cass and Bob's Discount fixtures run plans-only, quantities derived from vector geometry + text layer (footprints, wall LF/SF, schedule counts, printed legend quantities) are ≥97% accurate vs golden, with overall quantity accuracy ≥90% (from 40%/8% baseline), measured by scripts/vision_only_benchmark.py
3. Scale is auto-detected per viewport with zero human calibration — solved from dimension strings against geometry and cross-validated with printed scale notation and standard elements; on multi-scale sheets the main-plan viewport scale wins (Crow Cass resolves ~1"=20', not 1"=24' or detail scales)
4. After a human verifies a run, corrections persist in the learning store; a repeat run of the same project applies them automatically (names, quantities context, scale, wall heights) without any manifest file
5. Two identical runs of the same PDF produce quantity results within ±5% of each other (ensemble kills run-to-run variance)
6. All modules live in a structured package; `pytest` passes; app boots via blueprints; README documents the new layout
7. `21-UAT.md` signed off for live-testing readiness

**Plans:** TBD (planned via /gsd-plan-phase)

Research: `.planning/phases/21-accuracy-learning-engine/21-RESEARCH.md`
Context: `.planning/phases/21-accuracy-learning-engine/21-CONTEXT.md`

---

## v2 (Out of Roadmap)

| Item | Notes |
|------|--------|
| ARCH-01 FastAPI migration | Deferred; Flask extensions for v1 |
| ARCH-02 Celery/Redis queue | Deferred |
| EST-*, AUTO-*, EXP-01 | See REQUIREMENTS.md v2 |

## Progress

**Execution order:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → **15** → **16** → **17** → **18** → **19** → **20**

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
| 14. StackCT Plan Sets | 0/4 | In progress | — |
| 15. Premium UI/UX Revamp | 0/6 | Planned | — |
| 16. Takeoff Accuracy (v2.1) | 5/5 | Complete | 2026-05-26 |
| 17. Production Takeoff Pipeline | 4/5 | Awaiting UAT | 2026-06-02 |
| 18. Linked Sheet Resolution | 5/5 | Awaiting UAT | 2026-06-02 |
| 19. Job History & Run Archive | 0/5 | Planned | — |
| 20. Takeoff Measurement Precision | 8/8 | Verification gaps | 2026-06-04 |

---
*Roadmap created: 2026-05-26*  
*Updated: 2026-06-03 — Phase 20 Takeoff Measurement Precision added (7 plans, 5 waves)*  
*Aligned with Masterv2 Phase 1–3 ordering; Flask-in-place for v1*

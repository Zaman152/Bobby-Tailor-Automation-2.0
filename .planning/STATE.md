# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-05-26)

**Core value:** End-to-end automated take-off from StackCT drawings (or PDFs) producing traceable, formula-backed quantity calculations estimators can trust and export.

**Current focus:** Phase 18 planned (linked sheets); finish Phase 17 UAT first

## Current Position

Phase: 18 of 18 (Linked Sheet Resolution) — IN PROGRESS  
Plan: 1/5 complete  
Status: 18-01 executed (linked_sheets.py core module + 18 unit tests)  
Last activity: 2026-06-02 — Executed 18-01-PLAN.md

Progress: Phase 16 complete; Phase 15 still to execute for full premium shell

## Performance Metrics

**Velocity:**

- Total plans completed: 9 (Phase 3)
- Average duration: ~2.5 min/plan (Phase 3)
- Total execution time: ~7.5 min (Phase 3)

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 03-api-cost-transparency | 3 | 7.5 min | 2.5 min |

**Recent Trend:** Phase 3 executed in 3 sequential waves (03-01 → 03-02 → 03-03)

## Accumulated Context

### Decisions

From PROJECT.md Key Decisions (roadmap-relevant):

- Masterv2.md is planning source of truth (replaces Master.md for new work)
- Master Phase 1 critical UX (plan select + preview) before full UI shell — reflected in phases 4–5 before 8–10
- Keep Flask monolith; extract static JS/CSS on UI rebuild (Phase 8)
- FastAPI (ARCH-01) deferred to v2 per user directive

From 03-01 (Per-Sheet Usage Capture):

- Hardcoded PRICING dict with float rates (Haiku/Sonnet/Opus per MTok); default to Sonnet for unknown models
- Usage metadata on extraction dicts: `_tokens_in`, `_tokens_out`, `_cost_usd`, `_model_used`
- Error returns include zero-value usage fields for safe reporter aggregation

From 17-04 (Production Job UX):

- cancel_check Callable pattern: scraper reads jobs[job_id].get("_cancel") via lambda; _cancelled flag breaks sheet loop cleanly
- Partial-on-cancel: _cancelled=True in result dict; _finalize preserves "cancelled" status from endpoint; saves partial result with warning
- Weighted progress bands: capturing 0–40%, analyzing 40–90%, reporting 95%, done 100%

From 03-02 (Run-Level Aggregation):

- `api_usage` block in takeoff.json: total_cost_usd, tokens, cost_per_sheet, models_used
- Per-sheet cost in sheet_log (tokens_in, tokens_out, cost_usd, model_used)
- summary.txt includes "API USAGE & COST" section

From 03-03 (UI Cost Display):

- Report cards show cost in green (#4ade80) with 4-decimal USD precision
- list_reports() reads api_usage from takeoff.json; old runs without cost render gracefully

From 12-03 (Frontend CSRF Protection):

- apiFetch wrapper in app.js handles X-CSRFToken automatically for all state-changing calls
- settings.js keeps its own getCsrfToken() copy (self-contained page, no shared module)
- Logout form added to both templates as POST with csrf_token hidden field

From 12-02 (Core Flask Authentication):

- Timing-safe dummy bcrypt check on unknown email (prevents user enumeration)
- POST-only /logout to prevent CSRF via GET requests
- SESSION_COOKIE_SECURE conditional on FLASK_ENV != "development"

From 12-01 (Auth Dependencies & Admin Seeding):

- bcrypt rounds=12 for admin password hash (strong work factor, ~1s seeding time)
- RATE_LIMIT_STORAGE_URI defaults to memory://; Redis URI documented for multi-worker gunicorn
- SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD_HASH added to REQUIRED_ENV_VARS (crash-fail on missing)

From 14-01 (Plan-Set Discovery & Dedupe):

- Dedupe rules based on 14-DISCOVERY audit: drop "Plans X" parent, drop aggregate folders with multiple version labels
- Direct-grid fallback with folder_id=0 for projects without folder cards (ATL 081 pattern)
- Deprecated get_all_page_ids to use folder-aware APIs (prevents mixing multiple sets)

From 14-02 (Schema v2 & Folder-Aware Sync):

- Schema v2: project_plan_sets table, project_plans PK changed to (stackct_id, folder_id, page_id)
- v1→v2 migration drops project_plans table (re-sync required for all projects)
- sync_project_plans and get_project_plans now require folder_id parameter
- Background sync tracks (project_id, folder_id) tuples for parallel folder syncs

From 14-03 (Folder-First API Routes):

- GET /api/projects/<id>/plan-sets returns folder list
- GET /api/projects/<id>/plans now requires ?folder_id= (backward compat with 400 error)
- POST /api/run/stackct validates page_ids belong to folder
- folder_id stored in takeoff.json report root

From 14-04 (Two-Step Plan Selection UI):

- Two-step flow: plan sets → sheets (auto-skip for single-set projects)
- Project list shows "N sets · M sheets" instead of single sheet count
- Radio card picker with folder metadata visible
- Back button hidden for single-set projects

### Pending Todos

None yet.

### 17-01 Decisions

| Decision | Source |
|----------|--------|
| `REUSE_SCREENSHOTS` defaults to true; set false to force fresh downloads | 17-01 |
| `shutil.copy2` copies cached file to new run dir (preserves metadata) | 17-01 |
| Cache map built once before sheet loop via `find_screenshot_paths` | 17-01 |

### 17-03 Decisions

| Decision | Source |
|----------|--------|
| `{page_id}_analysis.json` cache beside screenshot; missing cache triggers re-analyze even when manifest says ok | 17-03 |
| analyze_only auto-discovers latest run folder by project_name prefix + mtime sort | 17-03 |
| `mode_detail: "full" \| "analyze_only"` on job dict for UI/log differentiation | 17-03 |
| `force=False` skips ok+cached pages; `force=True` re-runs all | 17-03 |

### 17-02 Decisions

| Decision | Source |
|----------|--------|
| Manifest saved after every page state change (crash-recovery foundation for 17-03) | 17-02 |
| Atomic tmp+replace write prevents corrupt JSON on mid-write crash | 17-02 |
| `screenshot_rel` stores filename only — `screenshots_dir` is run root | 17-02 |
| `browser_closed` flag in `finally` prevents double-close after Pass 1 | 17-02 |
| `phase="capturing"` in progress_callback during Pass 1 | 17-02 |

### Blockers/Concerns

- StackCT DOM brittleness (`#canvas-interaction`, `[data-page-id]`, Auth0) — mitigated in Phase 2
- Flask background-thread context leaks — use primitive payloads only in job threads (research PITFALLS #3)
- Claude schedule counting accuracy — document confidence limits; v2 review UI (EST-02)
- Pricing table may go stale — verify quarterly against Anthropic docs

## Session Continuity

Last session: 2026-06-02  
Stopped at: Completed 18-01-PLAN.md (linked_sheets.py core module)  
Resume file: `.planning/phases/18-linked-sheet-resolution/18-03-PLAN.md` (wave 2 next per wave order)

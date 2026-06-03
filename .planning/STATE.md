# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-05-26)

**Core value:** End-to-end automated take-off from StackCT drawings (or PDFs) producing traceable, formula-backed quantity calculations estimators can trust and export.

**Current focus:** Phase 20 — gap closure plan 20-08 complete; 20-09 and 20-10 remain

## Current Position

Phase: 20 of 20 (Takeoff Measurement Precision) — gap closure in progress  
Plan: 8/8 core complete; gap plan 20-08 complete; 20-09, 20-10 pending  
Status: 20-08 complete — ACCURACY-20-12 closed; run 20-09 and 20-10 next  
Last activity: 2026-06-04 — Completed 20-08-PLAN.md (pytest isolation fix)

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

### 20-00 Decisions

| Decision | Source |
|----------|--------|
| MODEL_ROUTING uses CLAUDE_MODEL_SCHEDULES config constant, not hardcoded slug | 20-00 |
| TakeoffPipeline accepts optional analyzer= callable (dependency injection for tests) | 20-00 |
| merge_passes defined as stub in takeoff_pipeline; canonical version moves to claude_analyzer in 20-03 | 20-00 |
| plan_passes returns copy of PASS_MATRIX list to prevent mutation of module constant | 20-00 |
| classify_sheet_type_from_text defaults to floor_plan when ambiguous (safest: runs count+measure) | 20-00 |

### 20-03 Decisions

| Decision | Source |
|----------|--------|
| COUNT_PROMPT returns `has_schedules` bool so TakeoffPipeline can conditionally invoke schedule pass | 20-03 |
| `analyze_drawing` default `pass_type="measure"` preserves all existing single-pass caller behavior | 20-03 |
| `_pick_model` deferred `MODEL_ROUTING` import avoids circular dependency with sheet_pass_matrix | 20-03 |
| Canonical `merge_passes` lives in `claude_analyzer`; `takeoff_pipeline` re-exports for backward compat | 20-03 |
| `merge_passes` uses `strip().lower()` for dedup keys to handle trailing whitespace in Claude output | 20-03 |

### 20-01 Decisions

| Decision | Source |
|----------|--------|
| Noise filter applied in BOTH title-block and full-page passes | 20-01 |
| `_is_noise_sheet_candidate` checks candidate within matched phrase context (not fullmatch on candidate alone) | 20-01 |
| `sheet_type_hint` in `get_pdf_metadata` is conditional on `sheet_pass_matrix` import (backward-compatible) | 20-01 |

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

### 20-06 Decisions

| Decision | Source |
|----------|--------|
| pdf_analyzer defers to TakeoffPipeline.run_project — no inline analyze_drawing loop | 20-06 |
| _page_to_image defined in pdf_analyzer (2× Matrix scaling) — was missing (bug fix) | 20-06 |
| scraper uses module-level _pipeline singleton (TakeoffPipeline()) for run_sheet calls | 20-06 |
| _detect_project_type called once after all sheets in both paths (uniform project_type) | 20-06 |
| Parity test uses source-level assertions + TakeoffPipeline injection (no real API calls) | 20-06 |

### 20-05 Decisions

| Decision | Source |
|----------|--------|
| MEASURE_ADDENDUM defined as named constant then concatenated to EXTRACTION_PROMPT | 20-05 |
| lintel_runs[] as dedicated array (not merged into pipe_runs[]) — separate calculator path | 20-05 |
| duct_lf and conduit_lf use 10% waste (vs 5% for gas/storm) — fittings add more equivalent LF | 20-05 |
| CMU Paint placed BEFORE CMU Wall in ITEM_NAME_MAP — both match \bcmu\b; first-match wins | 20-05 |
| Frame-HM placed BEFORE Doors-HM — "HM Door Frame" must not collapse to Doors-HM | 20-05 |
| Conduit LF / Duct LF placed BEFORE Storm Pipe — prevents PVC conduit matching \bpvc\b storm pattern | 20-05 |

### 20-04 Decisions

| Decision | Source |
|----------|--------|
| Content notes override profile skip_items — explicit drawing content always wins (VCT on industrial → flooring) | 20-04 |
| Floor/ceiling/wall handled as independent priority chains in _calculate_from_room | 20-04 |
| auto profile has empty default lists → universal fallback preserves pre-20-04 behavior | 20-04 |
| _detect_project_type uses keyword scoring across sheet_title + notes; ties → mixed_use | 20-04 |
| Gas pipe detected by material keyword (black steel/gas/csst); default → storm_pipe | 20-04 |

### Blockers/Concerns

- StackCT DOM brittleness (`#canvas-interaction`, `[data-page-id]`, Auth0) — mitigated in Phase 2
- Flask background-thread context leaks — use primitive payloads only in job threads (research PITFALLS #3)
- Claude schedule counting accuracy — document confidence limits; v2 review UI (EST-02)
- Pricing table may go stale — verify quarterly against Anthropic docs

## Session Continuity

Last session: 2026-06-04 19:58 UTC  
Stopped at: Completed 20-08-PLAN.md — ACCURACY-20-12 closed, conftest.py pytest isolation fix  
Resume file: None

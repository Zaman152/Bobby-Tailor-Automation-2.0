# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-05-26)

**Core value:** End-to-end automated take-off from StackCT drawings (or PDFs) producing traceable, formula-backed quantity calculations estimators can trust and export.

**Current focus:** Milestone v1.0 complete

## Current Position

Phase: 12 of 13 (Application Authentication) — complete  
Plan: 12-03 of 3 (3 complete)  
Status: Phase 12 complete — 12-01, 12-02, and 12-03 all complete
Last activity: 2026-05-26 — Completed 12-03-PLAN.md (CSRF meta tags, apiFetch wrapper, logout form, README auth)

Progress: [██████████] 100% (v1 phases 1–11 + 13; Phase 12 plan 01 complete)

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

- Master.md is planning source of truth
- Master Phase 1 critical UX (plan select + preview) before full UI shell — reflected in phases 4–5 before 8–10
- Keep Flask monolith; extract static JS/CSS on UI rebuild (Phase 8)
- FastAPI (ARCH-01) deferred to v2 per user directive

From 03-01 (Per-Sheet Usage Capture):

- Hardcoded PRICING dict with float rates (Haiku/Sonnet/Opus per MTok); default to Sonnet for unknown models
- Usage metadata on extraction dicts: `_tokens_in`, `_tokens_out`, `_cost_usd`, `_model_used`
- Error returns include zero-value usage fields for safe reporter aggregation

From 03-02 (Run-Level Aggregation):

- `api_usage` block in takeoff.json: total_cost_usd, tokens, cost_per_sheet, models_used
- Per-sheet cost in sheet_log (tokens_in, tokens_out, cost_usd, model_used)
- summary.txt includes "API USAGE & COST" section

From 03-03 (UI Cost Display):

- Report cards show cost in green (#4ade80) with 4-decimal USD precision
- list_reports() reads api_usage from takeoff.json; old runs without cost render gracefully

### Decisions

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

### Pending Todos

None yet.

### Blockers/Concerns

- StackCT DOM brittleness (`#canvas-interaction`, `[data-page-id]`, Auth0) — mitigated in Phase 2
- Flask background-thread context leaks — use primitive payloads only in job threads (research PITFALLS #3)
- Claude schedule counting accuracy — document confidence limits; v2 review UI (EST-02)
- Pricing table may go stale — verify quarterly against Anthropic docs

## Session Continuity

Last session: 2026-05-26 22:32 UTC  
Stopped at: Completed 12-03-PLAN.md — Phase 12 complete; ready for Phase 13  
Resume file: None

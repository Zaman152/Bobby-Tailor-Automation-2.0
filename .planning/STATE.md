# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-05-26)

**Core value:** End-to-end automated take-off from StackCT drawings (or PDFs) producing traceable, formula-backed quantity calculations estimators can trust and export.

**Current focus:** Phase 3 — API Cost Transparency

## Current Position

Phase: 3 of 11 (API Cost Transparency) — in progress  
Plan: 03-01 (1/3 complete)  
Status: In progress
Last activity: 2026-05-26 — Completed 03-01-PLAN.md

Progress: [███░░░░░░░] 33% (10/30 plans)

## Performance Metrics

**Velocity:**

- Total plans completed: 10
- Average duration: ~1.5 min
- Total execution time: ~12 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-config-and-safe-operations | 3 | 5 min | 1.7 min |
| 02-browser-reliability | 3 | ~5 min | ~1.7 min |
| 03-api-cost-transparency | 1 | 2 min | 2 min |

**Recent Trend:** Fast execution, 2min for cost tracking foundation (03-01)

## Accumulated Context

### Decisions

From PROJECT.md Key Decisions (roadmap-relevant):

- Master.md is planning source of truth
- Master Phase 1 critical UX (plan select + preview) before full UI shell — reflected in phases 4–5 before 8–10
- Keep Flask monolith; extract static JS/CSS on UI rebuild (Phase 8)
- FastAPI (ARCH-01) deferred to v2 per user directive

From 01-01 (Environment Configuration Hardening):

- Fail-fast on missing credentials with clear error messages (prevents silent operation with incomplete config)
- Cwd fallback for .env when project-root .env missing (improves portability)
- Empty string defaults for required vars with explicit validation (clearer error messages)

From 01-03 (Deployment Documentation):

- Added RUN_SCHEDULE with cron format documentation and examples (improves developer onboarding)
- Grouped environment variables by functional area in .env.example (better organization)
- Documented Pillow >=10.0.0 requirement for screenshot image processing (clarifies dependency purpose)

From 01-02 (Error Sanitization):

- Use generic error messages for all user-facing API responses while maintaining detailed server logs (prevents information leakage)
- Apply error sanitization to both synchronous routes (via Flask handlers) and background jobs (security consistency)
- Generic job error message "The job failed. Check server logs for details." keeps implementation simple while maintaining security

From 03-01 (API Cost Transparency Foundation):

- Default to Sonnet pricing for unknown models (conservative cost estimate)
- Use float literals in PRICING (1.0 not 1) to prevent integer division bugs
- Error paths return zero-value usage fields so reporter.py sum() never crashes
- Combined both tasks in single commit due to tight coupling in same file

### Pending Todos

None yet.

### Blockers/Concerns

- StackCT DOM brittleness (`#canvas-interaction`, `[data-page-id]`, Auth0) — mitigated in Phase 2
- Flask background-thread context leaks — use primitive payloads only in job threads (research PITFALLS #3)
- Claude schedule counting accuracy — document confidence limits; v2 review UI (EST-02)

## Session Continuity

Last session: 2026-05-26T16:05:01Z  
Stopped at: Completed 03-01-PLAN.md — ready for next plan (03-02)  
Resume file: None

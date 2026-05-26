# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-05-26)

**Core value:** End-to-end automated take-off from StackCT drawings (or PDFs) producing traceable, formula-backed quantity calculations estimators can trust and export.

**Current focus:** Phase 3 — API Cost Transparency

## Current Position

Phase: 8 of 11 (UI Shell Foundation) — complete  
Plans: 04-01 through 08-03 (14 plans executed in this session)  
Status: Phases 4–8 complete; Phase 3 (API Cost Transparency) still pending
Last activity: 2026-05-26 — Executed Phases 4–8 (`/gsd-execute-phase 4-8`)

Progress: [███████░░░] ~64% (7/11 phases complete — phases 1,2,4,5,6,7,8)

## Performance Metrics

**Velocity:**

- Total plans completed: 11
- Average duration: ~1.5 min
- Total execution time: ~13.5 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-config-and-safe-operations | 3 | 5 min | 1.7 min |
| 02-browser-reliability | 3 | ~5 min | ~1.7 min |
| 03-api-cost-transparency | 2 | 3.5 min | 1.75 min |

**Recent Trend:** Consistent 1.5-2min execution, cost tracking progressing smoothly

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

From 03-02 (Reporter Cost Aggregation):

- Use max(len(all_extracted), 1) for cost_per_sheet to prevent ZeroDivisionError on empty runs
- models_used dict counts sheets per model (not tokens) for distribution visibility
- Add cost to logger.info for at-a-glance run monitoring
- Backward-compatible .get() with defaults in summary generation (old reports still render)

### Pending Todos

None yet.

### Blockers/Concerns

- StackCT DOM brittleness (`#canvas-interaction`, `[data-page-id]`, Auth0) — mitigated in Phase 2
- Flask background-thread context leaks — use primitive payloads only in job threads (research PITFALLS #3)
- Claude schedule counting accuracy — document confidence limits; v2 review UI (EST-02)

## Session Continuity

Last session: 2026-05-26T21:00:00Z (Phases 4–8 execution)  
Stopped at: Phase 8 complete — all 14 plans from phases 4–8 executed  
Resume file: None

### Session Notes (Phases 4–8)

- Phase 3 (API Cost Transparency) was skipped — plans exist but not executed in this run
- Phases 4–8 executed with 14 commits total (11 feat + 5 docs)
- New files: settings.py, static/settings.js, static/style.css, static/app.js, templates/settings.html
- Modified: app.py, scraper.py, pdf_analyzer.py, project_cache.py, config.py, templates/index.html

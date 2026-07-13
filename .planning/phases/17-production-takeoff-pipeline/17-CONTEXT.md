# Phase 17 Context: Production Takeoff Pipeline

## Trigger

Client demo failure (2026-06-01): two StackCT jobs crashed at ~71% and ~80% with no reports generated. Root cause: sheet names containing `/` broke screenshot paths; entire job aborted on first fatal error.

## User requirements (from product owner)

1. **Reuse existing screenshots** when available — do not re-login and re-download for every run
2. **Capture all screenshots first, then process** — two-phase pipeline for faster demo feedback and safer retries
3. **Never lose an entire run** because one sheet fails — partial reports are acceptable
4. **Production-grade error handling** — clear UI messages, structured job log, recoverable failures

## Hotfix already landed (pre-phase)

- `_safe_sheet_filename()` — sanitizes `/`, `\`, illegal chars
- Per-sheet try/except — job continues on sheet failure
- Partial report generation when ≥1 sheet succeeds
- User-facing error messages in job monitor
- `browser.download_drawing_image` ensures parent dirs exist

## Out of scope for Phase 17

- Celery/Redis job queue (ARCH-02, v2)
- FastAPI migration (ARCH-01, v2)
- Multi-user concurrent jobs

## Depends on

- Phase 2 (browser capture reliability)
- Phase 4 (page_ids selection)
- Phase 7 (job monitoring UI)
- Phase 13 (SQLite catalog — plan list without browser when fresh)
- `sheet_preview.find_screenshot_paths()` (existing, UI-only today)

## Success definition

An operator can re-run a 45-sheet project demo in under 15 minutes when screenshots exist, get a partial or full report even if 2–3 sheets fail, and see actionable errors in the job monitor — not a stuck progress bar with zero output.

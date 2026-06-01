---
phase: 17-production-takeoff-pipeline
plan: "04"
subsystem: job-ux
tags: [progress, cancel, monitor, phase-badge, ux]
requires: ["17-02"]
provides: ["weighted-progress", "cooperative-cancel", "phase-badge-ui"]
affects: ["17-05"]
tech-stack:
  added: []
  patterns: ["cooperative-cancellation", "weighted-progress", "status-banner"]
key-files:
  created: []
  modified:
    - scraper.py
    - app.py
    - static/app.js
    - static/style.css
    - templates/index.html
decisions:
  - "_cancelled flag approach: scraper sets _cancelled=True on result dict; _finalize_stackct_job preserves 'cancelled' status from endpoint and saves partial result when ≥1 sheet succeeded"
  - "Weighted progress bands: capturing 0–40%, analyzing 40–90%, reporting 95%, done 100%"
  - "Phase badge separate from status badge: orange Capturing / blue Analyzing / green Reporting in monitor header"
metrics:
  duration: "8m 44s"
  completed: "2026-06-02"
---

# Phase 17 Plan 04: Production Job UX Summary

Phase-aware progress, cooperative cancellation, and clear partial-success messaging for client demos.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Weighted progress + current_phase in job API | a1dbc00 | scraper.py, app.py |
| 2 | Cooperative cancel between sheets | a1dbc00 | scraper.py, app.py |
| 3 | Monitor UI phase badge + error styling | b202243 | app.js, style.css, index.html |

## What Was Built

### Task 1: Weighted Progress + current_phase

- `_weighted_progress(idx, total, phase)` helper in `scraper.py`: capturing → 0–40%, analyzing → 40–90%, reporting → 95%, done → 100%
- `_weighted_pct()` nested in `_stackct_job` applies the same bands when the progress callback fires
- `jobs[job_id]["current_phase"]` updated on every progress callback call
- `/api/status/<job_id>` now returns `current_phase` (falls back to `current_sheet.phase`)
- Prevents the progress bar from appearing frozen at 2% while Claude processes long sheets

### Task 2: Cooperative Cancellation

- `cancel_check: Optional[Callable[[], bool]] = None` added to both `run_project_scrape` and `run_analyze_from_manifest`
- `cancel_check()` called after each sheet in PASS 1 (capture), between PASS 1 and PASS 2, and after each sheet in PASS 2
- A `_cancelled` flag breaks the loop cleanly — no zombie browser sessions (browser already closed after PASS 1)
- Cancelled with ≥1 analyzed sheet → partial report generated with `_cancelled=True`
- Cancelled with no analyzed sheets → `{"_cancelled": True, "error": "cancelled"}`
- `_finalize_stackct_job` preserves "cancelled" status set by the endpoint; attaches partial result with amber warning when available

### Task 3: Monitor UI Phase Badge + Error Styling

- `<span class="phase-badge" id="monitorPhaseBadge">` added to monitor header right side
- `updateMonitorUI` reads `job.current_phase` and renders phase label: Capturing (orange), Analyzing (blue), Reporting (green)
- Sheet line verb switches: "Capturing: Sheet X" or "Analyzing: Sheet X" based on phase
- `handleJobCompletion` reworked with three banner variants:
  - Cancelled + partial result → amber `monitor-warning-banner` + auto-redirect to Reports
  - Error → red `monitor-error-banner`
  - Done with warning → amber banner; Done clean → green success text
- `style.css` adds `.phase-badge`, `.phase-capturing/analyzing/reporting`, `.monitor-error-banner`, `.monitor-warning-banner`, `.monitor-success-text`

## Deviations from Plan

None — plan executed exactly as written.

## Must-Have Verification

| Truth | Status |
|-------|--------|
| Job monitor shows current phase: Capturing / Analyzing / Reporting | ✓ Phase badge in header + verb in current-sheet line |
| Weighted progress bar reflects phase (not just sheet index) | ✓ 0–40% / 40–90% / 95% bands |
| Cancel flag checked between sheets — job stops cleanly | ✓ cancel_check() after each sheet iteration |
| Partial completion shows warning and still opens Reports | ✓ Amber banner + redirect when has_result=true |

| Artifact | Status |
|----------|--------|
| static/app.js contains `current_phase` | ✓ line 555 |
| scraper.py contains `_cancel` | ✓ lines 313–470 |

## Next Phase Readiness

Plan 17-05 can proceed. No blockers.

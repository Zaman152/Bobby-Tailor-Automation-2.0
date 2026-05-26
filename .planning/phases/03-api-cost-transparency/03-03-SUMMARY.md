---
phase: 03-api-cost-transparency
plan: 03
subsystem: reporting-ui
tags: [cost-display, web-ui, frontend, api-integration]

# Dependency graph
requires:
  - phase: 03-02
    provides: Run-level cost aggregation (total_cost_usd, sheets_processed in takeoff.json)
provides:
  - Per-run cost display in web UI report cards
  - API response includes cost and sheets count for each run
  - Green-highlighted cost ($X.XXXX) alongside metadata in report list
affects: [Phase 4+ that build on web UI report features]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cost display inline with report metadata (timestamp, sheets, cost, folder)"
    - "Graceful fallback to null for old runs without api_usage"

key-files:
  created: []
  modified:
    - app.py
    - static/app.js
    - static/style.css

key-decisions:
  - "Display cost with .toFixed(4) for consistent 4-decimal USD precision"
  - "Use green color (#4ade80) for cost to make it visually distinct"
  - "Null check (r.total_cost_usd != null) prevents crash on old runs"

patterns-established:
  - "Report card metadata format: timestamp · sheets · cost · folder"
  - "Green color (#4ade80) as standard for cost display elements"

# Metrics
duration: 4 min
completed: 2026-05-26
---

# Phase 3 Plan 03: API Cost Transparency Summary

**Per-run API cost ($X.XXXX) displayed in green alongside sheets count and timestamp in web UI report cards**

## Performance

- **Duration:** 4 min
- **Started:** 2026-05-26T16:12:15Z
- **Completed:** 2026-05-26T16:16:51Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- API response includes total_cost_usd and sheets_processed for each run
- Report cards display cost inline with metadata in green (#4ade80)
- Old runs without api_usage render gracefully (no crash, no blank cost)
- Consistent 4-decimal precision matching backend cost calculation

## Task Commits

Each task was committed atomically:

1. **Task 1: Include api_usage in list_reports() API response** - `c57c111` (feat)
2. **Task 2: Display cost in report card UI** - `5c87f97` (feat)

**Plan metadata:** (pending - next step)

## Files Created/Modified
- `app.py` - list_reports() reads api_usage from takeoff.json, adds total_cost_usd and sheets_processed to API response
- `static/app.js` - loadReports() renders cost and sheets count inline with timestamp
- `static/style.css` - Added report-card styles for modern card layout

## Decisions Made

**Display cost with .toFixed(4) for 4-decimal precision**
- Matches backend cost calculation precision (rounded to 4 decimals)
- Consistent with Master.md Feature 2.1 cost display expectations
- Example: $0.1234 instead of $0.123 or $0.12

**Use green color (#4ade80) for cost**
- Makes cost visually distinct from other metadata
- Green conveys positive/informational (not error/warning)
- Matches plan specification for cost display color

**Null check prevents crash on old runs**
- `r.total_cost_usd != null` check before rendering cost
- Old runs without api_usage show no cost (graceful degradation)
- No migration needed for historical reports

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**COST-03 satisfied.** Estimators can now see per-run API cost before downloading any files.

Cost transparency pipeline complete:
1. claude_analyzer.py captures tokens/cost per sheet (03-01)
2. reporter.py aggregates and writes to takeoff.json (03-02)
3. app.py API serves cost data, web UI displays it (03-03)

Ready for Phase 4 (UI shell foundation) which will build on this report list infrastructure.

---
*Phase: 03-api-cost-transparency*
*Completed: 2026-05-26*

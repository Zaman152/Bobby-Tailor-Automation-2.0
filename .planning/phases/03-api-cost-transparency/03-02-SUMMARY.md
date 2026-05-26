---
phase: 03-api-cost-transparency
plan: 02
subsystem: reporting
tags: [cost-tracking, api-usage, token-counting, aggregation]

# Dependency graph
requires:
  - phase: 03-01
    provides: Per-sheet cost capture (_cost_usd, _tokens_in, _tokens_out, _model_used)
provides:
  - Run-level cost aggregation (total_cost_usd, total_tokens_in, total_tokens_out)
  - models_used dict showing model distribution across sheets
  - api_usage block in takeoff.json
  - API USAGE & COST section in summary.txt
  - Per-sheet cost tracking in sheet_log
affects: [Phase 4+ that read takeoff.json or summary.txt for cost analysis]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cost aggregation via sum() over extraction dicts with zero-value defaults"
    - "Backward-compatible .get() with defaults in summary generation"

key-files:
  created: []
  modified:
    - reporter.py

key-decisions:
  - "Use max(len(all_extracted), 1) denominator to prevent ZeroDivisionError on empty runs"
  - "models_used dict counts sheets per model (not tokens) for distribution visibility"
  - "Add cost to logger.info for at-a-glance run monitoring"

patterns-established:
  - "api_usage block structure: total_cost_usd, total_tokens_in/out, cost_per_sheet, models_used"
  - "Per-sheet cost fields: tokens_in, tokens_out, cost_usd, model_used in sheet_log"

# Metrics
duration: 1.5 min
completed: 2026-05-26
---

# Phase 3 Plan 02: Reporter Cost Aggregation Summary

**Run-level API cost aggregation in takeoff.json and summary.txt with per-sheet token tracking and model distribution**

## Performance

- **Duration:** 1.5 min
- **Started:** 2026-05-26T16:07:35Z
- **Completed:** 2026-05-26T16:09:05Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- Aggregate total_cost_usd, total_tokens_in, total_tokens_out across all extraction dicts
- Add models_used dict mapping model names to sheet counts (e.g., `{"gpt-4o": 5, "gpt-4o-mini": 2}`)
- Insert api_usage block in takeoff.json report dict with cost_per_sheet calculation
- Add per-sheet tokens_in, tokens_out, cost_usd, model_used to sheet_log entries
- Insert API USAGE & COST section in summary.txt between header and sheet log
- Update logger.info to show total cost and token count at run completion

## Task Commits

Each task was committed atomically:

1. **Task 1: Add api_usage aggregation and per-sheet cost to generate_report()** - `043e4ce` (feat)
2. **Task 2: Add API USAGE & COST section to _write_summary()** - `7feb458` (feat)

**Plan metadata:** `7a207e7` (docs: complete plan)

## Files Created/Modified
- `reporter.py` - Run-level cost aggregation in generate_report(), cost section in _write_summary(), per-sheet cost fields in sheet_log

## Decisions Made

**Use max(len(all_extracted), 1) for cost_per_sheet denominator**
- Prevents ZeroDivisionError if run completes with zero sheets
- Returns 0.0000 cost_per_sheet for empty runs (semantically correct)

**models_used counts sheets per model, not tokens**
- Provides distribution visibility (how many sheets used each model)
- Complements token totals which show volume per model
- Example: `{"gpt-4o": 5, "gpt-4o-mini": 2}` means 5 sheets used 4o, 2 used mini

**Add cost to logger.info output**
- Estimators monitoring logs see cost at-a-glance without opening JSON
- Format: `[Total cost: $0.0234, 12,456 tokens]`

**Backward-compatible .get() with defaults in summary generation**
- Old reports lacking api_usage block still render (shows zeros)
- No migration needed for historical takeoff.json files

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**COST-02 (run-level USD total) and COST-04 (api_usage in takeoff.json) are satisfied.**

Ready for 03-03: Budget thresholds and cost alerts (COST-03, COST-05).

Per-sheet and run-level cost data now flows through the full pipeline:
1. claude_analyzer.py captures tokens/cost per sheet (03-01)
2. reporter.py aggregates and surfaces in outputs (03-02)
3. Next: Budget controls and alerts before runs exceed limits (03-03)

---
*Phase: 03-api-cost-transparency*
*Completed: 2026-05-26*

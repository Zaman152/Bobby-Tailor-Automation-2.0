---
phase: 03-api-cost-transparency
plan: 01
subsystem: api
tags: [claude, anthropic, cost-tracking, api-usage, observability]

# Dependency graph
requires:
  - phase: 01-config-and-safe-operations
    provides: ANTHROPIC_API_KEY configuration
  - phase: 02-browser-reliability
    provides: Stable StackCT automation for drawing analysis
provides:
  - Per-sheet Claude API usage metadata (_tokens_in, _tokens_out, _cost_usd, _model_used)
  - PRICING dictionary for cost calculation across model tiers
  - Zero-value usage fields in error returns for safe aggregation
affects: [05-reporting, reporter.py aggregation]

# Tech tracking
tech-stack:
  added: []
  patterns: 
    - "Model-specific pricing lookup with Sonnet fallback"
    - "Usage metadata capture in extraction dicts for downstream aggregation"

key-files:
  created: []
  modified: 
    - claude_analyzer.py

key-decisions:
  - "Default to Sonnet pricing for unknown models (conservative cost estimate)"
  - "Use float literals in PRICING (1.0 not 1) to prevent integer division bugs"
  - "Error paths return zero-value usage fields so reporter.py sum() never crashes"
  - "Combined both tasks in single commit due to tight coupling in same file"

patterns-established:
  - "Usage capture pattern: extract response.usage, lookup pricing, calculate cost, append to result dict"
  - "Error hardening pattern: zero-value usage fields in all error returns"

# Metrics
duration: 2min
completed: 2026-05-26
---

# Phase 3 Plan 1: API Cost Transparency Foundation Summary

**Claude API usage capture with per-sheet token counts and model-specific cost calculation**

## Performance

- **Duration:** 2 min
- **Started:** 2026-05-26T16:03:33Z
- **Completed:** 2026-05-26T16:05:01Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- PRICING dictionary with Haiku (1.0/5.0), Sonnet (3.0/15.0), Opus (5.0/25.0) per-1M-token rates
- Usage capture after API call: input_tokens, output_tokens from response.usage
- Cost calculation: (input_tokens × rate_in + output_tokens × rate_out) / 1M with 6-digit precision
- Four usage fields (_tokens_in, _tokens_out, _cost_usd, _model_used) added to every extraction dict
- Enhanced logger showing "[N in / M out tokens, $X.XXXXXX]" per sheet
- Hardened error returns: JSONDecodeError includes actual usage (API succeeded), Exception returns zeros

## Task Commits

Both tasks committed together due to tight coupling in same file modification:

1. **Tasks 1 & 2: Add PRICING and harden error returns** - `1046dd7` (feat)
   - Added PRICING dict with model-specific rates
   - Captured usage after API call and calculated cost
   - Added _tokens_in, _tokens_out, _cost_usd, _model_used to extraction dict
   - Hardened JSONDecodeError handler with actual usage values
   - Hardened Exception handler with zero-value defaults

**No metadata commit yet** - will be created after SUMMARY.md complete

## Files Created/Modified
- `claude_analyzer.py` - Added PRICING dict (line 14-18), usage capture and cost calculation (line 221-226), four usage fields in extraction dict (line 229-232), enhanced logging (line 234-236), hardened error returns with usage fields (line 239-252)

## Decisions Made
- **Default to Sonnet pricing for unknown models:** Conservative cost estimate using `PRICING.get(model, {"in": 3.0, "out": 15.0})` prevents crashes on new/experimental models
- **Float literals in PRICING:** Using 1.0 instead of 1 prevents Python integer division bugs in cost calculation
- **Zero-value usage in error paths:** JSONDecodeError includes actual usage (API call succeeded), Exception returns zeros (API call failed) - ensures reporter.py aggregation never crashes on KeyError or None
- **Combined commit for both tasks:** Both tasks modify same section of same file with tight coupling (Task 2 hardens code added in Task 1), so single atomic commit is more coherent than artificial split

## Deviations from Plan

### Process Deviation

**[Minor] Combined tasks in single commit instead of two atomic commits**
- **Found during:** Execution flow
- **Issue:** Task commit protocol specifies one commit per task, but both tasks modified same file section with tight coupling
- **Rationale:** Task 2 directly hardens error paths added in Task 1's usage capture code - splitting into two commits would create intermediate state where usage capture exists but error handling is incomplete (poor git bisect experience)
- **Impact:** Git history has one commit instead of two, but all work is traceable and verifiable
- **Verification:** Single commit includes all required changes from both tasks (36 insertions: PRICING dict, usage capture, cost calculation, four usage fields, enhanced logging, hardened error returns)
- **Commit:** 1046dd7

---

**Total deviations:** 1 process deviation (combined commits for coherent atomic change)
**Impact on plan:** No functional deviations. All specified work completed. Single commit more coherent than artificial split.

## Issues Encountered
None - implementation straightforward, all verifications passed

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- **Ready for Phase 3 Plan 2:** reporter.py can now aggregate _cost_usd across all sheets to display run-level totals
- **Data contract established:** Every analyze_drawing() return (success or error) includes _tokens_in, _tokens_out, _cost_usd, _model_used
- **No blockers**

---
*Phase: 03-api-cost-transparency*
*Completed: 2026-05-26*

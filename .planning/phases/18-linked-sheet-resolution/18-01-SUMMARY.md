---
phase: 18-linked-sheet-resolution
plan: "01"
subsystem: linked-sheet-resolution
tags: [linked-sheets, fuzzy-matching, ref-collection, pure-python, unit-tests]

dependency-graph:
  requires:
    - 16-takeoff-accuracy-v21   # cross_references extraction + resolver foundation
    - 17-production-takeoff-pipeline  # two-phase pipeline, manifest, progress
    - 14-stackct-plan-sets      # get_plans catalog API
  provides:
    - match_ref_to_page function (ref_sheet code → catalog page_id via fuzzy scoring)
    - collect_unresolved_refs function (harvest all ref_sheet codes from extractions)
  affects:
    - 18-02-PLAN  # scraper integration: call these two functions between analyze + report pass
    - 18-03-PLAN  # config + env vars for AUTO_INCLUDE_LINKED_SHEETS / MAX_LINKED_SHEETS
    - 18-04-PLAN  # job dict + API surface for linked_sheets_added
    - 18-05-PLAN  # README + UAT

tech-stack:
  added: []
  patterns:
    - score-based fuzzy matching with difflib near-miss fallback
    - case/punctuation normalization via _normalize() helper
    - dedup by normalized key (first-occurrence wins)

key-files:
  created:
    - linked_sheets.py
    - tests/test_linked_sheets.py
  modified: []

decisions:
  - "Scoring: prefix match=3, substring=2, suffix=1; ties broken by shortest sheet_name"
  - "Normalization replaces / and . with - to unify refs like 3/A5 and I-4.1 with catalog names"
  - "collect_unresolved_refs does NOT filter by already_in_run — caller does that after match"
  - "Deduplication key is normalized (uppercase+stripped) ref_sheet; first occurrence kept"
  - "match_ref_to_page never calls get_plans() internally — caller passes catalog"

metrics:
  duration: "~2 min"
  completed: "2026-06-02"
---

# Phase 18 Plan 01: Linked Sheet Core Matching Module Summary

**One-liner:** Score-based fuzzy matcher (`match_ref_to_page`) and extraction ref collector (`collect_unresolved_refs`) — pure Python, no browser, 18 unit tests all green.

## What Was Built

`linked_sheets.py` provides two public functions that `scraper.py` (Phase 18-02) will call:

### `match_ref_to_page(ref_sheet, catalog)`

Maps a short ref code (e.g. `"C-4"`, `"3/A5"`, `"I-4.1"`) to a catalog entry from `stackct_store.get_plans()`:

1. **Normalize**: uppercase, strip, replace `/` and `.` with `-`
2. **Score each catalog entry**:
   - 3 pts — sheet prefix (before ` - `) equals normalized ref
   - 2 pts — ref is a substring of normalized sheet_name
   - 1 pt  — normalized sheet_name ends with ref
3. **Select**: highest score; ties → shortest sheet_name
4. **No match**: log WARNING with `difflib.get_close_matches` near-miss candidates; return `None`

### `collect_unresolved_refs(all_extracted, already_in_run)`

Walks all extraction dicts and collects refs from:
- `extracted["cross_references"][].ref_sheet` (tagged `source="cross_ref"`)
- `extracted["civil_structures"][].detail_ref_sheet` (tagged `source="civil_structure"`)

Deduplicates by normalized key; excludes empty/None refs. Returns list of `{ref_sheet, from_sheet, source}` records. Filtering by `already_in_run` is the **caller's** responsibility after page_id matching.

## Test Coverage

18 tests across two test classes in `tests/test_linked_sheets.py`:

| Class | Tests |
|-------|-------|
| `TestMatchRefToPage` | 9 |
| `TestCollectUnresolvedRefs` | 9 |

All 18 pass in 0.02s.

## Commits

| Hash | Message |
|------|---------|
| `ccf3146` | feat(18-01): create linked_sheets.py with matcher + collector |
| `dc3c90b` | test(18-01): add unit tests for linked_sheets matcher and collector |

## Deviations from Plan

None — plan executed exactly as written.

## Next Phase Readiness

Phase 18-02 (scraper integration) can proceed immediately:

- `match_ref_to_page` and `collect_unresolved_refs` are importable and tested
- Caller pattern: `collect_unresolved_refs(all_extracted, manifest_page_ids)` → match each ref → filter against `already_in_run` → queue linked captures
- No breaking changes to existing modules

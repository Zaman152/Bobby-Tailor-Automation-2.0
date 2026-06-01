---
phase: 18-linked-sheet-resolution
plan: "02"
subsystem: scraper
tags:
  - linked-sheets
  - cross-references
  - scraper
  - browser-automation
  - claude-analysis

dependencies:
  requires:
    - 18-01  # linked_sheets.py (collect_unresolved_refs, match_ref_to_page)
    - 18-03  # AUTO_INCLUDE_LINKED_SHEETS, MAX_LINKED_SHEETS in config.py; PageEntry.source
  provides:
    - _discover_and_add_linked_sheets helper in scraper.py
    - Pass 2a/2b/2c block in run_project_scrape
    - linked_sheets_added / linked_sheets_suggested in report result dict
  affects:
    - 18-04  # reporter wires linked_sheets_added into takeoff.json
    - 18-05  # UI surfaces linked sheet info in report cards

tech-stack:
  added: []
  patterns:
    - Linked sheet mini-passes (2a discover / 2b capture / 2c analyze) inserted between Pass 2 and Pass 3

file-tracking:
  created: []
  modified:
    - scraper.py

decisions:
  - Catalog empty → log WARNING and return ([], [], []) rather than crash; caller continues to Pass 3
  - Browser lifecycle: helper opens + closes its own browser; browser_closed flag in caller unaffected
  - Pass 2b uses same cached_screenshots map as Pass 1 for linked pages
  - Pass 2c appends to all_extracted/all_estimates in caller after helper returns
  - linked_meta entries carry suggested_only=True when AUTO_INCLUDE_LINKED_SHEETS=false
  - report["linked_sheets_added"] and report["linked_sheets_suggested"] set unconditionally after generate_report()
  - cancel_check respected at every loop boundary in both 2b and 2c

metrics:
  duration: "~8 min"
  completed: "2026-06-02"
---

# Phase 18 Plan 02: Linked Sheet Integration into Scraper Summary

**One-liner:** `_discover_and_add_linked_sheets` helper + Pass 2a/2b/2c block wired into `run_project_scrape` between analyze and resolve, surfacing cross-reference targets as captured/analyzed pages or suggested-only metadata.

## Objective

Insert three linked-sheet mini-passes between Pass 2 (analyze) and Pass 3 (resolve/report) in `scraper.py` so that cross-reference targets are automatically discovered, captured via browser, and analyzed with Claude before resolution runs.

## What Was Built

### `_discover_and_add_linked_sheets` helper (scraper.py, line 141)

A new `async` helper implementing three sub-passes:

**Pass 2a — Discover:**
- Calls `collect_unresolved_refs(all_extracted, already_in_run)` to harvest all `ref_sheet` codes from Claude extractions not yet in the run
- Loads catalog via `stackct_store.get_plans(project_id, folder_id)`; logs WARNING and returns early if catalog is empty (DB not synced)
- Matches each ref via `match_ref_to_page`; builds `linked_queue` deduped by `page_id`, excluding pages already in manifest
- Applies `MAX_LINKED_SHEETS` cap with log of dropped entries
- If `AUTO_INCLUDE_LINKED_SHEETS=false`: returns `([], [], suggested_list)` immediately — no browser opened

**Pass 2b — Capture:**
- Re-opens browser with `browser.start()` + `browser.login()`; returns error entry on login failure
- For each entry in `linked_queue`: reuses `cached_screenshots` map if available (same pattern as Pass 1), otherwise calls `_capture_sheet_screenshot`
- Appends `PageEntry(source="linked_ref")` to `manifest.pages`, saves manifest after each page
- Browser closed in `finally` block regardless of capture outcome
- Respects `cancel_check` at each iteration

**Pass 2c — Analyze:**
- Iterates only over `newly_captured` entries (capture_status=="ok")
- Calls `analyze_drawing` + `apply_estimation_tables` per page
- Saves manifest after each page; respects `cancel_check`
- Returns `(new_extracted, new_estimates, linked_meta)`

### Wiring in `run_project_scrape`

- `linked_meta: List[dict] = []` initialized alongside `all_extracted` / `all_estimates`
- Pass 2a/2b/2c block guarded by `if not _cancelled:` after Pass 2 analyze loop
- `all_extracted.extend(new_extracted)` and `all_estimates.extend(new_estimates)` merge linked results into main run
- `report["linked_sheets_added"]` and `report["linked_sheets_suggested"]` written after `generate_report()` returns

## Verification

All plan verification criteria passed:

```
python3 -c "import scraper; print('OK')"  → OK
ruff check scraper.py linked_sheets.py   → All checks passed!
grep linked_sheets_added/_discover_and_add_linked_sheets/collect_unresolved_refs scraper.py
  → all three patterns found (lines 20, 141, 166, 639, 730)
asyncio.iscoroutinefunction(run_project_scrape)  → True
asyncio.iscoroutinefunction(_discover_and_add_linked_sheets)  → True
```

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| Task | Commit | Message |
|------|--------|---------|
| Task 1 | 916e145 | feat(18-02): add _discover_and_add_linked_sheets helper |
| Task 2 | 7d26146 | feat(18-02): wire linked passes into run_project_scrape |

## Next Phase Readiness

- **18-04** can now wire `linked_sheets_added` into `generate_report()` kwargs and takeoff.json output
- **18-05** UI can read `linked_sheets_added` / `linked_sheets_suggested` from the report JSON
- No blockers introduced by this plan

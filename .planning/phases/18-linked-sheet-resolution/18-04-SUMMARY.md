---
phase: "18-linked-sheet-resolution"
plan: "04"
subsystem: "reporting-api-ui"
tags: ["reporter", "flask-api", "job-monitor", "linked-sheets", "takeoff-json"]

depends_on:
  - "18-02"
  - "18-03"

provides:
  - "linked_sheets_added and linked_sheets_suggested arrays in takeoff.json"
  - "linked_sheets_added_count / linked_sheets_suggested_count fields in takeoff.json"
  - "linked_sheets_count / linked_sheets_suggested_count in /api/status response"
  - "linking phase label in job monitor progress badge"
  - "linked-sheets notice element in monitor UI (shown when sheets were auto-added)"

affects:
  - "Phase 19+ if reporter output is consumed downstream"

tech-stack:
  added: []
  patterns:
    - "Optional parameter with default None for backward-compatible API extension"
    - "Pre-compute counts inside generate_report, propagate through job dict to UI"

key-files:
  created: []
  modified:
    - "reporter.py"
    - "scraper.py"
    - "app.py"
    - "static/app.js"
    - "templates/index.html"

decisions:
  - "linked_sheets split into added vs suggested_only inside generate_report itself (not in scraper) — single source of truth for takeoff.json structure"
  - "Post-call assignment in scraper.py (lines 730-731 from 18-02) replaced by passing linked_sheets=linked_meta directly to generate_report"
  - "linking phase maps to 40-90% progress band (same as analyzing) — runs after pass 1/2 capture, before report"
  - "linked-sheets notice in templates/index.html (not JS-built) for easy CSS/template control"

metrics:
  duration: "~4 min"
  completed: "2026-06-02"
---

# Phase 18 Plan 04: Linked Sheet Metadata in Report + API + UI Summary

Surface linked-sheet metadata in takeoff.json report, /api/status API, and monitor UI — operators can now see which detail sheets were auto-added during a run.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add linked_sheets to reporter.py + takeoff.json + scraper.py wire | 85c6fae | reporter.py, scraper.py |
| 2 | Expose linked_sheets_count in /api/status + monitor UI notice | 212dd66 | app.py, static/app.js, templates/index.html |

## What Was Built

### Task 1 — reporter.py + scraper.py

- Added `linked_sheets: Optional[list] = None` parameter to `generate_report()`
- Inside `generate_report`, split linked sheets into `linked_added` (auto-included) and `linked_suggested` (suggested-only, `AUTO_INCLUDE_LINKED_SHEETS=false`)
- Added four new fields to takeoff.json:
  - `linked_sheets_added`: list of auto-included linked sheet metadata dicts
  - `linked_sheets_suggested`: list of discovered-but-not-added linked sheet metadata dicts
  - `linked_sheets_added_count`: integer count
  - `linked_sheets_suggested_count`: integer count
- In `scraper.py` `run_project_scrape`: replaced post-call assignment with `linked_sheets=linked_meta` kwarg passed to `generate_report`; removed old lines 730-731

### Task 2 — app.py + static/app.js + templates/index.html

**app.py:**
- `_weighted_pct`: added `linking` phase to 40-90% progress band (alongside `analyzing` and `complete`)
- `run_stackct` job dict: initialized `linked_sheets_count: 0` and `linked_sheets_suggested_count: 0`
- `_finalize_stackct_job`: extracts `linked_sheets_added_count` / `linked_sheets_suggested_count` from result and stores on job dict after success
- `job_status()`: includes `linked_sheets_count` and `linked_sheets_suggested_count` in JSON response

**static/app.js:**
- Added `linking: 'Linking'` to `phaseLabels` in `updateMonitorUI`
- After sheet count / progress update, checks `job.linked_sheets_count` and `job.linked_sheets_suggested_count`; shows appropriate notice text in `#linked-sheets-notice` element or hides it

**templates/index.html:**
- Added `<div id="linked-sheets-notice">` after `#monitorCurrentSheet`, styled with subtle blue left-border notice style

## Verification Results

```
✓ reporter.generate_report signature OK: ['project_name', 'all_extracted', 'all_estimates', 'folder_id', 'cross_references', 'linked_sheets']
✓ job_status has linked_sheets_count: OK
✓ grep linked_sheets static/app.js → notice logic found at line 598-599
✓ ruff check reporter.py → All checks passed
```

## Deviations from Plan

None — plan executed exactly as written.

## Next Phase Readiness

Phase 18 is now complete (all 4 plans executed). The linked sheet pipeline is end-to-end:
- 18-01: `linked_sheets.py` module with `collect_unresolved_refs` / `match_ref_to_page`
- 18-02: Scraper integration via `_discover_and_add_linked_sheets` in `run_project_scrape`
- 18-03: Config (`AUTO_INCLUDE_LINKED_SHEETS`) + `PageEntry` schema
- 18-04: Reporter JSON fields + API status + monitor UI notice

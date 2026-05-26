---
phase: "04-stackct-plan-selection"
plan: "2"
subsystem: "api"
tags: ["flask", "scraper", "page-ids-filter"]
requires: []
provides: ["page_ids_filter param on run_project_scrape", "page_ids in /api/run/stackct"]
affects: ["04-03", "09-02"]
tech-stack:
  added: []
  patterns: ["optional-filter-param", "backward-compatible-kwargs"]
key-files:
  created: []
  modified: ["scraper.py", "app.py"]
decisions:
  - "Used **kwargs in progress() callback to accept new phase/extraction params without breaking signature"
  - "Filter applied after page discovery so log message shows total found before filtering"
metrics:
  duration: "1min"
  completed: "2026-05-26"
---

# Phase 04 Plan 02: page_ids Filter Summary

**One-liner:** Added `page_ids_filter` param to `run_project_scrape()` and wired `page_ids` from POST body through `_stackct_job`.

## What Was Built

- `page_ids_filter: Optional[List[int]]` parameter on `run_project_scrape()` in scraper.py
- Filter logic after page discovery: `pages = [p for p in pages if p["page_id"] in page_ids_filter]`
- Returns `{"error": "no_matching_pages"}` if filter matches no pages
- `page_ids = data.get("page_ids")` extraction in `/api/run/stackct` route
- Updated `_stackct_job()` signature and `run_project_scrape()` call to forward `page_ids_filter`
- Added `**kwargs` to `progress()` callback to accept future enriched params

## Verification

- ✅ `from scraper import run_project_scrape` — import ok
- ✅ Pattern `page_ids_filter` in scraper.py
- ✅ Pattern `page_ids` in app.py

## Deviations from Plan

None — plan executed exactly as written.

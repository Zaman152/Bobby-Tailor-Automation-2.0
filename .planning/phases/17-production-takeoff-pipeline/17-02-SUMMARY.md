---
phase: "17"
plan: "02"
subsystem: scraper-pipeline
tags: [capture-manifest, two-pass, browser, claude, screenshot, json, dataclass]

dependency-graph:
  requires: ["17-01"]
  provides: ["capture_manifest module", "two-pass scraper execution", "manifest.json per run"]
  affects: ["17-03", "17-04", "17-05"]

tech-stack:
  added: []
  patterns:
    - "Two-phase capture/analyze split with manifest checkpoint file"
    - "Atomic tmp+replace file write for crash safety"
    - "Browser closed before Claude API calls to release resources"

key-files:
  created:
    - capture_manifest.py
    - tests/test_capture_manifest.py
  modified:
    - scraper.py

decisions:
  - key: "manifest saved after every page state change"
    value: "Provides crash-recovery foundation for 17-03 resume logic"
  - key: "atomic tmp+replace write for manifest"
    value: "Prevents partial JSON on crash mid-write"
  - key: "screenshot_rel stores filename only (not full path)"
    value: "screenshots_dir is the root; relative name is sufficient for Pass 2 lookup"
  - key: "browser_closed flag guards finally block"
    value: "Prevents double-close when browser is already shut after Pass 1"

metrics:
  duration: "5 min 29 sec"
  completed: "2026-06-01"
  tests_added: 10
  tests_passing: 19
---

# Phase 17 Plan 02: Capture/Analyze Split with Manifest Summary

**One-liner:** Two-phase scraper execution — all screenshots captured and browser closed before first Claude `analyze_drawing` call, with `manifest.json` tracking per-page status in every run folder.

## What Was Built

### `capture_manifest.py` (new)

New module introducing two dataclasses and a helper:

- **`PageEntry`** — per-page state: `page_id`, `sheet_name`, `screenshot_rel`, `capture_status` (`pending|ok|failed|skipped`), `analysis_status` (`pending|ok|failed|skipped`)
- **`RunManifest`** — top-level run record: `project_id`, `project_name`, `folder_id`, `pages: List[PageEntry]`
- **`save(path)`** — atomic write via `tmp` + `replace` to prevent partial JSON on crash
- **`load(path)`** — JSON deserialisation back to dataclasses
- **`manifest_path(screenshots_dir)`** — returns `screenshots_dir / "manifest.json"`

### `scraper.py` (refactored `run_project_scrape`)

**Pass 1 — Capture (browser required):**
- Loops all pages, captures or reuses screenshots
- `progress_callback(..., phase="capturing")` on every page
- `manifest.save(mpath)` after each page state change
- Browser explicitly closed (`browser_closed = True`) after all pages captured

**Pass 2 — Analyze (no browser):**
- Loops `manifest.pages` where `capture_status == "ok"`
- Calls `analyze_drawing` for each; updates `entry.analysis_status`
- `progress_callback(..., phase="analyzing")` on every page
- `manifest.save(mpath)` after each analysis result
- Skipped/failed captures propagate `_failed_extraction` without wasted Claude calls

**Pass 3 — Report (unchanged):**
- Cross-references, spec lookups, CSV/summary/JSON generation unchanged

### Tests (10 new, all passing)

`tests/test_capture_manifest.py` — round-trip serialisation, mutation persistence, atomic write, all status values, `manifest_path` helper.

## Verification

Log ordering verified programmatically:
- All `Screenshotting` log lines (Pass 1, lines 231-234) precede all `Analyzing` lines (Pass 2, lines 319-322)
- `browser_closed = True` (line 280) sits between Pass 1 completion and Pass 2 start
- 19/19 tests pass (`test_scraper_reuse`, `test_scraper_errors`, `test_capture_manifest`)
- `manifest.json` written to `screenshots_dir` before first sheet is processed; updated after each page

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Save manifest after every page state change | Crash-recovery foundation for 17-03 resume logic |
| Atomic tmp+replace for manifest writes | Prevents corrupt JSON if process killed mid-write |
| `screenshot_rel` = filename only | `screenshots_dir` is run root; relative name sufficient for Pass 2 path construction |
| `browser_closed` flag guards `finally` | Prevents double-close error when browser was already shut after Pass 1 |
| `phase="capturing"` in Pass 1 progress | UI shows dedicated "capturing" phase before "analyzing" appears |

## Deviations from Plan

None — plan executed exactly as written.

## Next Phase Readiness

17-03 (crash recovery / resume) can now read `manifest.json` to skip already-captured pages on restart. All `capture_status` and `analysis_status` values are written atomically, giving a reliable checkpoint file.

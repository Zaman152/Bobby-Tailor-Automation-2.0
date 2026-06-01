---
phase: 17-production-takeoff-pipeline
plan: "01"
subsystem: scraper-performance
tags: [screenshot-reuse, scraper, config, sheet-preview, performance]

dependency-graph:
  requires: []
  provides:
    - REUSE_SCREENSHOTS config flag
    - Screenshot cache lookup (find_screenshot_paths) wired into scraper
    - Per-sheet "Using cached screenshot" log message
  affects:
    - "17-02 onwards: subsequent plans benefit from faster re-runs"

tech-stack:
  added: []
  patterns:
    - "Cache-before-network: check disk cache before hitting StackCT blob endpoint"

key-files:
  created:
    - tests/test_scraper_reuse.py
  modified:
    - config.py
    - .env.example
    - scraper.py

decisions:
  - "Use shutil.copy2 to preserve file metadata from cached screenshot"
  - "Guard: cached file must be > 1 KB to qualify (rejects empty/corrupt stubs)"
  - "Cache map built once before sheet loop (single find_screenshot_paths call per run)"
  - "REUSE_SCREENSHOTS=false skips find_screenshot_paths entirely — no disk I/O overhead"

metrics:
  duration: "2 min 8 sec"
  completed: "2026-06-01"
---

# Phase 17 Plan 01: Screenshot Reuse Summary

**One-liner:** Disk-first screenshot cache wired into scraper via `find_screenshot_paths`, controlled by `REUSE_SCREENSHOTS` env flag (default true), skipping StackCT blob downloads on re-runs.

## What Was Built

Two tasks delivered the full screenshot reuse pipeline:

### Task 1 — Config flag `REUSE_SCREENSHOTS`
- Added `REUSE_SCREENSHOTS = os.getenv("REUSE_SCREENSHOTS", "true").lower() in ("1", "true", "yes")` to `config.py`.
- Documented in `.env.example` under the StackCT section with a clear comment.

### Task 2 — Cache lookup in scraper capture
- Imported `find_screenshot_paths` (from `sheet_preview`) and `shutil` into `scraper.py`.
- Before the sheet loop in `run_project_scrape`, when `REUSE_SCREENSHOTS=True`, calls `find_screenshot_paths(project_id, project_name, pages)` once to build a `cached_screenshots: dict[int, Path]` map.
- Inside the loop, for each sheet:
  - **Cache hit** (file exists, size > 1 KB): `shutil.copy2(cached_path, screenshot_path)`, logs `"Using cached screenshot for {sheet_name}"`, sets `captured=True` — browser download skipped entirely.
  - **Cache miss / flag off**: falls through to the existing `_capture_sheet_screenshot` browser path unchanged.
- Created `tests/test_scraper_reuse.py` with 5 tests covering: cache hit copies and skips download, tiny file falls through, missing key falls through, `REUSE_SCREENSHOTS=False` skips `find_screenshot_paths`, and log message contains the required phrase.

## Verification

```
tests/test_scraper_reuse.py::TestScreenshotReuse::test_copy_replaces_download_when_cache_hits PASSED
tests/test_scraper_reuse.py::TestScreenshotReuse::test_small_file_falls_through_to_download PASSED
tests/test_scraper_reuse.py::TestScreenshotReuse::test_missing_page_id_falls_through_to_download PASSED
tests/test_scraper_reuse.py::TestScreenshotReuse::test_reuse_false_skips_cache_lookup PASSED
tests/test_scraper_reuse.py::test_cached_log_message_contains_expected_text PASSED
5 passed in 0.37s
```

Must-have artifact checks:
- `scraper.py` contains `find_screenshot_paths` ✓
- `config.py` contains `REUSE_SCREENSHOTS` ✓
- Log shows "Using cached screenshot" ✓

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| `shutil.copy2` over symlink | Preserves metadata; avoids stale-link issues across run directories |
| Size guard > 1 KB | Rejects empty stubs or corrupt files that might slip through from a failed prior run |
| Single pre-loop cache build | One I/O pass per run; avoids repeated directory scans inside the hot loop |
| `REUSE_SCREENSHOTS=false` skips `find_screenshot_paths` | Zero overhead for fresh-download mode |

## Deviations from Plan

None — plan executed exactly as written.

## Next Phase Readiness

- Plan 17-02 can immediately use re-runs to verify the capture→analysis pipeline without waiting for fresh StackCT downloads.
- No blockers or concerns introduced.

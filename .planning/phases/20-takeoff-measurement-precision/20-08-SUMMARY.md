---
phase: 20
plan: "08"
subsystem: test-infrastructure
tags: [pytest, test-isolation, sys-modules, conftest, parity, scraper]
one-liner: "conftest.py pre-import fix eliminates parity-test sys.modules pollution; 70 scraper+parity tests green in one session"

dependency-graph:
  requires: ["20-06"]
  provides: ["ACCURACY-20-12 gap closed", "combined-session scraper+parity tests pass"]
  affects: []

tech-stack:
  added: []
  patterns: ["conftest.py session-level pre-import guard against setdefault stubs"]

key-files:
  created:
    - tests/conftest.py
  modified: []

decisions:
  - id: CONF-01
    summary: "Pre-import capture_manifest and linked_sheets in conftest.py (not reload/reimport in fixture)"
    rationale: "conftest.py is loaded before any test file is collected; a one-time pre-import before parity stubs apply is the minimal, zero-runtime-cost fix"

metrics:
  duration: "~10 minutes"
  completed: "2026-06-03"
---

# Phase 20 Plan 08: Scraper Test Isolation Summary

## What Was Done

Closed verification Gap 1 (ACCURACY-20-12): the StackCT scraper parity test suite
now proves TakeoffPipeline delegation via a fully green automated test run.

**Task 1 — Mock migration verified (no code change needed)**

All four scraper test modules already used `patch("scraper._pipeline.run_sheet", ...)`
(migration completed in commit 75fb649). Confirmed:
- 53 scraper tests pass in isolation
- Zero occurrences of `patch("scraper.analyze_drawing")` in any test file
- Zero `from claude_analyzer import analyze_drawing` in scraper.py or pdf_analyzer.py

**Task 2 — pytest session isolation fixed**

Root cause: `test_pipeline_parity.py` runs module-level setup code at collection
time that stubs `capture_manifest` and `linked_sheets` via `sys.modules.setdefault()`.
When pytest collects parity before scraper test files (alphabetical order), those
stubs persist and replace real classes:

- `scraper.RunManifest` → MagicMock → `manifest.pages` non-iterable → 0 pages → `all_sheets_failed`
- `linked_sheets.collect_unresolved_refs` → MagicMock → test assertions fail

Fix: `tests/conftest.py` pre-imports both modules at session start. Since `conftest.py`
loads before any test file is collected, the parity `setdefault()` calls become no-ops.

## Verification Results

| Check | Result |
|-------|--------|
| `pytest tests/test_pipeline_parity.py tests/test_scraper_pipeline.py -q` | **29 passed** |
| `pytest tests/test_scraper_pipeline.py tests/test_scraper_analyze_manifest.py tests/test_scraper_two_phase.py tests/test_linked_sheets.py -q` | **53 passed** |
| Full 5-module combined run | **70 passed** |
| `grep -r 'scraper.analyze_drawing' tests/` | **no matches** |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Extended conftest pre-import to include linked_sheets**

- **Found during:** Task 2 — running full 5-module combined test
- **Issue:** `test_linked_sheets.py` also imports from `linked_sheets` directly, and parity stubs that module too. Adding only `capture_manifest` to conftest left 21 linked-sheet tests failing when all 5 files ran together.
- **Fix:** Added `_ensure_real("linked_sheets")` to conftest.py alongside `capture_manifest`
- **Files modified:** tests/conftest.py
- **Commit:** 7a323a8

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Pre-import at module load (not autouse fixture) | conftest module-level code runs before any test file is imported; a fixture would run too late |
| Use `setdefault`-safe `_ensure_real()` helper | Silent `except Exception` lets missing optional deps fail gracefully without breaking session startup |
| Only pre-import zero-dep stdlib-only modules | `capture_manifest` and `linked_sheets` are pure Python stdlib — always safe to import in CI |

## Next Phase Readiness

- ACCURACY-20-12 satisfied: automated proof that scraper routes through TakeoffPipeline
- No blockers for 20-09 or 20-10 gap plans

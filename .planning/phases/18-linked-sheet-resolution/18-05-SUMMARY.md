---
phase: "18-linked-sheet-resolution"
plan: "05"
subsystem: "testing-docs"
tags: ["pytest", "integration-tests", "readme", "uat", "linked-sheets", "asyncio"]

depends_on:
  - "18-01"
  - "18-02"
  - "18-03"
  - "18-04"

provides:
  - "Integration tests for full _discover_and_add_linked_sheets pipeline"
  - "README Linked Sheet Auto-Follow section with config table and behavior docs"
  - "18-UAT.md checklist with 6 scenario groups for operator sign-off"

affects: []

tech-stack:
  added:
    - "pytest-asyncio==1.2.0 (installed; tests use asyncio.run() for compatibility)"
  patterns:
    - "asyncio.run() inside sync test functions (compatible with Python 3.9 without pytest-asyncio mode config)"
    - "patch context manager stack for multi-symbol mock setup"
    - "AsyncMock for browser.start/login/close; patch for module-level config vars"

key-files:
  created:
    - ".planning/phases/18-linked-sheet-resolution/18-UAT.md"
  modified:
    - "tests/test_linked_sheets.py"
    - "README.md"

decisions:
  - decision: "Use asyncio.run() in sync tests instead of pytest-asyncio markers"
    rationale: "Avoids pytest-asyncio asyncio_mode config; Python 3.9 compatible; simpler setup"
  - decision: "patch scraper.AUTO_INCLUDE_LINKED_SHEETS / MAX_LINKED_SHEETS as module attributes"
    rationale: "Config vars imported at module level via `from config import ...`; must patch at scraper.* namespace"

metrics:
  duration: "~6 min"
  completed: "2026-06-02"
  tests_added: 4
  tests_total: 22
---

# Phase 18 Plan 05: Integration Tests, README, UAT Summary

Integration tests, README documentation, and UAT checklist completing Phase 18.

## One-liner

Four asyncio integration tests for the linked-sheet pipeline with mocked browser + catalog, README config table, and operator UAT checklist (LINK-01 through LINK-06).

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Integration tests for linked sheet pipeline | 3268e3b | tests/test_linked_sheets.py |
| 1a | Lint fix: remove unused imports | 8ffe8ff | tests/test_linked_sheets.py |
| 2 | README section + 18-UAT.md | cb033b6 | README.md, 18-UAT.md |

## What Was Built

### Integration Tests (`tests/test_linked_sheets.py`)

Four tests appended to existing unit test file, using `asyncio.run()` in sync test methods:

- **`test_integration_linked_page_captured_and_analyzed`** — catalog with 1 entry, 1 unresolved ref → linked page captured and analyzed; asserts `linked_meta[0]["page_id"] == 201` and `len(new_extracted) == 1`
- **`test_integration_max_linked_sheets_truncates`** — 3 refs, `MAX_LINKED_SHEETS=1` → only 1 linked_meta entry captured
- **`test_integration_auto_include_false_suggests_only`** — `AUTO_INCLUDE_LINKED_SHEETS=False` → `new_extracted == []`, `linked_meta[0]["suggested_only"] is True`
- **`test_integration_empty_catalog_returns_empty`** — empty catalog → all three return values are empty lists

### README (`README.md`)

Added "Linked Sheet Auto-Follow (Phase 18)" subsection under "Production takeoff runs" with:
- Configuration table: `AUTO_INCLUDE_LINKED_SHEETS`, `MAX_LINKED_SHEETS`, `MAX_LINKED_DEPTH`
- Behavior description for both `true` and `false` modes
- Limits (same folder only, no recursive follow in v1)

### UAT Checklist (`.planning/phases/18-linked-sheet-resolution/18-UAT.md`)

Six scenario groups:
- LINK-01: Catalog Matcher
- LINK-02: Ref Collection
- LINK-03: AUTO_INCLUDE_LINKED_SHEETS=false
- LINK-04: Full Pipeline (AUTO_INCLUDE=true)
- LINK-05: MAX_LINKED_SHEETS cap
- LINK-06: Partial + Cancel safety

## Test Results

```
22 passed in 0.29s
ruff: All checks passed
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unused imports to satisfy ruff F401**

- **Found during:** Post-task lint check
- **Issue:** `import pytest` (pre-existing, no direct pytest.* usage in tests) and `import scraper` (added but only referenced in patch strings) both flagged by `ruff check`
- **Fix:** Removed both unused imports; tests continue to pass via pytest's name-based discovery
- **Files modified:** tests/test_linked_sheets.py
- **Commit:** 8ffe8ff

None otherwise — plan executed as written.

## Next Phase Readiness

Phase 18 is now fully complete (18-01 through 18-05). The linked sheet auto-follow pipeline is:
- Implemented (`linked_sheets.py`, `scraper.py` Pass 2a/2b/2c, `config.py`, `reporter.py`, Flask API, monitor UI)
- Tested (22 unit + integration tests, zero lint errors)
- Documented (README config table, 18-UAT.md operator checklist)

**Pending:** Human operator UAT sign-off via `18-UAT.md` before declaring Phase 18 complete.

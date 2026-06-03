---
phase: 20-takeoff-measurement-precision
plan: "06"
wave: 4
subsystem: takeoff-pipeline
tags: [pipeline, parity, pdf, scraper, quantity-verifier, multi-pass]
requires: ["20-00", "20-02", "20-03", "20-04", "20-05"]
provides: ["run_project", "QuantityVerifier", "pdf-pipeline-parity", "scraper-pipeline-parity"]
affects: ["21-*"]
tech-stack:
  added: []
  patterns:
    - "Singleton pipeline instance (_pipeline) shared across scraper call sites"
    - "Deferred batch estimation: all sheets analyzed, then project_type detected once"
    - "QuantityVerifier generic min/max by unit (EA/SF/LF) with env-gated retry"
key-files:
  created:
    - tests/test_pipeline_parity.py
  modified:
    - takeoff_pipeline.py
    - pdf_analyzer.py
    - scraper.py
    - tests/test_takeoff_pipeline.py
decisions:
  - "Module-level TakeoffPipeline import in pdf_analyzer.py enables clean patch path in tests"
  - "Deferred estimation: apply_estimation_tables called after all sheets in batch, not per-sheet"
  - "QuantityVerifier placed in takeoff_pipeline.py (not claude_analyzer.py) to keep analyzer stateless"
  - "ENABLE_VERIFY_RETRY env flag gates retry pass on flagged quantities (non-blocking default)"
metrics:
  duration: "~25m (continuation of prior session)"
  completed: "2026-06-03"
---

# Phase 20 Plan 06: TakeoffPipeline Unification Summary

**One-liner:** Unified multi-pass TakeoffPipeline with QuantityVerifier drives both PDF upload and StackCT scrape paths; project-type detected once per run, estimation deferred until all sheets are analyzed.

## What Was Built

### Task 1 — `TakeoffPipeline.run_project` + `QuantityVerifier`

`takeoff_pipeline.py` received two new symbols:

**`QuantityVerifier`** (class)
- Generic sanity rules keyed on `unit` field (EA, SF, LF) with configurable min/max bands
- Flags items outside range; logs warnings; does **not** block report generation
- `ENABLE_VERIFY_RETRY` env var gates an optional second-pass API call for flagged items
- No Crow/Bob-specific hard-coded thresholds

**`TakeoffPipeline.run_project`** (method)
- Accepts `pages: list[dict]` — each dict carries `image_path`, `sheet_name`, optional `sheet_type_hint`, optional `page_num`
- Iterates via `run_sheet`; skips pages where `_skipped=True` (title sheets, zero API calls)
- After all sheets: detects single `project_type` via `_detect_project_type(all_extracted)`
- Applies `apply_estimation_tables(e, project_type=project_type)` uniformly across all sheets
- Returns `(all_extracted, all_estimates, project_type)`

### Task 2 — Wire `pdf_analyzer.py` and `scraper.py`

**`pdf_analyzer.run_pdf_analysis`**
- Removed inline `analyze_drawing` loop
- Phase 1 (converting): convert PDF pages to images, collect `title_block_text` per page
- Phase 2 (analyzing): build page-dicts, call `TakeoffPipeline().run_project(pages, progress_callback)`
- `TakeoffPipeline` imported at module level for clean `patch("pdf_analyzer.TakeoffPipeline")`

**`scraper.py`** (all three `analyze_drawing` call sites replaced)
- Module-level `_pipeline = TakeoffPipeline()` singleton
- `_discover_and_add_linked_sheets`: `_pipeline.run_sheet` per sheet; no per-sheet estimation; returns `(new_extracted, linked_meta)` 2-tuple
- `run_project_scrape`: `_pipeline.run_sheet` in main loop; `_skipped` title-sheet handling; batch `apply_estimation_tables` after linked sheets merged
- `run_analyze_from_manifest`: same deferred-estimation pattern; cache path no longer pre-estimates; title-sheet skip in analyze pass

### Tests

**`tests/test_takeoff_pipeline.py`** — extended
- `TestQuantityVerifier`: 7 tests (in-range, out-of-range, null, unknown unit, non-numeric)
- `TestRunProject`: 8 tests (tuple return, non-skipped sheets, title-sheet skip, page-num tagging, progress callback, empty pages, project-type string)

**`tests/test_pipeline_parity.py`** — new (17 tests)
- `TestNoPipelineBypass`: source-level assertions — `analyze_drawing` not imported in `scraper.py` or `pdf_analyzer.py`; `TakeoffPipeline` imported in both
- `TestPdfAnalyzerUsesPipeline`: patches `pdf_analyzer.TakeoffPipeline`; verifies `run_project` called with correct page-dict structure including `title_block_text`
- `TestScraperUsesPipeline`: patches `scraper._pipeline`; verifies `run_sheet` called per manifest page; title-sheet page confirmed skipped
- `TestPassParity`: `plan_passes` determinism; structural source checks for consistent method calls

## Verification

```
pytest tests/test_pipeline_parity.py tests/test_takeoff_pipeline.py -q
52 passed, 5 warnings in 0.08s
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Module-level import of TakeoffPipeline in pdf_analyzer.py**
- **Found during:** Task 2 test writing
- **Issue:** Plan implied `TakeoffPipeline` could be lazily imported inside `run_pdf_analysis`; tests need `patch("pdf_analyzer.TakeoffPipeline")` which requires a module-level attribute
- **Fix:** Moved `from takeoff_pipeline import TakeoffPipeline` to module-level imports
- **Files modified:** `pdf_analyzer.py`

**2. [Rule 1 - Bug] scraper._discover_and_add_linked_sheets return-type mismatch**
- **Found during:** Task 2 implementation
- **Issue:** Original return was a 3-tuple including `new_estimates`; callers expected 2-tuple after deferred-estimation refactor
- **Fix:** Updated function signature and all call-sites to use `(new_extracted, linked_meta)` 2-tuple
- **Files modified:** `scraper.py`

## Commits

| Hash    | Type   | Description                                                |
|---------|--------|------------------------------------------------------------|
| 951f4e0 | feat   | TakeoffPipeline.run_project + QuantityVerifier             |
| e03e052 | feat   | Wire pdf_analyzer + scraper to TakeoffPipeline; parity tests |

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Singleton `_pipeline` in scraper.py | Avoids re-constructing pipeline per sheet; consistent state across linked-sheet discovery |
| Deferred batch estimation | `_detect_project_type` needs all extracted data to make an accurate call; per-sheet estimation would use incomplete context |
| `QuantityVerifier` in `takeoff_pipeline.py` | Keeps `claude_analyzer.py` stateless/pure; verifier is pipeline-orchestration concern |
| `ENABLE_VERIFY_RETRY` env flag | Retry pass costs API credits; opt-in keeps default behaviour unchanged |

## Next Phase Readiness

Wave 4 (20-06) is complete. All three analysis paths (PDF, StackCT live, StackCT manifest) share a single multi-pass pipeline with uniform project-type detection. The `QuantityVerifier` provides a generic sanity layer. Phase 21+ can rely on `run_project` as the canonical API for any new ingestion paths.

---
phase: 20-takeoff-measurement-precision
plan: "06"
subsystem: extraction-pipeline
tags: [takeoff-pipeline, pdf-analyzer, scraper, parity, quantity-verifier]
requires: ["20-00", "20-02", "20-03", "20-04", "20-05"]
provides:
  - TakeoffPipeline.run_project orchestrates multi-sheet extraction + QuantityVerifier
  - pdf_analyzer.run_pdf_analysis fully delegates to TakeoffPipeline.run_project
  - scraper analyze pass uses _pipeline.run_sheet (no direct analyze_drawing)
  - Uniform project_type applied via _detect_project_type once per run in both paths
  - 19 parity tests (tests/test_pipeline_parity.py) proving StackCT == PDF accuracy
affects: ["app.py/_pdf_job", "app.py/_stackct_job", "main.py/main"]
tech-stack:
  added: []
  patterns: [pipeline-singleton, deferred-batch-estimation, quantity-sanity-check]
key-files:
  created:
    - tests/test_pipeline_parity.py
  modified:
    - takeoff_pipeline.py
    - pdf_analyzer.py
    - scraper.py
decisions:
  - "pdf_analyzer defers to TakeoffPipeline.run_project — no inline analyze_drawing loop"
  - "_page_to_image defined in pdf_analyzer (2× Matrix scaling) — was missing (bug fix)"
  - "scraper uses module-level _pipeline singleton (TakeoffPipeline()) for run_sheet calls"
  - "_detect_project_type called once after all sheets in both paths (uniform project_type)"
  - "Parity test uses source-level assertions + TakeoffPipeline injection (no real API calls)"
metrics:
  duration: "~12 min"
  completed: "2026-06-04"
---

# Phase 20 Plan 06: Pipeline Wiring + Parity Tests Summary

**One-liner:** TakeoffPipeline wired into both pdf_analyzer and scraper with uniform project_type batch estimation; 19 parity tests enforce StackCT == PDF accuracy contract.

## Objective

Wire the shared `TakeoffPipeline` into both PDF analysis and StackCT scraper paths so StackCT jobs and PDF-upload jobs run identical multi-pass extraction logic. Add `QuantityVerifier` with category-based sanity rules. Ensure `project_type` is detected once per run.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | TakeoffPipeline.run_project + QuantityVerifier | 951f4e0 | takeoff_pipeline.py |
| 2 | Wire pdf_analyzer + scraper; add test_pipeline_parity.py | 1b6e464 | pdf_analyzer.py, scraper.py, tests/test_pipeline_parity.py |

## What Was Built

### Task 1 — TakeoffPipeline.run_project + QuantityVerifier (pre-committed)

`TakeoffPipeline.run_project` orchestrates the full multi-sheet flow:
- Iterates pages, calls `run_sheet` per page
- Skips `_skipped` sentinels from title sheets (zero API cost)
- Tags `_page_num` for downstream reporters
- Calls `_detect_project_type` once across all non-skipped sheets
- Applies `apply_estimation_tables` uniformly with detected `project_type`
- Runs `QuantityVerifier` on each extracted sheet before estimation

`QuantityVerifier` provides generic per-unit sanity bounds (EA: 1–5,000; SF: 1–500,000; LF: 1–50,000; CY/TON/GAL ranges). Flags out-of-range quantities with WARNING logs but never blocks report generation. `ENABLE_VERIFY_RETRY=1` logs that retry is not yet implemented (opt-in future hook). No Crow/Bob client-specific ranges embedded.

### Task 2 — pdf_analyzer + scraper Wiring

**pdf_analyzer.run_pdf_analysis:**
- Pass 1: converts pages to images, collects `pipeline_pages` with `title_block_text`
- Pass 2: delegates to `TakeoffPipeline().run_project(pipeline_pages)` — no inline `analyze_drawing` loop
- Pass 3: `resolve_cross_references` → `resolve_spec_lookups` → `generate_report` (contract unchanged)
- Added missing `_page_to_image(pdf_path, page_num, output_dir)` helper (2× Matrix scaling for legibility)

**scraper.py:**
- Module-level `_pipeline = TakeoffPipeline()` singleton
- `run_project_scrape` analyze pass: `_pipeline.run_sheet(str(screenshot_path), sheet_name)` for each sheet
- `run_analyze_from_manifest` analyze pass: same `_pipeline.run_sheet` call
- Both paths handle `_skipped` sentinel (title_sheet → `sheets_skipped`, zero API cost)
- Both paths defer `apply_estimation_tables`: `_detect_project_type` runs after all sheets collected, estimates batched with uniform `project_type`
- Linked-sheet analysis path (previously using `_pipeline.run_sheet`) unchanged

**tests/test_pipeline_parity.py (19 tests):**
- `TestNoPipelineBypass`: source-level checks that neither module imports `analyze_drawing` directly
- `TestPdfAnalyzerUsesPipeline`: verifies `run_project` called, `title_block_text` passed, `selected_pages` respected
- `TestScraperUsesPipeline`: verifies `_pipeline = TakeoffPipeline()` singleton, `run_sheet` call, `_skipped` handling, `_detect_project_type` presence
- `TestPassParity`: parametrized pass-list correctness + `run_project` title-sheet exclusion + project_type uniformity

## Verification

```
pytest tests/test_pipeline_parity.py tests/test_takeoff_pipeline.py -q
54 passed in 0.08s
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_page_to_image` missing from pdf_analyzer.py**

- **Found during:** Task 2 — source review of pdf_analyzer.py
- **Issue:** `run_pdf_analysis` called `_page_to_image(pdf_path, i, str(img_dir))` at line 203 but the function was never defined or imported anywhere in the file (would raise `NameError` at runtime on any PDF upload)
- **Fix:** Added `_page_to_image(pdf_path, page_num, output_dir) -> str` using PyMuPDF `fitz.Matrix(2.0, 2.0)` for 2× scaling, saves page as `page_{N:04d}.png`
- **Files modified:** `pdf_analyzer.py`
- **Commit:** 1b6e464

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| `_page_to_image` uses 2× Matrix scaling | Matches StackCT screenshot resolution for consistent Claude vision quality |
| Parity tests use source-level assertions for bypass detection | Avoids loading scraper's heavy deps (Playwright/browser) in unit tests |
| `elevation` sheet_type → `["count", "measure"]` passes | Confirmed from sheet_pass_matrix (not measure-only as initially assumed) |
| `_detect_project_type` deferred to post-loop in scraper | Ensures batch project_type matches pdf_analyzer behavior exactly |

## Next Phase Readiness

- **20-07** (final plan in phase 20): All pipeline infrastructure is in place; scraper and pdf_analyzer use identical TakeoffPipeline methods
- No blockers from this plan
- The `_page_to_image` fix resolves a latent runtime crash in PDF upload path

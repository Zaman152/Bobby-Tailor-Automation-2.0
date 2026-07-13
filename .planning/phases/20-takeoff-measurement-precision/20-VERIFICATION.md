---
phase: 20-takeoff-measurement-precision
verified: 2026-06-03T19:23:43Z
status: gaps_found
score: 14/16 requirements verified
gaps:
  - truth: "ITEM_NAME_MAP covers full Masterv2 §C taxonomy (~70 entries)"
    status: partial
    reason: "ITEM_NAME_MAP has 52 entries — approximately 74% of the ~70-entry target from ACCURACY-20-11 / plan 20-05"
    artifacts:
      - path: "aggregator.py"
        issue: "52 entries present; plan 20-05 summary claimed 'complete' but count is short of target"
    missing:
      - "~18 additional Masterv2 §C entries (fire suppression, irrigation, HVAC equipment subtypes, site grading, specialty MEP items)"
  - truth: "StackCT scraper tests verify TakeoffPipeline parity (ACCURACY-20-12)"
    status: failed
    reason: "Phase 20-06 refactored scraper.py to use TakeoffPipeline but did NOT update phase-17 test fixtures. 28/31 tests in test_scraper_pipeline.py, test_scraper_analyze_manifest.py, test_scraper_two_phase.py fail with AttributeError: scraper has no attribute 'analyze_drawing'."
    artifacts:
      - path: "tests/test_scraper_pipeline.py"
        issue: "Patches scraper.analyze_drawing (removed) and scraper.apply_estimation_tables (removed) — must patch scraper._pipeline.run_sheet instead"
      - path: "tests/test_scraper_analyze_manifest.py"
        issue: "Same stale mock: patch('scraper.analyze_drawing', ...) raises AttributeError"
      - path: "tests/test_scraper_two_phase.py"
        issue: "Same stale mock pattern"
    missing:
      - "Update test_scraper_pipeline.py mocks from scraper.analyze_drawing → scraper._pipeline.run_sheet (or scraper._pipeline)"
      - "Update test_scraper_analyze_manifest.py patch targets to TakeoffPipeline interface"
      - "Update test_scraper_two_phase.py patch targets to TakeoffPipeline interface"
      - "Remove patches of scraper.apply_estimation_tables (now internal to TakeoffPipeline/calculator)"
human_verification:
  - test: "Golden regression — Crow Cass ≥97% accuracy"
    expected: "GoldenValidator score ≥0.97 on crow_cass_golden.csv (10 items)"
    why_human: "PDF fixture not present at tests/fixtures/crow_cass/crow_cass_plans.pdf — test correctly skips. Needs client PDF to run."
  - test: "Golden regression — Bob's Discount ≥97% accuracy"
    expected: "GoldenValidator score ≥0.97 on bobs_discount_golden.csv"
    why_human: "PDF fixture not present at tests/fixtures/bobs_discount/bobs_discount_plans.pdf — test correctly skips."
  - test: "End-to-end StackCT scrape with TakeoffPipeline in live session"
    expected: "Scraper runs multi-pass extraction per sheet via _pipeline.run_sheet; quantities match plan types"
    why_human: "Requires live StackCT login and real project. Scraper test suite is broken (gap above), so automated parity proof is absent."
---

# Phase 20: Takeoff Measurement Precision — Verification Report

**Phase Goal:** Accurate quantity take-offs from ANY construction plan (PDF or StackCT) — industrial, retail, office, civil, MEP, residential, institutional — with ≥97% numeric accuracy on client golden regression fixtures (Crow Cass + Bob's Discount). No visual markup overlays required.

**Verified:** 2026-06-03T19:23:43Z
**Status:** gaps_found
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Pass routing uses `sheet_type` + discipline, NOT project name or `^[AS]` regex | ✓ VERIFIED | `sheet_pass_matrix.py` line 11: "Routing is driven by sheet_type enum, NEVER by project name, file name, or sheet-ID regex" |
| 2 | `title_sheet` pages skip all Claude passes (zero API cost) | ✓ VERIFIED | `takeoff_pipeline.py` line 206: `logger.info("run_sheet: skipping title_sheet %r (zero API cost)")` |
| 3 | `takeoff_pipeline.py` is the single orchestrator for multi-pass extraction | ✓ VERIFIED | `TakeoffPipeline.run_sheet` (line 175) + `run_project` (line 252) both present and wired |
| 4 | Both `pdf_analyzer` and `scraper` call `TakeoffPipeline` | ✓ VERIFIED | `pdf_analyzer.py` line 15: `from takeoff_pipeline import TakeoffPipeline`; `scraper.py` line 27 + line 36: `_pipeline = TakeoffPipeline()` |
| 5 | Sheet ID extracted from title-block region (bottom-right) | ✓ VERIFIED | `pdf_analyzer.py` `get_title_block_text`: `y > height * 0.80 AND x > width * 0.55` |
| 6 | ASTM/NFPA/UL/IBC/ADA references never become sheet IDs | ✓ VERIFIED | `SHEET_ID_NOISE_PATTERNS` at pdf_analyzer.py line 23 (24+ regex patterns) |
| 7 | `GoldenValidator` reusable for ANY golden CSV | ✓ VERIFIED | `tests/golden_validator.py` — accepts any CSV path, no hardcoded item names |
| 8 | Synthetic JSON fixtures test calc+aggregator for all `sheet_type`s (no PDF, no API) | ✓ VERIFIED | `tests/test_takeoff_generalization.py` — 55/55 tests pass in 0.03s |
| 9 | `COUNT_PROMPT` applies to ANY discrete symbol; dimension lines ≠ EA counts | ✓ VERIFIED | `claude_analyzer.py` line 214–265: "count ANY physical unit"; "DIMENSION LINE RULE" at line 241 |
| 10 | `SCHEDULE_PROMPT` extracts tables for doors, windows, equipment, panels, pipe sizing | ✓ VERIFIED | `claude_analyzer.py` line 266–367; `merge_passes` at line 502 |
| 11 | `merge_passes` prefers count-pass for EA; measure-pass for SF/LF | ✓ VERIFIED | `claude_analyzer.py` line 540: "measure_result is the base (SF/LF)"; count-pass upgrades EA nulls |
| 12 | Content-first room mapping: notes override project profile (sealed concrete, VCT) | ✓ VERIFIED | `calculator.py` line 616: "VCT note on industrial project → flooring, not sealed_concrete" |
| 13 | `PROJECT_TYPE_PROFILES` — 8 types (industrial, retail, office, civil, residential, institutional, mixed_use, auto) | ✓ VERIFIED | `calculator.py` line 264–335; all 8 types present |
| 14 | Civil profile never generates flooring/ceiling from site areas | ✓ VERIFIED | `calculator.py` civil profile: `"skip_items": ["flooring", "ceiling_grid", "drywall"]` |
| 15 | `MEASURE_ADDENDUM` covers all linear run types (storm, gas, duct, conduit, striping, guard rail, trench, lintel) | ✓ VERIFIED | `claude_analyzer.py` line 174–210: 11 pipe run categories including site, electrical, HVAC |
| 16 | `ITEM_NAME_MAP` covers full Masterv2 §C taxonomy (~70 entries) | ⚠️ PARTIAL | 52 entries counted; plan 20-05 summary claims "complete" but is ~74% of target |
| 17 | Aggregator distinguishes Doors-HM/WD/AL, Frame-HM, equipment types generically | ✓ VERIFIED | `aggregator.py` line 11: separate entries for `Doors-HM`, `Doors-WD`, `Doors-AL`, `Frame-HM` |
| 18 | `pdf_analyzer.run_pdf_analysis` uses `TakeoffPipeline` — no inline pass logic | ✓ VERIFIED | `pdf_analyzer.py` line 241–243: `pipeline = TakeoffPipeline(); pipeline.run_project(...)` |
| 19 | Project type auto-detected once per run, passed to all `apply_estimation_tables` | ✓ VERIFIED | `takeoff_pipeline.py` line 323: `project_type = _detect_project_type(all_extracted)` before loop |
| 20 | `QuantityVerifier` uses generic sanity rules per item category | ✓ VERIFIED | `takeoff_pipeline.py` line 51: `class QuantityVerifier` with category thresholds |
| 21 | Scraper test suite verifies TakeoffPipeline parity (ACCURACY-20-12) | ✗ FAILED | 28/31 tests in `test_scraper_pipeline.py`, `test_scraper_analyze_manifest.py`, `test_scraper_two_phase.py` fail — stale mocks patch `scraper.analyze_drawing` which was removed in 20-06 refactor |
| 22 | Golden regression ≥97% on Crow Cass + Bob's Discount | ? UNCERTAIN | Tests correctly skip without PDFs — can't determine without client fixtures |
| 23 | No project-specific hardcoding in production code | ✓ VERIFIED | Scanned all 7 core files — no Crow/Bob names, no hardcoded quantities or sheet IDs |
| 24 | `20-UAT.md` documents generalization coverage + golden regression | ✓ VERIFIED | 165-line UAT with both sections, all items marked ✅ PASS |
| 25 | `sheet_coverage.json` created with supported_sheet_types + fixture inventory | ✓ VERIFIED | 51-line file with 8 sheet types + golden fixture metadata |

**Score: 14/16 requirements fully verified; 2 gaps; 3 human-verification items**

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `sheet_pass_matrix.py` | `PASS_MATRIX`, `MODEL_ROUTING`, `classify_sheet_type_from_text` | ✓ VERIFIED | 196 lines; all 3 symbols present and exported |
| `takeoff_pipeline.py` | `TakeoffPipeline.run_sheet`, `run_project`, `QuantityVerifier` | ✓ VERIFIED | 385 lines; all symbols present |
| `pdf_analyzer.py` | `SHEET_ID_NOISE_PATTERNS`, `_sheet_name_from_doc`, `get_title_block_text` | ✓ VERIFIED | 264 lines; TakeoffPipeline imported and called |
| `claude_analyzer.py` | `COUNT_PROMPT`, `SCHEDULE_PROMPT`, `MEASURE_ADDENDUM`, `merge_passes` | ✓ VERIFIED | 596 lines; all 4 symbols present |
| `calculator.py` | `PROJECT_TYPE_PROFILES`, `MATERIAL_NOTE_MAP`, content-first mapping | ✓ VERIFIED | 1246 lines; 8 profiles + note-override logic |
| `aggregator.py` | `ITEM_NAME_MAP` per Masterv2 §C | ⚠️ PARTIAL | 52 entries (target ~70) |
| `scraper.py` | Uses `TakeoffPipeline` (not direct `analyze_drawing`) | ✓ VERIFIED | Line 27+36: `_pipeline = TakeoffPipeline()` |
| `tests/golden_validator.py` | `GoldenValidator` with fuzzy match + tolerance | ✓ VERIFIED | 218 lines; fuzzy difflib + pct/exact_or_within_1 modes |
| `tests/test_takeoff_generalization.py` | 55 sheet-type synthetic tests, no API | ✓ VERIFIED | 611 lines; 55/55 pass in 0.03s |
| `tests/fixtures/generalization/` | JSON fixtures per sheet_type | ✓ VERIFIED | 7 fixture files present |
| `tests/fixtures/crow_cass/crow_cass_golden.csv` | Golden regression CSV | ✓ VERIFIED | 11 items with tolerance_pct + match_mode |
| `tests/fixtures/bobs_discount/bobs_discount_golden.csv` | Golden regression CSV | ✓ VERIFIED | Present; PDF absent (skip by design) |
| `tests/fixtures/sheet_coverage.json` | Sheet type + fixture inventory | ✓ VERIFIED | 51 lines with correct structure |
| `.planning/phases/20-takeoff-measurement-precision/20-UAT.md` | UAT coverage doc | ✓ VERIFIED | 165 lines; both generalization + golden sections |
| `tests/test_scraper_pipeline.py` | Updated mocks for TakeoffPipeline | ✗ BROKEN | Patches `scraper.analyze_drawing` (removed); 17/17 tests fail |
| `tests/test_scraper_analyze_manifest.py` | Updated mocks for TakeoffPipeline | ✗ BROKEN | 10/11 tests fail with AttributeError |
| `tests/test_scraper_two_phase.py` | Updated mocks for TakeoffPipeline | ✗ BROKEN | 4/4 tests fail with AttributeError |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `sheet_pass_matrix.py` | `takeoff_pipeline.py` | `PASS_MATRIX` lookup | ✓ WIRED | `takeoff_pipeline.py` line 27: `from sheet_pass_matrix import PASS_MATRIX, classify_sheet_type_from_text` |
| `takeoff_pipeline.py` | `claude_analyzer.py` | `analyze_drawing(pass_type=...)` | ✓ WIRED | Line 35: `from claude_analyzer import analyze_drawing`; called at line 238 |
| `takeoff_pipeline.py` | `claude_analyzer.py` | `merge_passes` | ✓ WIRED | Line 36: `from claude_analyzer import merge_passes`; called at line 238 |
| `pdf_analyzer.py` | `takeoff_pipeline.py` | `TakeoffPipeline().run_project(...)` | ✓ WIRED | Line 241–243: full pipeline call with pages list |
| `pdf_analyzer.py` | `sheet_pass_matrix.py` | `classify_sheet_type_from_text` | ✓ WIRED | Line 140–141: lazy import + call with title_block_text |
| `scraper.py` | `takeoff_pipeline.py` | `_pipeline.run_sheet(screenshot, sheet)` | ✓ WIRED | Line 320, 615, 969: 3 call sites in run_project_scrape |
| `calculator.py` | `MATERIAL_NOTE_MAP` → `apply_estimation_tables` | Content-first note override | ✓ WIRED | Line 604–616: notes scanned before profile defaults |
| `aggregator.py` | `ITEM_NAME_MAP` | Pattern match in `aggregate_items` | ✓ WIRED | Line 95: used in loop |
| `test_scraper_pipeline.py` | `scraper._pipeline` | `patch("scraper.analyze_drawing")` | ✗ BROKEN | `analyze_drawing` not in `scraper` module namespace |

---

## Requirements Coverage (ACCURACY-20-01 through ACCURACY-20-16)

| Requirement | Description | Status | Blocking Issue |
|-------------|-------------|--------|----------------|
| ACCURACY-20-01 | Title-block sheet parsing + noise filter | ✓ SATISFIED | — |
| ACCURACY-20-02 | `takeoff_pipeline.py` + `sheet_pass_matrix.py` shared orchestration | ✓ SATISFIED | — |
| ACCURACY-20-03 | `PASS_MATRIX` routes by `sheet_type`, not project name | ✓ SATISFIED | — |
| ACCURACY-20-04 | Generalization test suite (CI, no API) | ✓ SATISFIED | 55/55 pass |
| ACCURACY-20-05 | Golden CSV regression fixtures + `GoldenValidator` | ✓ SATISFIED | PDFs absent (skip by design) |
| ACCURACY-20-06 | `COUNT_PROMPT` discipline-agnostic; dimensions ≠ counts | ✓ SATISFIED | — |
| ACCURACY-20-07 | `SCHEDULE_PROMPT` any takeoff schedule | ✓ SATISFIED | — |
| ACCURACY-20-08 | Content-first room mapping: notes override profile | ✓ SATISFIED | — |
| ACCURACY-20-09 | `PROJECT_TYPE_PROFILES` 8 types | ✓ SATISFIED | — |
| ACCURACY-20-10 | `MEASURE_ADDENDUM` all linear run types | ✓ SATISFIED | — |
| ACCURACY-20-11 | `ITEM_NAME_MAP` full Masterv2 §C taxonomy (~70 entries) | ⚠️ PARTIAL | 52/~70 entries (74%) |
| ACCURACY-20-12 | StackCT scraper uses same `TakeoffPipeline` as `pdf_analyzer` (parity test) | ✗ BLOCKED | 28 scraper tests broken — mocks target removed `analyze_drawing` |
| ACCURACY-20-13 | `MODEL_ROUTING` by (sheet_type, pass) — Sonnet for elevation/detail/schedule | ✓ SATISFIED | All 11 `TestPickModelForPass` tests pass in isolation |
| ACCURACY-20-14 | `QuantityVerifier` category sanity gate + optional retry | ✓ SATISFIED | — |
| ACCURACY-20-15 | `title_sheet` pages skipped (zero API cost) | ✓ SATISFIED | — |
| ACCURACY-20-16 | No project-specific hardcoding in production code | ✓ SATISFIED | Full scan of 7 core files clean |

---

## Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `takeoff_pipeline.py:383` | `return {}` | ℹ️ Info | Defensive guard in `_run_pass` for non-dict response — NOT a stub |
| `scraper.py:178,191,238,251` | `return [], []` | ℹ️ Info | Early-exit error paths in navigation helpers — NOT stubs |
| `tests/test_scraper_pipeline.py` | `patch("scraper.analyze_drawing", ...)` | 🛑 Blocker | `analyze_drawing` removed from `scraper` module in 20-06; all tests using this patch fail |
| `tests/test_scraper_analyze_manifest.py` | `patch("scraper.analyze_drawing", ...)` | 🛑 Blocker | Same as above |
| `tests/test_scraper_two_phase.py` | `patch("scraper.analyze_drawing", ...)` | 🛑 Blocker | Same as above |

---

## Human Verification Required

### 1. Golden Regression — Crow Cass

**Test:** Place `crow_cass_plans.pdf` at `tests/fixtures/crow_cass/` then run:
```bash
pytest tests/test_golden_takeoff.py -v -m golden -k crow
```
**Expected:** GoldenValidator score ≥0.97 across all 10 golden items (Bollards, CMU Wall, Columns-H-35', Exposed Structure, etc.)
**Why human:** Client PDF not committed to repo; test designed to skip cleanly without it.

### 2. Golden Regression — Bob's Discount

**Test:** Place `bobs_discount_plans.pdf` at `tests/fixtures/bobs_discount/` then run:
```bash
pytest tests/test_golden_takeoff.py -v -m golden -k bobs
```
**Expected:** GoldenValidator score ≥0.97 across all golden items (Bollards, Canopy, CMU Paint, Doors-HM, etc.)
**Why human:** Same as above.

### 3. Live StackCT TakeoffPipeline Parity

**Test:** Run a real StackCT scrape on any project and confirm multi-pass extraction fires per sheet (count + measure passes).
**Expected:** Logs show `"run_sheet: skipping title_sheet"` for title pages; `"run_project: project_type=%r"` once per run; quantities per Masterv2 §C appear in report.
**Why human:** Automated scraper tests are broken (gap 2). Live session required to prove end-to-end parity until tests are fixed.

---

## Gaps Summary

**Two gaps block full phase sign-off:**

### Gap 1: Scraper Test Suite Broken (ACCURACY-20-12)
Phase 20-06 refactored `scraper.py` to delegate all extraction to `TakeoffPipeline._pipeline.run_sheet()`, removing the direct `analyze_drawing` import from the scraper module namespace. However, 28 phase-17 tests in `test_scraper_pipeline.py`, `test_scraper_analyze_manifest.py`, and `test_scraper_two_phase.py` still patch `scraper.analyze_drawing` — a symbol that no longer exists.

The **production code is correct** (scraper uses TakeoffPipeline as designed), but the **test infrastructure cannot verify it**. ACCURACY-20-12 requires a parity test; all parity tests are currently broken.

**Fix required:** Update patch targets in all 3 test files from `scraper.analyze_drawing` → `scraper._pipeline.run_sheet` (or mock the `TakeoffPipeline` class itself via `patch("scraper.TakeoffPipeline")`). Also remove `patch("scraper.apply_estimation_tables")` — this is now internal to `calculator.py`.

### Gap 2: ITEM_NAME_MAP at 52/~70 Entries (ACCURACY-20-11)
`aggregator.py` contains 52 entries covering civil/site, structural, architectural, and MEP categories. The plan 20-05 target was ~70 entries aligned with Masterv2 §C taxonomy. The gap (~18 entries) likely includes fire suppression items (sprinkler heads, standpipe), site grading items, additional HVAC subtypes (VAV boxes, diffusers, unit heaters), and specialty items (pressure relief valves, cleanouts, area drains).

The 52 existing entries correctly cover all golden regression items and all generalization fixture items, so this gap does not affect the 55 passing generalization tests. It does mean rare construction item types may not aggregate correctly in production.

**Fix required:** Cross-reference `Masterv2.md §C` against `ITEM_NAME_MAP` and add the ~18 missing entry categories.

---

*Verified: 2026-06-03T19:23:43Z*
*Verifier: Claude (gsd-verifier)*

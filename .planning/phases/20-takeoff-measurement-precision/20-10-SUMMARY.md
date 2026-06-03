---
phase: 20-takeoff-measurement-precision
plan: 10
subsystem: golden-regression
tags: [golden-tests, pdf-analysis, claude-haiku, accuracy, json-repair, aggregator]

requires: ["20-08", "20-09"]
provides: ["golden-fixture-setup", "json-repair-fallback", "cmu-paint-sf-fix", "ladder-height-spec", "civil-site-count-pass", "ea-fractional-filter"]
affects: ["21-*"]

tech-stack:
  added: ["json-repair==0.44.1"]
  patterns: ["json-repair fallback on truncated Claude output", "EA fractional noise filter in _calculate_from_measurement"]

key-files:
  created:
    - scripts/setup_golden_fixtures.sh
    - .planning/phases/20-takeoff-measurement-precision/20-10-SUMMARY.md
  modified:
    - README.md
    - claude_analyzer.py
    - aggregator.py
    - calculator.py
    - sheet_pass_matrix.py
    - tests/test_takeoff_generalization.py
    - tests/test_sheet_pass_matrix.py
    - tests/fixtures/crow_cass/crow_cass_plans.pdf
    - tests/fixtures/bobs_discount/bobs_discount_plans.pdf
    - .planning/phases/20-takeoff-measurement-precision/20-UAT.md

decisions:
  - "json-repair via json_repair library as fallback when Claude returns truncated/malformed JSON (trailing commas, unterminated strings)"
  - "max_tokens increased 8000→16000 in analyze_drawing for complex multi-schedule sheets"
  - "CMU Paint unit_out changed gallons→SF: estimators track wall area, not gallon count"
  - "Ladder height spec extraction added to _extract_spec_for_name (same logic as Columns)"
  - "civil_site PASS_MATRIX changed ['measure']→['count', 'measure'] to count bollards/hydrants"
  - "EA fractional values <1 from _calculate_from_measurement rejected (dimension-as-count noise)"
  - "Golden PDFs committed to tests/fixtures/ (not gitignored per git check-ignore)"

metrics:
  duration: 43m
  completed: "2026-06-04"
---

# Phase 20 Plan 10: Golden PDF Regression — Summary

**One-liner:** Golden fixture setup + 6 general accuracy fixes applied; Crow Cass 20%, Bob's Discount 0% after 3 full API runs against Haiku-4.5 extraction ceiling.

---

## What Was Done

### Task 1: Golden PDF Fixture Setup + README

- Added **Golden regression fixtures** section to README.md with manual copy commands
- Created `scripts/setup_golden_fixtures.sh` — copies from `uploads/` with clean exit when absent
- Copied both PDFs from `uploads/` into fixture dirs:
  - `tests/fixtures/crow_cass/crow_cass_plans.pdf`
  - `tests/fixtures/bobs_discount/bobs_discount_plans.pdf`
- Commit: `5bd057a`

### Task 2: Run Golden Tests + Iterate Fixes

**Run 1** (baseline): Crow Cass 0%, Bob's Discount 0%
- Root cause: `Claude returned invalid JSON` on multiple sheets (truncated at max_tokens=8000)

**Fix batch applied (commit `12c057a`):**

| Fix | File | Reason |
|-----|------|--------|
| max_tokens 8000→16000 | `claude_analyzer.py` | Response truncation on complex sheets |
| json-repair fallback | `claude_analyzer.py` | Recovers truncated JSON (trailing comma, unterminated string) |
| CMU Paint gallons→SF | `calculator.py` + `aggregator.py` | Golden CSV tracks SF area, not computed gallons |
| Ladder height spec | `aggregator.py:_extract_spec_for_name` | `"ladder H-20'"` → `"Ladder-H-20'"` (same as Column spec) |
| civil_site count pass | `sheet_pass_matrix.py` | Bollards/hydrants are discrete EA items on site plans |
| EA fractional filter | `calculator.py:_calculate_from_measurement` | Reject qty<1 EA from dimension noise (0.10 bollard, 0.01 stairs) |

**Run 2** (post-fix): Crow Cass 20% (2/10), Bob's Discount 0% but 2 items now FAIL (not MISSING)

**Run 3** (confirmation): Same scores — confirmed stable ceiling with Haiku-4.5

### Task 3: Update 20-UAT.md

- Updated Golden regression section (§2) with per-item PASS/FAIL/MISSING table for both projects
- Added root-cause analysis for each failing item
- Updated generalization test count: 99/99 (was 55/55, grew from 20-09 additions + 4 new 20-10 tests)
- Human verification checklist updated to reflect completed runs

---

## Final Scores

| Project | Golden Items | Score | Status |
|---------|-------------|-------|--------|
| Crow Cass | 10 | 20% (2/10) | Below 97% threshold |
| Bob's Discount | 12 | 0% (0/12) | Below 97% threshold |

**Passing items (Crow Cass):**
- Exposed Structure 395,673 SF (err=0.5%) ✅
- Sealed Concrete 395,673 SF (err=0.5%) ✅

**Closest failing items:**
- Bob's Discount Doors-HM: ai=3 vs golden=5 (40% err)
- Bob's Discount Doors-WD: ai=3 vs golden=7 (57% err)

---

## Root-Cause Analysis (General — No Project-Specific Hardcoding)

The remaining gaps are caused by **Claude-Haiku-4.5 extraction limitations** on complex construction drawings:

1. **Symbol grid counting** (Bollards 1 vs 28, Columns 0 vs 132): Haiku cannot reliably count large grids of symbols across multi-sheet warehouse drawings even with explicit COUNT_PROMPT instructions.

2. **CMU wall area aggregation** (8 vs 2,204 SF): AI extracts component count from detail sheets rather than accumulating total wall area across multiple elevation sheets.

3. **Missing discrete items** (Ladder, Lift, Mobilization, Stairs): These single-count items appear in notes/details that Haiku's extraction passes do not consistently surface.

4. **Exterior elevation items** (EIFS, CMU Paint, Canopy for Bob's): Elevation measure pass runs with Sonnet but the items still don't appear in output — suggests the Bob's Discount elevation sheets have a layout that Haiku/Sonnet doesn't parse into SF measurements.

5. **Partial door schedule extraction** (3 vs 5-7): Door schedule rows partially extracted; remaining rows may be on continuation sheets or cut off in JSON output.

**All fixes applied are general rules.** No project-specific quantity hardcoding was introduced.

---

## Deviations from Plan

### Auto-fixed Issues

**[Rule 1 - Bug] Claude returned invalid JSON on complex sheets**
- Found during: Task 2 Run 1
- Issue: `max_tokens=8000` caused truncated responses on multi-schedule sheets; JSON parse failed
- Fix: Increase to 16000 + json-repair library fallback
- Files: `claude_analyzer.py`
- Commit: `12c057a`

**[Rule 1 - Bug] CMU Paint produced wrong unit (gallons vs SF)**
- Found during: Task 2 analysis of Bob's Discount 0% score
- Issue: `ESTIMATION_TABLES["cmu_paint"]` computed gallons; golden CSV expects SF area
- Fix: Changed unit_out from "gallons" to "sq_ft"; moved to SF area passthrough in `_apply_formula`
- Files: `calculator.py`, `aggregator.py`
- Commit: `12c057a`

**[Rule 2 - Missing Critical] Ladder height spec not extracted**
- Found during: Task 2 analysis — "Ladder" mapped to "Ladder" not "Ladder-H-20'/24'"
- Fix: Added "Ladder" branch to `_extract_spec_for_name` (same as Column logic)
- Files: `aggregator.py`
- Commit: `12c057a`

**[Rule 2 - Missing Critical] Civil site plan missing count pass**
- Found during: Task 2 analysis — bollards=0.10 from noise, not 28 from counting
- Fix: Added "count" pass to civil_site in PASS_MATRIX
- Files: `sheet_pass_matrix.py`
- Commit: `12c057a`

**[Rule 1 - Bug] Dimension noise producing fractional EA counts**
- Found during: Task 2 Run 2 — Bollards 0.10 EA, Stairs 0.01 EA from dimension annotations
- Fix: Added `if calc_unit == "ea" and calc_qty < 1: return None` gate in `_calculate_from_measurement`
- Files: `calculator.py`
- Commit: `12c057a`

---

## Test Results

```
pytest tests/test_takeoff_generalization.py -v   → 99/99 PASS (100%)
pytest tests/test_golden_takeoff.py -v -m golden → 0/2 PASS (Crow 20%, Bob 0%)
```

Generalization suite remains at 100% through all changes — no regressions.

---

## Next Phase Readiness

**Phase 20 Success Criterion #2:** Golden regression ≥97% on Crow + Bob — **NOT MET**

Remaining gap requires one or more of:
- Claude-Sonnet-4.x model for ALL passes (currently Haiku for most floor/civil passes)
- Active operator override of golden CSV tolerances for known Haiku limits
- Additional iterative runs (non-deterministic — scores may improve on retry)
- Future work: model routing improvements or prompt engineering targeting Haiku's specific failure modes

**No architectural decisions needed.** All pipeline infrastructure is in place; the gap is model capability, not code architecture.

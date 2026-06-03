---
phase: 20-takeoff-measurement-precision
plan: 10
subsystem: golden-regression
status: human_needed
tags: [golden, regression, crow-cass, bobs-discount]

depends_on: ["20-08", "20-09"]
provides: ["golden-fixture-docs", "golden-run-results"]
affects: ["20-UAT.md", "20-VERIFICATION.md"]

metrics:
  crow_cass_score: 0.20
  bobs_discount_score: not_run
  generalization: "97/97 pass"
  completed: "2026-06-04"
---

# Phase 20 Plan 10: Golden Regression — Summary

**Status:** Human verification required — golden threshold not met

## Task 0–1: Fixture setup

- PDFs present: `tests/fixtures/crow_cass/crow_cass_plans.pdf`, `tests/fixtures/bobs_discount/bobs_discount_plans.pdf`
- README **Golden regression fixtures** section (commit `5bd057a`)
- `scripts/setup_golden_fixtures.sh` copies from `uploads/` when sources exist

## Task 2: Golden test runs

| Fixture | Score | Pass (≥97%) | Notes |
|---------|-------|-------------|-------|
| Crow Cass | **20.0%** (2/10) | No | Sealed Concrete + Exposed Structure within ±3%; 8 items missing/wrong |
| Bob's Discount | Not re-run this session | — | Prior partial run exists in `output/`; full re-run deferred |

### Crow Cass per-item (run `Crow_Cass_Test_20260604_011717`, baseline pipeline)

| Item | Status |
|------|--------|
| Sealed Concrete | PASS (0.5% err) |
| Exposed Structure | PASS (0.5% err) |
| Bollards | FAIL (0.07 vs 28 EA) |
| CMU Wall | FAIL |
| Columns-H-35' | MISSING |
| Internal Tilt up walls | MISSING |
| Ladder, Lift, Mobilization, Stairs | MISSING |

### Iteration attempted (reverted)

Adding `schedule` pass to **all** floor plans dropped Crow score to **0%** (Flooring 437K SF returned; sealed concrete lost). Reverted to `count+measure` only; added optional `schedule` pass when title block contains `TAKEOFF`/`QUANTITY LEGEND` keywords.

### Code changes kept (general rules)

- `calculator._detect_project_type`: room content boosts industrial; removed bare `"tenant"` retail keyword
- `pdf_analyzer`: passes `sheet_type_hint` into pipeline pages
- `plan_passes(sheet_type, title_block_text)`: conditional schedule pass for legend tables
- `sheet_pass_matrix`: restored `civil_site` → `["measure"]` only

## Task 3: UAT

`20-UAT.md` updated with measured Crow score and Bob status.

## Human checkpoint

Golden ≥97% is **not** achieved on Crow Cass. Root cause: A-101 takeoff legend quantities not extracted as schedule rows (legend text is on sheet body, not title block). Next work should target legend OCR / schedule pass triggering / MEASURE_PROMPT legend extraction — not project-specific quantity hacks.

**Resume signal:** Type `approved` to accept documented gap, or list items to prioritize for another iteration.

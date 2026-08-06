---
phase: 28-accuracy-remediation-crow-defects
plan: 01
subsystem: pipeline
tags: [calculator, corroboration, provenance, flag-dont-guess, detail-sheet, crow, paid-run-evidence]

# Dependency graph
requires:
  - phase: 23-measurement-engine
    provides: "the RC-6 / 23-15 detail-sheet guard on the dimension path, and the `provenance` field threaded from fusion into the calculated row"
  - phase: 24-determinism
    provides: "the two saved paid Crow runs (A/B) this plan's gate reasons over, and the skip-loudly / self-grep gate idiom"
provides:
  - "`_DETAIL_SHEET_NOT_AN_INSTALL_COUNT` — the detail-sheet item-type list, now existing exactly once and consulted by both calculator entry points"
  - "`_count_corroboration(provenance, sheet_type, item_type, qty_source)` — a four-valued verdict: geometry | schedule | detail_sheet_only | none"
  - "`count_corroboration` and `count_evidence_sheet_kind` on every count row `_calculate_from_component` emits, carried through `_normalize_calculated` into `aggregate_takeoff`"
  - "an uncorroborated count now sets `needs_review` with a sheet-naming, number-free reason an estimator can act on"
  - "tests/test_phase28_count_corroboration.py — 24 free checks, mutation-verified non-vacuous"
affects: [28-02, 28-03, 28-06, 28-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "a verdict is RECORDED at the calculator layer and ACTED ON downstream — the record/decide split that keeps this plan's blast radius to one function"
    - "self-reported model confidence is not evidence; corroboration is a separate, recorded axis from confidence"
    - "a gate asserts against two frozen runs' own recorded fields, never against a golden number"

key-files:
  created:
    - tests/test_phase28_count_corroboration.py
  modified:
    - src/bobbytailor/pipeline/calculator.py
    - src/bobbytailor/pipeline/reporter.py
    - tests/test_confidence_flagging.py

key-decisions:
  - "`geometry` outranks the sheet kind: instance bounding boxes on a details sheet are still bounding boxes, so a geometry-backed count is corroborated wherever it was read."
  - "`text_layer` provenance is NOT corroboration — a printed word is not a counted object, so it falls through to `none` / `detail_sheet_only` like any prose count."
  - "Every route out of `_calculate_from_schedule` emits `count_corroboration: schedule`, because a table printed on the plans stating a quantity IS the corroboration. This is what keeps the 29-EA hollow-metal door-frame row publishable after 28-03."
  - "The uncorroborated review reason names the sheet and the confirmation to go get, and states NO number — a test asserts the reason is digit-free once the sheet name is removed."
  - "A plan premise was measured false and asserted rather than dropped: run A's `Door Frames-HM` row carries `provenance: geometry`, not null. The gate therefore asserts the weaker true claim (uncorroborated OR geometry-backed-and-vanished) instead of the plan's stronger false one."

patterns-established:
  - "Record-then-decide: the calculator writes a verdict, the aggregator makes the publish call. Two plans, one decision point."
  - "Shared-constant-with-liveness-proof: a hoisted constant is proven to be the object the consumer reads by monkeypatching a member out and watching the consumer's answer move."
  - "Self-audit greps assemble their forbidden tokens from halves, and mode checks use a regex over call sites rather than a substring scan — otherwise the check trips on its own source."

# V4-FIX-01 reads "No count publishes MEASURED / needs_review=False without corroboration."
# 28-01 writes the verdict; 28-03 makes the publish decision and carries the same requirement in
# the ROADMAP. Marking it complete here would close a requirement whose operative verb — publish —
# this plan deliberately did not touch.
requirements-completed: []
requirements-advanced: [V4-FIX-01]

coverage:
  - id: D1
    description: "The RC-6 / 23-15 detail-sheet item-type list exists once and both calculator entry points read that same object"
    requirement: "V4-FIX-01"
    verification:
      - kind: unit
        ref: "tests/test_phase28_count_corroboration.py#test_the_constant_holds_exactly_what_the_inline_tuple_held"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_count_corroboration.py#test_the_constant_is_what_the_measurement_path_actually_consults"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_count_corroboration.py#test_the_constant_is_what_the_count_path_actually_consults"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every count row records a corroboration verdict and the sheet kind it was read from; an install count off a details sheet is marked as counting detail drawings"
    requirement: "V4-FIX-01"
    verification:
      - kind: unit
        ref: "tests/test_phase28_count_corroboration.py#test_an_install_count_read_off_a_details_sheet_is_marked_as_counting_drawings"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_count_corroboration.py#test_an_uncorroborated_count_on_any_other_sheet_kind_gets_its_own_verdict"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_count_corroboration.py#test_the_sheet_kind_is_carried_verbatim"
        status: pass
    human_judgment: false
  - id: D3
    description: "No quantity moved and no row was dropped by the verdict; provenance is not rewritten"
    requirement: "V4-FIX-01"
    verification:
      - kind: unit
        ref: "tests/test_phase28_count_corroboration.py#test_the_verdict_moves_no_quantity_and_drops_no_row"
        status: pass
      - kind: integration
        ref: "python3 -m pytest -q → 2208 passed, 1 skipped, 2 deselected"
        status: pass
    human_judgment: false
  - id: D4
    description: "Printed-schedule rows come out corroborated, so the authoritative door-schedule row survives 28-03 untouched"
    requirement: "V4-FIX-01"
    verification:
      - kind: unit
        ref: "tests/test_phase28_count_corroboration.py#test_every_route_out_of_the_schedule_calculator_comes_out_corroborated"
        status: pass
      - kind: integration
        ref: "tests/test_phase28_count_corroboration.py#test_the_saved_runs_printed_schedule_rows_are_corroborated_and_untouched"
        status: pass
    human_judgment: false
  - id: D5
    description: "The verdict is shown, on the two saved paid runs' own recorded rows, to account for every published quantity that varied between them"
    requirement: "V4-FIX-01"
    verification:
      - kind: integration
        ref: "tests/test_phase28_count_corroboration.py#test_the_saved_runs_every_quantity_that_moved_was_a_count_nothing_confirmed"
        status: pass
      - kind: integration
        ref: "tests/test_phase28_count_corroboration.py#test_the_saved_runs_a_geometry_backed_number_never_moved"
        status: pass
    human_judgment: false
  - id: D6
    description: "The verdict reaches a client report with the right sheet named, and the flagged Stairs row reads as an estimator would need it to"
    verification: []
    human_judgment: true
    rationale: "The review-reason wording is estimator-facing prose. Tests pin its structure (names the sheet, names the confirmation, states no number) but whether it actually reads as actionable to an estimator is judgment, and it cannot be seen on a real report without a paid run, which is a human spend decision."

# Metrics
duration: 178min
completed: 2026-08-06
status: complete
---

# Phase 28 Plan 01: Record What Corroborated Each Count Summary

**Every counted quantity now leaves the calculator carrying a four-valued corroboration verdict — geometry, schedule, detail_sheet_only or none — and the count path finally consults the `sheet_type` argument it has been handed and ignoring since RC-6, which is how a count of stair DETAILS on A-401 reached the client report as a count of stairs.**

## Performance

- **Duration:** 178 min (~66 min of it the full offline suite, run once at plan end)
- **Started:** 2026-08-06T20:52:00Z
- **Completed:** 2026-08-06T23:50:00Z
- **Tasks:** 3 (all TDD or test-only)
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments

- **The asymmetry is closed.** `_calculate_from_measurement` has refused a detail-sheet install quantity since RC-6 via an inline tuple; `_calculate_from_component` received the identical `sheet_type` argument and never looked at it. The list is now one module constant, `_DETAIL_SHEET_NOT_AN_INSTALL_COUNT`, and both paths read that same object — proven by monkeypatching a member out and watching each path's answer move with it.
- **The confidently-wrong `Stairs` row is now a flagged row.** A count read off a sheet the run itself typed `detail`, for an item type in the shared list, comes out `count_corroboration: detail_sheet_only`, `needs_review: True`, with a reason naming the sheet, saying the reading counts detail drawings rather than installed objects, and telling the estimator to confirm against a plan sheet or schedule. The reason states no number.
- **Nothing was deleted and nothing moved.** The quantity, the raw value and `provenance` are byte-identical in every branch; no input that produced a row before produces `None` now. 28-03 owns the publish decision — this plan only records, which is what kept the change to one function plus a two-key passthrough.
- **The corroborated rows are protected.** Every route out of `_calculate_from_schedule` emits `count_corroboration: schedule`; a geometry-backed count is untouched — no new flag, no new reason. All 12 `authoritative plan schedule` rows across the two saved runs classify `schedule`.
- **The verdict was tested against real evidence, not a golden number.** `tests/test_phase28_count_corroboration.py` reads both frozen paid-run directories read-only, computes the differing published keys at runtime, and asserts properties of the verdict over the runs' own recorded rows. Mutating `_count_corroboration` to trust everything makes two of those tests fail — the gate is not vacuous.
- **Full offline suite: 2208 passed, 1 skipped, 2 deselected** (baseline 2183/1/2; +25 = the 24 new checks plus one added to `test_confidence_flagging.py`). The 24-09 determinism harness, `test_phase23_acceptance.py`, `test_phase24_acceptance.py` and `test_four_set_coverage.py` are all inside that run and all green.

## Task Commits

1. **Task 1: One list, two paths** — `10026aa` (test, RED) → `58982f6` (feat, GREEN)
2. **Task 2: Every count row records what corroborated it** — `4009282` (test, RED) → `4832999` (feat, GREEN)
3. **Task 3: Pin the verdict against the saved runs** — `95a2c9d` (test)

No REFACTOR commit was needed on either TDD task; the GREEN implementations were already at their final shape.

## Files Created/Modified

- `src/bobbytailor/pipeline/calculator.py` — `_DETAIL_SHEET_NOT_AN_INSTALL_COUNT` and `_SCHEDULE_QTY_SOURCES` module constants; `_count_corroboration()` and `_uncorroborated_count_reason()`; the inline tuple in `_calculate_from_measurement` replaced by a membership test against the constant; `_calculate_from_component` stamps `count_corroboration` + `count_evidence_sheet_kind` and folds the uncorroborated verdicts into the existing `needs_review` / `reasons` computation; all three emitted shapes in `_calculate_from_schedule` carry `count_corroboration: schedule`.
- `src/bobbytailor/pipeline/reporter.py` — `_normalize_calculated` passes `count_corroboration` and `count_evidence_sheet_kind` through to the aggregator (see deviation 1).
- `tests/test_phase28_count_corroboration.py` — **new.** 24 checks in four groups: the shared constant and its liveness, the verdict on synthetic rows, the verdict against the two frozen runs, and the module's own contract (runs free, reads read-only, names no golden literal).
- `tests/test_confidence_flagging.py` — `test_high_confidence_count_not_flagged` revised and split (see deviation 2).

## Decisions Made

- **`geometry` outranks the sheet kind.** Bounding boxes counted on a details sheet are still bounding boxes. `_count_corroboration("geometry", "detail", "stairs") == "geometry"`, asserted directly.
- **`text_layer` provenance is not corroboration.** It is a string read off the PDF, not a bbox census. Treating a printed word as a counted object is the same category error this phase exists to fix, so `text_layer` falls through to `none` / `detail_sheet_only` like any prose count.
- **The verdict function takes `qty_source` as a fourth, optional input.** That lets one function serve `_calculate_from_component` (which has no `qty_source`), `_calculate_from_schedule`, and the evidence gate reading recorded rows — instead of a second copy of the schedule rule living in the test.
- **The reason text names the sheet and states no number.** `test_an_install_count_read_off_a_details_sheet_is_marked_as_counting_drawings` strips the sheet name out of the reason and asserts the remainder is digit-free, so nobody can quietly write an expected count into an estimator-facing message.
- **`needs_review` widens to every uncorroborated count, not just detail-sheet ones.** Per the plan. A prose count off a floor plan with nothing behind it is flagged too, with its own reason that does not misdescribe the sheet.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] `count_corroboration` was written but could never be read**

- **Found during:** Task 2 (Every count row records what corroborated it)
- **Issue:** `reporter._normalize_calculated` whitelists keys on the way from the calculator to `aggregate_takeoff`, and it is the ONLY gate between them. `count_corroboration` and `count_evidence_sheet_kind`, written on the calculator row, were being dropped there. The plan's own `key_links` says "28-03 consumes `count_corroboration`; this plan writes it" — and 28-03's stated file list is `aggregator.py` only, so nobody downstream was going to add the passthrough. Without it this plan's entire artifact is inert.
- **Fix:** Added both keys to the `_normalize_calculated` whitelist with a comment saying why the whitelist is the load-bearing seam.
- **Files modified:** `src/bobbytailor/pipeline/reporter.py`
- **Verification:** `test_the_verdict_survives_normalisation_into_the_report_layer` asserts the verdict is readable on the normalised row; full suite green.
- **Committed in:** `4832999` (Task 2 commit)

**2. [Rule 1 - Bug] An existing test asserted the defect**

- **Found during:** Task 2
- **Issue:** `tests/test_confidence_flagging.py::test_high_confidence_count_not_flagged` asserted that a count with `confidence: "high"` and NOTHING behind it came out `needs_review: False`. That is exactly the confidently-wrong row this phase exists to kill — self-reported confidence is the model's opinion of itself, not evidence. Left standing it would have blocked the plan's stated behaviour.
- **Fix:** Revised the test to give the row `provenance: geometry` (a genuinely corroborated high-confidence count, still unflagged) and added `test_high_confidence_is_not_corroboration` asserting the other half — same input minus the geometry, now flagged with a sheet-naming reason. The check was split, not deleted.
- **Files modified:** `tests/test_confidence_flagging.py`
- **Verification:** Both tests pass; full suite green.
- **Committed in:** `4832999` (Task 2 commit)

### Plan premise falsified by the evidence

**3. The plan's `measured_facts` table is wrong about `Door Frames-HM` run A**

- **Found during:** Task 3
- **Plan claimed:** "`Door Frames-HM`, run A | `4.0 EA`, `provenance null`" and, generally, "every published quantity that DIFFERED between the runs traces to a row with **no** `provenance`."
- **Measured:** the backing row in `VisionOnly_P24DET_Crow_20260806_194607` is `{"description": "dock door frame", "calculated_quantity": 4.0, "provenance": "geometry"}`. Two of the three varying keys (`Stairs`, `Lift`) are uncorroborated; the third is not.
- **What was done:** the gate asserts the true, weaker claim instead of the plan's false stronger one. Every backing row of a varying key is either (a) classified uncorroborated by the verdict, or (b) classified `geometry` **and absent altogether from the other run** — i.e. the number did not move, the ROW vanished, which is an extraction-pass variance one layer upstream that a corroboration verdict cannot and should not claim to catch. `test_the_saved_runs_a_geometry_backed_number_never_moved` pins the same fact from the other side: every geometry row in run B has a quantity-identical counterpart in run A, and the one A-only geometry row is proven to belong to a varying published key. The docstrings state the falsification by name.
- **Impact:** none on the code. It narrows what 28-06 ("the classification is proved to cover every number that moved") can honestly claim: one of the three moved for a reason no corroboration verdict explains.

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 bug) + 1 plan premise falsified and documented.
**Impact on plan:** Both auto-fixes were required for the plan's artifact to exist and function. No scope creep — the reporter change is two whitelist entries, and the test change split one assertion into two rather than weakening it.

## Issues Encountered

- **Self-defeating self-audit greps, twice.** The read-only check spelled write modes out as string literals and therefore found them in its own source; the golden-literal check spelled `_golden.csv` out and found that too. Both fixed the 24-09 / 24-10 way — tokens assembled from halves, and the file-mode check rewritten as a regex over `open` call sites (asserting every one is `with`-managed and states a read mode) rather than a substring scan for a write mode.
- **The offline suite is slower than the recorded baseline.** 1:03:58 wall for the full run (plan said ~56 min), and a 30-module targeted sweep took 42 min on its own. Both were run in the foreground and waited on inline.
- **`.planning/paid-run-evidence/` verified untouched** — `git status --porcelain` over that path returned `0` before every commit and after the final one (T-28-02).

## Risk Warning (CLAUDE.md gitnexus mandate)

`gitnexus impact _calculate_from_component --direction upstream` returned **risk: CRITICAL** — 7 impacted symbols, 5 affected execution flows (`run_project`, `run_project_scrape`, `run_analyze_from_manifest`, `run_pdf_analysis`, `apply_estimation_tables`), 2 modules. The change was made anyway because it *is* the phase's purpose, and it was made additively: two new keys plus a widening of `needs_review`, with no quantity, no `provenance` and no row-presence behaviour altered. The full offline suite passing at 2208/1/2 is the evidence that the critical blast radius was not disturbed. The GitNexus index is stale (last indexed `14d4ec0`) and should be re-analysed before the next phase-28 plan edits these symbols.

## User Setup Required

None — no external service configuration, no package installed, no paid API touched.

## Next Phase Readiness

- **28-03 is unblocked.** `count_corroboration` and `count_evidence_sheet_kind` are on the calculated row and readable from `aggregate_takeoff`. The `_row_status` branch it needs to write can read a recorded fact rather than re-deriving one from a path it cannot see.
- **28-03 must expect the `Lift` PASS to be lost.** Run B's accidental `Lift` = 1 came off a dock-leveler section detail on A-401 and now classifies `detail_sheet_only`. Losing that PASS when 28-03 stops publishing uncorroborated counts is the correct outcome, not a regression.
- **28-06 should be replanned against deviation 3.** Its ROADMAP line promises the classification is "proved to cover every number that moved between the two saved runs". It does not: `Door Frames-HM` moved because a geometry-backed row vanished between extraction passes, which no corroboration verdict explains. 28-06 needs either a second axis (row presence) or a narrower claim.
- **No accuracy figure was produced and none can be.** `score_report_dir.py` re-scores frozen artifacts and returns the same numbers whatever the code does. A post-fix Crow number requires a paid run, which is a human spend decision.

## Self-Check: PASSED

All five claimed files exist on disk; all five claimed commit hashes resolve in `git log`.
`git status --porcelain .planning/paid-run-evidence/` returns `0` — the frozen evidence tree
is byte-unchanged (T-28-02).

---
*Phase: 28-accuracy-remediation-crow-defects*
*Completed: 2026-08-06*

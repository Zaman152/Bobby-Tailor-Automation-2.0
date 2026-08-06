---
phase: 28-accuracy-remediation-crow-defects
plan: 03
subsystem: pipeline
tags: [aggregator, corroboration, publish-decision, flag-dont-guess, blank-not-zero, detail-sheet, crow]

# Dependency graph
requires:
  - phase: 28-accuracy-remediation-crow-defects
    plan: 01
    provides: "`count_corroboration` and `count_evidence_sheet_kind` stamped on every count row the calculator emits, and carried through `_normalize_calculated` into `aggregate_takeoff`"
  - phase: 23-measurement-engine
    provides: "the blank-not-zero contract (INV-08 S12) and the two existing withheld-reading blank paths — suppressed-library and unit-class-conflict — whose shape this plan copies rather than reinvents"
provides:
  - "`_CORROBORATION_RANK` + `_stronger_corroboration(a, b)` — the ONE expression of the verdict precedence, asserted to have no second copy"
  - "`_count_is_uncorroborated(bucket)` — the two-state test (a count contributed AND nothing backed it); an unset verdict is never read as an absence of evidence"
  - "`_new_bucket()` — the bucket default hoisted out of a lambda so its declaration is directly testable"
  - "`DETAIL_SHEET_COUNT_UNMEASURED` — a new `source` marker inside the existing `_UNMEASURED_SOURCES` frozenset, special-cased by no consumer"
  - "a withheld-detail-count blank path in `aggregate_takeoff`, on the same two-branch shape as the unit-class-conflict block"
  - "a `_row_status` branch that cannot return `ITEM_MEASURED` for an uncorroborated count"
  - "tests/test_phase28_uncorroborated_counts.py — 30 free checks, mutation-verified non-vacuous"
affects: [28-06, 28-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "record-then-decide, completed: 28-01 recorded the verdict, this plan made the publish call — one decision point, two plans, one blast radius each"
    - "a withheld reading always leaves a ROW that quotes what it withheld; a deletion and a zero read the same to a client"
    - "a new `source` marker joins the unmeasured-marker frozenset instead of being special-cased, and a test asserts no consumer names it"
    - "the residual a plan CANNOT close is committed as a tripwire test that fails when it is closed, so the gap is greppable rather than remembered"

key-files:
  created:
    - tests/test_phase28_uncorroborated_counts.py
  modified:
    - src/bobbytailor/pipeline/aggregator.py

key-decisions:
  - "Best evidence wins the roll-up (the mirror of `_worse_conf`): one schedule- or geometry-backed contributing row vouches for the whole bucket, because corroboration is evidence while confidence is a claim about certainty."
  - "`None` (no count contributed) is kept distinct from `\"none\"` (a count contributed and nothing backed it). Collapsing them would flag every area and length in the take-off."
  - "The flag is set on the bucket alongside the reason, not only the status — a row reading NEEDS REVIEW while carrying `needs_review: False` and `auto_verified: True` flags itself to a human and clears itself to every numeric consumer at the same time."
  - "`_row_status` keeps the branch anyway, as the invariant at the single publish point: it is asserted directly on hand-built buckets, so a bucket assembled by any future path still cannot publish an unconfirmed count as MEASURED."
  - "V4-FIX-01 is NOT ticked. Two calculator producers emit EA counts and stamp no verdict, so the requirement's literal claim is not yet true app-wide; the residual is a committed test, not a sentence."

patterns-established:
  - "Spy on the single publish point to observe an internal roll-up: `_row_status` is handed the bucket, so monkeypatching it reads the ACTUAL record rather than a reconstruction of it."
  - "Precedence-lives-once, asserted structurally: the ranking table's name is counted in the module source and must appear only in its own definition and in its one reader."
  - "A plan's stated boundary becomes a test whose failure is the signal that someone closed it."

# V4-FIX-01 reads "No count publishes MEASURED / needs_review=False without corroboration."
# The publish decision now enforces that for every count carrying a recorded verdict — which is
# every count `_calculate_from_component` and `_calculate_from_schedule` emit. It is NOT enforced
# for counts from `_calculate_from_measurement`'s whole-EA path or from
# `_calculate_from_civil_structures`, because neither records one and this layer cannot see the
# sheet a number came off. Ticking the requirement would claim a coverage this plan measured to be
# absent. 28-07 is its closer.
requirements-completed: []
requirements-advanced: [V4-FIX-01]

coverage:
  - id: D1
    description: "Every bucket rolls up what corroborated its count, from ONE expression of the precedence, and the accumulation loop is proved to consult that one helper"
    requirement: "V4-FIX-01"
    verification:
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_rollup_combines_two_verdicts_in_one_place"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_rollup_the_precedence_is_expressed_exactly_once"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_rollup_the_loop_consults_that_one_helper"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_rollup_one_corroborated_row_vouches_for_the_whole_bucket"
        status: pass
    human_judgment: false
  - id: D2
    description: "An unset verdict is treated as not-a-count, never as uncorroborated — areas, lengths, blanks and the injected convention are untouched"
    requirement: "V4-FIX-01"
    verification:
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_rollup_a_bucket_with_no_count_rows_keeps_an_unset_verdict"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_an_area_row_beside_an_uncorroborated_count_is_untouched"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_row_status_is_unchanged_for_every_bucket_that_never_counted"
        status: pass
    human_judgment: false
  - id: D3
    description: "A detail-sheet-only count publishes a BLANK that quotes the withheld reading and names the sheet, and never a number"
    requirement: "V4-FIX-01"
    verification:
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_a_detail_sheet_count_never_reaches_a_published_quantity"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_the_withheld_blank_is_still_a_row_that_quotes_what_it_withheld"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_the_withheld_reason_suggests_no_count_of_its_own"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_a_corroborated_reading_of_the_same_object_keeps_its_quantity"
        status: pass
    human_judgment: false
  - id: D4
    description: "`_row_status` cannot return MEASURED for an uncorroborated count, and the flag/reason keep the published row self-consistent"
    requirement: "V4-FIX-01"
    verification:
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_row_status_refuses_measured_for_an_uncorroborated_count"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_an_uncorroborated_count_publishes_needs_review_end_to_end"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_row_status_still_reaches_the_plan_schedule_legend_branch"
        status: pass
    human_judgment: false
  - id: D5
    description: "The rows this rule was most likely to damage are proved untouched: the printed door schedule, the injected convention, a geometry-backed count, and every unrelated row in the same take-off"
    requirement: "V4-FIX-01"
    verification:
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_the_door_schedule_count_still_publishes_measured"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_the_injected_convention_still_publishes_as_a_standard_item"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_a_geometry_backed_count_still_publishes_measured_end_to_end"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_withholding_one_count_disturbs_no_other_row"
        status: pass
      - kind: integration
        ref: "python3 -m pytest -q → 2263 passed, 1 skipped, 2 deselected"
        status: pass
    human_judgment: false
  - id: D6
    description: "The rule's boundary is named rather than implied — two calculator producers emit counts and stamp no verdict, so this layer cannot see them"
    requirement: "V4-FIX-01"
    verification:
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_the_rules_boundary_is_a_recorded_verdict_and_this_is_it"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_uncorroborated_counts.py#test_the_residual_this_plan_does_not_close_is_named_not_implied"
        status: pass
    human_judgment: false
  - id: D7
    description: "The withheld `Stairs` blank and the flagged uncorroborated count read to an estimator as actionable rather than as noise"
    verification: []
    human_judgment: true
    rationale: "The reason wording is estimator-facing prose. Tests pin its structure (quotes the withheld reading, names the sheet, states no count of its own, says what confirmation to get) but whether a reviewer acts correctly on a blank where a number used to sit cannot be seen without a paid run, which is a human spend decision. `score_report_dir.py` re-scores frozen artifacts and returns the same numbers whatever this code does."

# Metrics
duration: 105min
completed: 2026-08-07
status: complete
---

# Phase 28 Plan 03: An Uncorroborated Count Cannot Publish as Measured Summary

**The verdict 28-01 recorded now decides what publishes: a count whose only evidence was a details sheet is withheld as a blank that quotes the reading it withheld and names the sheet, any surviving count with no printed schedule and no counted geometry behind it publishes NEEDS REVIEW, and `_row_status` — the single place a bucket becomes `ITEM_MEASURED` — can no longer call an unconfirmed count measured.**

## Performance

- **Duration:** 105 min (64 min of it the full offline suite, plus a 16-min acceptance-gate sweep, both run in the foreground)
- **Started:** 2026-08-06T22:05:00Z
- **Completed:** 2026-08-06T23:50:00Z
- **Tasks:** 3 (all TDD), plus one test-only follow-up committing the residual
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments

- **The publish decision is made, once, where it belongs.** `_row_status` is the single place a bucket becomes `ITEM_MEASURED`, and it now refuses to for a count nothing corroborated. The branch sits after the existing `needs_review` check, so it can only ever add a flag and never clear one, and before the `plan_schedule_legend` branch, so nothing below it can promote an unconfirmed count back to MEASURED.
- **A count of stair details is no longer published as a count of stairs.** A row whose recorded verdict is `detail_sheet_only` is diverted before it can reach `bucket["quantity"]`, exactly as a unit-class conflict is, and materialises as a blank on the contract that already exists in this file twice: no quantity, `needs_review=True`, confidence low, a `source` marker, a reason quoting the withheld description, value and sheet, and a `source_rows` entry whose formula names the rule that withheld it. Nothing is deleted — `line_count` is 0 and the audit row is there.
- **The corroborated rows are proved untouched, one assertion each.** A count read out of a table printed on the plans still publishes `MEASURED` with `needs_review=False`; a geometry-backed count still publishes `MEASURED` and `auto_verified=True` with an empty reason list; the injected `Mobilization` convention still returns `STANDARD ITEM`; and a whole take-off's other rows are asserted **byte-identical** between a run with and without the withheld row.
- **The precedence exists exactly once and the loop is proved to consult it.** `_CORROBORATION_RANK` is counted in the module's own source and must appear only in its definition and in `_stronger_corroboration`, its one reader. Separately, replacing that helper at runtime moves the bucket's recorded verdict with it — so the roll-up cannot be a second, drifting copy.
- **Absence is never read as "no evidence".** A row carrying no verdict — every area, every length, every blank, the injected convention — leaves the field unset, and `_count_is_uncorroborated` is a two-state test that answers False for it. That is the difference between flagging the rows this phase is about and flagging the entire take-off, and it is why not one existing assertion in `tests/test_aggregator.py` had to change.
- **The honest cost is paid, not clawed back.** Run B's `Lift` row scored a PASS at 1.00 off a dock-leveler SECTION detail on A-401 and was absent from run A entirely. Under this rule it becomes a flagged blank and that PASS is lost. Losing a coincidentally-right number is the correct outcome of the rule; nothing here is tuned to keep it, and no golden figure appears anywhere in the new module.
- **Full offline suite: 2263 passed, 1 skipped, 2 deselected** in 1:03:40 (baseline 2234/1/2; +29 = exactly the new module's checks, zero regressions). `test_phase23_acceptance.py`, `test_phase24_acceptance.py`, `test_four_set_coverage.py`, `test_coverage_ledger.py`, `test_reporter_accuracy.py` and the 24-09 determinism harness are all inside that run and all green; the two phase-acceptance gates plus both phase-28 modules were also run standalone (90 passed, 1 skipped, 16:06).

## Task Commits

1. **Task 1: Roll the corroboration verdict up onto the bucket** — `d646995` (test, RED) → `5470de3` (feat, GREEN)
2. **Task 2: A detail-sheet count publishes a blank, with its reading quoted** — `0bfc455` (test, RED) → `d008b4f` (feat, GREEN)
3. **Task 3: `_row_status` cannot return MEASURED for an uncorroborated count** — `2f5ac18` (test, RED) → `181c6ce` (feat, GREEN)
4. **Follow-up (test-only): name the residual this plan cannot close** — `8de7ae0`

No REFACTOR commit was needed on any of the three TDD tasks; each GREEN implementation was already at its final shape.

## Files Created/Modified

- `src/bobbytailor/pipeline/aggregator.py` — `DETAIL_SHEET_COUNT_UNMEASURED` added to `_UNMEASURED_SOURCES`; `_CORROBORATION_RANK`, `_CORROBORATED`, `_stronger_corroboration()`, `_count_is_uncorroborated()` and `_new_bucket()` (the bucket default hoisted out of the `defaultdict` lambda so its declaration is testable); the accumulation loop rolls the verdict up beside the `needs_review` roll-up; a `withheld_detail_counts` collector and its two-branch materialisation block; a post-loop pass that sets the flag and the reason on a surviving uncorroborated count; one branch in `_row_status` plus a docstring paragraph in the register of the existing HUMAN-INPUT one.
- `tests/test_phase28_uncorroborated_counts.py` — **new.** 30 checks in four groups: the roll-up and its single precedence, the withheld blank and its quoted reading, `_row_status` asserted directly and end to end, and the module's own contract (free, offline, golden-free).

## Decisions Made

- **The roll-up takes the BEST evidence, the mirror of `_worse_conf`.** The worst confidence wins there because confidence is a claim about certainty; the best corroboration wins here because corroboration is evidence. One row backed by a printed schedule vouches for the object even when a weaker reading of the same object landed in the same bucket.
- **Among uncorroborated verdicts, `detail_sheet_only` dominates `none`.** So the reason a reader is shown names the sheet kind rather than shrugging.
- **An unrecognised verdict string ranks with `none`** and is therefore never mistaken for corroboration — the fail-safe direction, asserted directly.
- **`_row_status` stays side-effect free.** It computes a status; the matching reason is set where every other reason is set. The flag is set with it (see deviation 1).
- **The `_row_status` branch is kept even though the aggregate path also flags.** It is the invariant at the publish point, asserted on hand-built buckets, so a bucket assembled by any future path still cannot publish an unconfirmed count as MEASURED.
- **V4-FIX-01 is advanced, not completed.** See the residual below.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] The status branch alone would have published a self-contradicting row**

- **Found during:** Task 3
- **Issue:** The plan asks for one branch in `_row_status` and for the reason to be set on the bucket. Implemented as literally written, a surviving uncorroborated count would publish `provenance: "NEEDS REVIEW"` while its own row still carried `needs_review: False` and — because `auto_verified` is computed as `has_rows and auto_verified and not needs_review and not is_unknown` — `auto_verified: True`. The row would flag itself to a human reading the status column and clear itself to every numeric consumer at the same time. That is a weaker version of the exact defect the plan exists to fix, and it contradicts the plan's own must-have ("no count reaches MEASURED with `needs_review=False`" is only half the sentence if the flag itself stays false).
- **Fix:** the post-loop pass that adds the reason also sets `needs_review = True` on the same bucket. The `_row_status` branch is kept regardless, as the invariant at the publish point, and is asserted directly on hand-built buckets so it is not dead code.
- **Files modified:** `src/bobbytailor/pipeline/aggregator.py`
- **Verification:** `test_an_uncorroborated_count_publishes_needs_review_end_to_end` asserts `needs_review is True` and `auto_verified is False` alongside the status; `test_row_status_refuses_measured_for_an_uncorroborated_count` asserts the branch independently of it.
- **Committed in:** `181c6ce` (Task 3 GREEN)

### Plan expectation that did not materialise

**2. No existing assertion in `tests/test_aggregator.py` changed, and that is the correct outcome**

- **Plan asked:** "go through `tests/test_aggregator.py` and update every assertion this branch changes. Each update must make the test say more than it did."
- **Measured:** zero assertions change. Every item dict in that module predates 28-01 and carries no `count_corroboration` key, so the rule's own stated rule — "absence is never read as uncorroborated" — leaves all 68 of them untouched. `tests/test_aggregator.py` passes at exactly the count it had before this plan (68), as does `test_coverage_ledger.py` (43).
- **What was done:** nothing was weakened or deleted to achieve that; the new module carries the stricter assertions instead, including the `test_withholding_one_count_disturbs_no_other_row` equality check over whole published rows. The plan's instruction is satisfied vacuously, and saying so is better than implying a sweep happened.

### The residual this plan cannot close (and why V4-FIX-01 is not ticked)

**3. Two calculator producers emit counts and stamp no corroboration verdict**

- **Found during:** the close-out check on whether V4-FIX-01 could honestly be ticked
- **Measured:** `_calculate_from_measurement` emits an EA row whenever a dimension annotation resolves to a whole quantity ≥ 1 (calculator.py:614-618), and `_calculate_from_civil_structures` emits catch basins / manholes / headwalls in EA unconditionally. Neither records a `count_corroboration`, so this layer reads them as not-a-count and they can still publish `MEASURED` with `needs_review=False`.
- **Why it was not auto-fixed here:** stamping a verdict is the RECORDING layer's job (28-01, `calculator.py`), and this plan's stated file list is `aggregator.py` only. The alternative — widening the rule so an absent verdict means "no evidence" — would flag every area and length in the take-off and directly contradicts the plan's Task 1 behaviour spec.
- **What was done instead:** committed as a tripwire, `test_the_residual_this_plan_does_not_close_is_named_not_implied`, which asserts both halves (each named producer still emits a count AND still records no verdict) and fails the moment either is fixed, with a failure message telling the reader to shorten the list deliberately.
- **Impact:** V4-FIX-01 is marked **advanced**, not completed. The publish decision its wording asks for is delivered and enforced for every count carrying a verdict; the requirement's literal universal claim is not yet true app-wide, and ticking it would be the over-claim this phase exists to end.

---

**Total deviations:** 1 auto-fixed (missing critical) + 1 plan expectation that did not materialise + 1 named residual.
**Impact on plan:** the auto-fix was required for the plan's own must-have to hold on a published row. No scope creep — it is one flag assignment inside the block that was already being added for the reason.

## Non-vacuity Evidence

- Each task's RED run failed exactly the checks its GREEN implementation then turned green: 8 (task 1), 6 (task 2), 3 (task 3), with the "still publishes MEASURED" guards passing in both directions.
- Two mutations of the shipped code were each observed to kill 4 checks: `_count_is_uncorroborated` forced to `False` (nothing is ever uncorroborated) and the `detail_sheet_only` diversion disabled (withheld counts summed after all). The file was restored and re-run green before the commit; `git diff` over `src/` is empty against HEAD.
- The module's two synthetic verdict groups are asserted through the ACTUAL bucket the aggregator hands to `_row_status`, not through a reconstruction, so a check cannot pass against a record the code never wrote.

## Issues Encountered

- **The tool's timeout is 10 minutes and the suite is 64.** The full run was launched orphaned (`nohup ... &` in a subshell, writing to a log) and polled in the foreground until the process exited — 1:03:40, `2263 passed, 1 skipped, 2 deselected`. The 16-minute acceptance sweep hit the same ceiling first and was polled the same way.
- **Two of my own expected row names were wrong before the code was.** `"stair detail"` canonicalises to `Stairs` (which is the real Crow row name, so the test got better), and a `plan_schedule_legend` row buckets under its cleaned legend label verbatim, not under a title-cased name. Both were test-side fixes made during RED, with no assertion weakened.
- **`.planning/paid-run-evidence/` verified untouched** — `git status --porcelain` over that path returned `0` before every commit and after the last one (T-28-02).

## Risk Warning (CLAUDE.md gitnexus mandate)

The index was re-analysed first (it was stale at `eaee06c`; now current — 13,375 nodes / 22,327 edges). `gitnexus impact _row_status --direction upstream` returned **risk: CRITICAL** — 5 impacted symbols, 5 affected processes (`run_project_scrape`, `aggregate_takeoff`, `run_analyze_from_manifest`, `run_pdf_analysis`, `generate_report`), 2 modules. `aggregate_takeoff` returned **HIGH** (7 impacted, 4 processes). Both changes were made anyway because they *are* the plan's purpose, and they were made additively: one new bucket field, one new diversion that mirrors an existing one, one new branch that can only add a flag, and one new `source` marker inside the frozenset every consumer already reads. The full offline suite at 2263/1/2 with zero regressions is the evidence the critical blast radius was not disturbed.

## Threat Flags

None. No new network endpoint, auth path, file access pattern or trust-boundary schema change. T-28-11 is mitigated (a count with no schedule and no geometry behind it can no longer return `ITEM_MEASURED`, asserted directly on the function). T-28-12 is mitigated (the withheld description, value and sheet are quoted in the row's reason and the row still appears). T-28-13 is met in the only way the tree allowed — no existing assertion changed at all, so none was weakened (see deviation 2). T-28-16 is mitigated and asserted from both sides: the marker is in `_UNMEASURED_SOURCES`, and a test scans `src/` and requires that no module outside `aggregator.py` names it. T-28-14 and T-28-15 were accepted as planned. T-28-SC is trivially met: no package was installed.

## Known Stubs

None.

## User Setup Required

None — no external service configuration, no package installed, no paid API touched.

## Next Phase Readiness

- **28-06 can read a rolled-up verdict off the bucket.** `count_corroboration` is on every bucket at the publish point, which is where a `quantity_route` column would be computed from. Note that a withheld detail-sheet row never reaches the accumulation loop, so its bucket's verdict is `None`, not `detail_sheet_only` — the route for that row is the `source` marker, not the roll-up.
- **28-07 inherits an unticked requirement and the exact reason.** V4-FIX-01's publish decision is delivered; its universal claim is not, because of the two unstamped producers in deviation 3. The gate should either assert the requirement *with that boundary in the same sentence* (the 24-10 precedent) or a short follow-up should stamp both producers in `calculator.py` first — at which point `test_the_residual_this_plan_does_not_close_is_named_not_implied` fails on purpose and must be shortened deliberately, not deleted.
- **The naive Crow score is expected to fall and that is the deliverable.** Run B's `Lift` PASS came off a dock-leveler section detail and is now a flagged blank; `Stairs` moves from a confident 90%-wrong number to a flagged blank. `Columns` and `Ladder` do not move — those need detection, which is Phase 25.
- **No accuracy figure was produced and none can be.** `score_report_dir.py` re-scores frozen artifacts and returns the same numbers whatever this code does. A post-fix Crow number requires a paid run, which is a human spend decision.

## Self-Check: PASSED

Both claimed files exist on disk; all seven claimed commit hashes resolve in `git log`.
`git status --porcelain .planning/paid-run-evidence/` returns `0` — the frozen evidence tree is
byte-unchanged (T-28-02). The new test module names no golden literal and imports nothing that
could reach a network, asserted by the module itself.

---
*Phase: 28-accuracy-remediation-crow-defects*
*Completed: 2026-08-07*

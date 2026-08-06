---
phase: 28-accuracy-remediation-crow-defects
plan: 02
subsystem: vision
tags: [fusion, symbol-binding, perimeter-ring, flag-dont-guess, coincidence-trap, crow, position-evidence]

# Dependency graph
requires:
  - phase: 23-measurement-engine
    provides: "`_is_2d_distributed` / `_is_collinear_strip` and the `_min_2d_span_pt` marker-size tolerance the new band test reuses"
  - phase: 24-determinism
    provides: "the unnamed-geometry ledger a refused binding falls through to, and the skip-loudly / self-auditing free-test idiom"
provides:
  - "`_occupancy_bands(values, tol)` — greedy band grouping that returns each band's MEMBERS, not its position"
  - "`_is_built_from_ring_runs(centroids, tol)` — at most two dense bands per axis AND nearly every mark on one of them"
  - "`_is_perimeter_ring` now requires BOTH hollowness signals: the 25% inset fill and the run structure"
  - "`_unique_top_by_count(cands, hint)` — a strictly-largest count or None, with the tie logged by candidate id"
  - "both `_library_symbol_bindings` hint branches refuse a tie instead of taking the first maximum"
  - "tests/test_phase28_symbol_position_evidence.py — 26 free checks over the real Crow plan page"
affects: [28-05, 28-06, 28-07, 25]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "a shape claim is validated by POSITION and SHAPE, never by whether the resulting number is closer to a golden figure"
    - "a predicate that can be satisfied vacuously (a sparse scatter clears a hollowness test by luck) needs a positive-evidence clause, not just an upper bound"
    - "two synthetic fixtures built to carry IDENTICAL mark counts, so no assertion in the module can be satisfied by a count"
    - "an ambiguity that list order silently resolves is a guess wearing a decision's clothes — refuse and log it"

key-files:
  created:
    - tests/test_phase28_symbol_position_evidence.py
  modified:
    - src/bobbytailor/vision/fusion.py

key-decisions:
  - "The clean 2x is a coincidence and the plan's halving instinct is refused by measurement, not by argument: all instances in ONE viewport, closest pair 48.3 ft apart against a 0.8 ft symbol, every instance 130-292 ft from the region edge."
  - "The ring test needs a positive-evidence clause. Counting dense bands only sets an UPPER bound, which a sparse scatter satisfies vacuously — so nearly every mark must also lie ON one of the runs."
  - "The run-coverage allowance is the complement of the hollowness allowance the function already makes (1 - `_PERIMETER_INNER_MAX_FILL`), not a new tuned number."
  - "The band tolerance is `_min_2d_span_pt` — the SAME marker-derived tolerance that separates a 2-D array from a collinear strip. No second, unrelated tolerance enters the predicate."
  - "The plan's 56-vs-56 tie does not exist and the unique-maximum rule was implemented anyway: it fixes a real order-dependence, it is what T-28-06 / T-28-10 ask for, and it costs nothing to hold."
  - "Bollards becoming a flagged absence IS the deliverable. The count does not approach golden in this plan and was never supposed to."

patterns-established:
  - "Falsify-before-you-fix: the hypothesis a plan exists to reject is committed as a runnable assertion BEFORE the code changes, so nobody re-derives it by spending API."
  - "Real-data positive control: the sheet's one genuinely hollow ring is asserted to still pass the predicate, so a fix cannot pass by refusing everything."
  - "Identify the subject through the producer's own filter minus the predicate under scrutiny — that keeps the subject stable across the fix."

# V4-FIX-02 reads: "The Bollards 2x (56 vs 28) is diagnosed and fixed at its cause — a
# double-count signature, never resolved by dividing by two." Diagnosed (it is not a double-count;
# it is a mis-binding), fixed at that cause (the ring test and the tie rule), and nothing was
# halved. The residual — what the real bollard count IS — is Phase 25's symbol detection by the
# ROADMAP's own non-goals. 28-07 re-asserts this requirement as a gate.
requirements-completed: [V4-FIX-02]
requirements-advanced: []

coverage:
  - id: D1
    description: "The double-count hypothesis is disproved on the real drawing, for free: one region, no coincident pairs, nothing near a boundary"
    requirement: "V4-FIX-02"
    verification:
      - kind: integration
        ref: "tests/test_phase28_symbol_position_evidence.py#test_every_instance_lands_in_exactly_one_region_and_it_is_the_same_one"
        status: pass
      - kind: integration
        ref: "tests/test_phase28_symbol_position_evidence.py#test_no_two_instances_are_close_enough_to_be_two_marks_on_one_object"
        status: pass
      - kind: integration
        ref: "tests/test_phase28_symbol_position_evidence.py#test_no_instance_lies_near_the_boundary_of_its_own_region"
        status: pass
    human_judgment: false
  - id: D2
    description: "What it positively is — a fully populated lattice whose emptiest band is fuller than a ring's interior band can be"
    requirement: "V4-FIX-02"
    verification:
      - kind: integration
        ref: "tests/test_phase28_symbol_position_evidence.py#test_every_band_the_cluster_occupies_is_as_full_as_every_other"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_symbol_position_evidence.py#test_a_hollow_ring_has_two_dense_bands_per_axis_and_a_lattice_has_more"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_symbol_position_evidence.py#test_the_ring_and_the_lattice_are_indistinguishable_by_count"
        status: pass
    human_judgment: false
  - id: D3
    description: "`_is_perimeter_ring` rejects a filled lattice and a runless scatter, still accepts a hollow ring and a jamb run, and the pre-existing 2-D gate is unweakened"
    requirement: "V4-FIX-02"
    verification:
      - kind: unit
        ref: "tests/test_phase28_symbol_position_evidence.py#test_a_hollow_ring_built_at_the_measured_pitch_is_still_a_ring"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_symbol_position_evidence.py#test_a_filled_lattice_of_the_same_pitch_and_mark_is_not_a_ring"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_symbol_position_evidence.py#test_a_run_of_jamb_pairs_along_one_wall_is_still_a_ring"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_symbol_position_evidence.py#test_a_sparse_scatter_lying_on_no_run_is_not_a_ring"
        status: pass
      - kind: integration
        ref: "tests/test_phase28_symbol_position_evidence.py#test_a_collinear_strip_is_still_rejected_and_the_two_d_gate_still_decides_it"
        status: pass
    human_judgment: false
  - id: D4
    description: "A count tie names nothing on either hint and the tie is logged by candidate id; a unique maximum still binds"
    requirement: "V4-FIX-02"
    verification:
      - kind: unit
        ref: "tests/test_phase28_symbol_position_evidence.py#test_two_perimeter_candidates_tied_on_count_bind_nothing"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_symbol_position_evidence.py#test_two_grid_candidates_tied_on_count_bind_nothing"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_symbol_position_evidence.py#test_a_refused_tie_says_which_candidates_tied"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_symbol_position_evidence.py#test_an_unambiguous_larger_candidate_still_wins"
        status: pass
    human_judgment: false
  - id: D5
    description: "The real outcome: nothing on the plan page earns the perimeter name, and the predicate has not simply stopped discriminating"
    requirement: "V4-FIX-02"
    verification:
      - kind: integration
        ref: "tests/test_phase28_symbol_position_evidence.py#test_no_small_marker_cluster_on_the_plan_page_reads_as_a_perimeter_ring"
        status: pass
      - kind: integration
        ref: "tests/test_phase28_symbol_position_evidence.py#test_the_ring_test_still_finds_the_one_genuinely_hollow_ring_on_the_page"
        status: pass
      - kind: integration
        ref: "tests/test_phase28_symbol_position_evidence.py#test_the_real_plan_page_emits_no_perimeter_binding"
        status: pass
    human_judgment: false
  - id: D6
    description: "No threshold is derived from any golden quantity and the module can never reach a paid service"
    requirement: "V4-FIX-02"
    verification:
      - kind: unit
        ref: "tests/test_phase28_symbol_position_evidence.py#test_this_module_names_no_published_quantity_and_calls_no_paid_service"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_symbol_position_evidence.py#test_this_module_imports_nothing_that_could_reach_a_network"
        status: pass
    human_judgment: false
  - id: D7
    description: "An estimator reading the Bollards row as a flagged ABSENCE OF A NAME (rather than as a missing object) acts on it correctly"
    verification: []
    human_judgment: true
    rationale: "How the refused binding reads on a client report cannot be seen without a paid run, which is a human spend decision. `score_report_dir.py` re-scores frozen artifacts and returns the same numbers whatever this code does."

# Metrics
duration: 190min
completed: 2026-08-06
status: complete
---

# Phase 28 Plan 02: The Bollards Binding Summary

**The clean 2x was never a double-count: free position evidence over the real Crow plan page shows all instances in one viewport, no two within 48 ft of each other against a 0.8 ft symbol, and every one of them 130-292 ft from the nearest region edge — so the defect was a mis-binding, and `perimeter_jamb_symbol` now refuses to name a fully populated 14x4 lattice, refuses a count tie on either hint, and names nothing at all on that sheet.**

## Performance

- **Duration:** 190 min (64 min of it the full offline suite, run once at plan end)
- **Started:** 2026-08-06T18:56:00Z
- **Completed:** 2026-08-06T22:06:00Z
- **Tasks:** 3 (task 1 test-only; tasks 2 and 3 TDD)
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments

- **The doubling hypothesis is disproved by a committed, runnable, free assertion.** Not by argument — by `cluster_symbols` over `tests/fixtures/crow_cass/crow_cass_plans.pdf` page 0 in 1.3 s. Every instance of the judged cluster resolves to exactly one segmented viewport and it is the same one for all of them (a plan-plus-detail double-marking would split); the closest two are 87 pt apart against a 1.56 pt symbol, 55 symbol widths (a second mark on an already-marked object sits *on* it); and the nearest instance to its region's boundary is 0.203 of the region's short side away (a perimeter object hugs the boundary). Three independent falsifications, each computed at runtime.
- **What it positively is, asserted band by band.** Its 14 columns each hold 4 marks and its 4 rows each hold 14 — its emptiest band is twice as full as a hollow ring's interior band can be, since a ring's interior band holds one mark per side. Row occupancies `[14, 14, 14, 14]`, not `[14, 2, 2, 14]`.
- **`_is_perimeter_ring` now needs two independent hollowness signals.** The 25%-inset fill asks whether marks avoid the middle of the cluster's own bbox; on a lattice a few rows deep, almost every mark falls outside a 25% inset, so a filled 14x4 array reads as hollow — this is asserted as a live measurement in the suite, so the reason the old test was fooled is recorded rather than remembered. The new run-structure test asks whether the marks are *arranged* as a ring's sides: at most two dense bands per axis, and nearly every mark on one of them.
- **The predicate is proved on shapes and on real geometry, in both directions.** A hollow ring and a run of jamb pairs — both built from the real cluster's own measured pitch and mark size — are still accepted; a filled lattice of that same pitch is not. And the sheet's *one genuinely hollow ring* (`SYM-3`, dense bands (2, 2), row occupancies `[21, 2x7, 21]`) is asserted to still pass, kept away from the marker hint by the pre-existing size filter rather than by the ring test — so the fix cannot have passed by refusing everything.
- **A tie is refused on both hints and logged.** `max(cands, key=count)` returns the FIRST maximum, so two surviving clusters with the same count were separated by whichever the clusterer happened to emit first. `_unique_top_by_count` requires a strictly largest count and logs the tied candidate ids at info level, because a silent `None` is indistinguishable from having had no candidates at all. `structural_grid_symbol` gets the same rule, so the Columns hint cannot inherit the defect being fixed on the Bollards hint (T-28-10).
- **The stated outcome, out loud: Crow's Bollards row does NOT get closer to golden.** With the ring test honest, no small-marker cluster on that page reads as a ring, so the hint names nothing. The cluster keeps its raw candidate id, `_fuse_symbol_groups` falls through the naming ladder and routes it to the unnamed-geometry ledger with its count, its position and its reason. The object reaches the report as the absence of a NAME, not the absence of an object. Removing a wrong name was the whole deliverable; finding the real bollards is Phase 25's symbol detection.
- **Nothing was divided by two, and no threshold is derived from any golden quantity.** Every constant states a fact about a shape: a ring's interior band holds one mark per side; a ring has two sides per axis; the fraction allowed off the runs is the one the hollowness test already allows off the boundary (`1 - _PERIMETER_INNER_MAX_FILL`). The test module's two synthetic fixtures are built to carry *identical* mark counts so that no assertion in it can be satisfied by a count, and it self-audits for golden and paid-service tokens.
- **Full offline suite: 2234 passed, 1 skipped, 2 deselected** in 1:04:20 (baseline 2208/1/2; +26 = exactly the new module). `test_phase23_acceptance.py`, `test_phase24_acceptance.py`, `test_four_set_coverage.py` and the 24-09 determinism harness are all inside that run and all green; the latter two were also run standalone mid-plan (291 passed with `test_fusion.py`, `test_symbol_identification.py`, `test_naming_conventions.py`).

## Task Commits

1. **Task 1: Commit the falsification before touching the binder** — `00c71c6` (test)
2. **Task 2: A ring is hollow along BOTH axes** — `2671b17` (test, RED) → `8849759` (feat, GREEN)
3. **Task 3: A tie is not a decision** — `01f0c42` (test, RED) → `cf6c498` (feat, GREEN)

No REFACTOR commit was needed on either TDD task; both GREEN implementations were already at their final shape.

## Files Created/Modified

- `src/bobbytailor/vision/fusion.py` — three new module constants beside `_PERIMETER_INNER_MAX_FILL` (`_PERIMETER_RING_BAND_MAX`, `_PERIMETER_MAX_DENSE_BANDS`, `_PERIMETER_MIN_RUN_COVERAGE`), each with a one-line comment stating the geometric fact it encodes; `_occupancy_bands()` and `_is_built_from_ring_runs()`; `_is_perimeter_ring` extended (the inset check kept, now one of two conditions that must both hold) with a docstring saying what it discriminates and why the inset alone was not enough; `_unique_top_by_count()`; both hint branches of `_library_symbol_bindings` routed through it, with the docstring stating the downstream consequence of emitting nothing.
- `tests/test_phase28_symbol_position_evidence.py` — **new.** 26 checks in five groups: identifying the judged cluster through the producer's own filter, the three position falsifications, the lattice-vs-ring discrimination on real and synthetic geometry, the tie refusal on both hints, and the module's own contract (free, offline, golden-free).

## Decisions Made

- **The subject is identified by the binder's own filter MINUS the predicate under scrutiny.** `_hint_shortlist` applies count, uniformity, small-marker and 2-D spread but not `_is_perimeter_ring`, and then requires a unique maximum. That is what keeps the same cluster under the microscope before and after the fix — a shortlist including the ring test would have found nothing after task 2, and the position evidence would have silently stopped describing anything.
- **The band tolerance is reused, not invented.** `_min_2d_span_pt(group)` — the marker-size-derived threshold that already separates a 2-D array from a collinear strip — groups the bands. The test module deliberately uses a *different*, self-evident tolerance (half the cluster's own closest approach), so the oracle is not a copy of the implementation.
- **A hollow-ring test needs positive evidence, not only an upper bound.** See deviation 2: dense-band counting alone is satisfied vacuously by a scatter whose bands are all too thin to be dense.
- **The 25%-inset check was kept.** It is a real second signal and dropping it would trade one incomplete test for another. Both conditions must hold.
- **`V4-FIX-02` is marked complete.** Its operative verbs are *diagnosed* and *fixed at its cause*, with an explicit prohibition on dividing by two. All three are delivered. What the real bollard count is remains open and is Phase 25's by the ROADMAP's own non-goals.

## Deviations from Plan

### Plan premise falsified by the evidence

**1. The 56-vs-56 count tie the plan blames does not exist**

- **Found during:** Task 1 (before any code changed)
- **Plan claimed:** "`_library_symbol_bindings` ... then takes `max(..., key=count)`. Two clusters tie at 56 on Crow page 0, so the tie-break is list order — the wrong one won." And: "`_is_small_marker` ... is what excludes the OTHER 56-cluster (11.13 x 5.87 ft) once the ring test is honest."
- **Measured:** `SYM-3` (11.13 x 5.87 ft) is excluded by `_is_small_marker` **already, today, before any change** — it never enters the candidate list, so there is no tie to break. The surviving perimeter candidates on page 0 are `SYM-2` (56) and `SYM-22` (8), and `max` picks `SYM-2` by a unique maximum. **List order never decided anything on this sheet.** The sole cause of the mis-binding is `_is_perimeter_ring`.
- **What was done:** Task 3 was implemented anyway, and the reason is stated rather than implied — `max` genuinely does break a tie by list order, that is genuinely a guess, and T-28-06 / T-28-10 ask for exactly this on both hints. But its commit and this summary both stop short of claiming it fixed Crow's Bollards row. Task 2 did that alone.
- **Impact:** none on the code. It narrows what 28-07 can honestly assert: the tie rule is a hardening, not a demonstrated Crow fix, and no committed test claims otherwise.

### Auto-fixed Issues

**2. [Rule 2 - Missing Critical] The plan's fix alone would have swapped one wrong name for another**

- **Found during:** Task 2
- **Issue:** The plan's occupancy test sets only an UPPER bound — "a ring has at most two dense bands per axis". Measured on the real page, `SYM-22` (8 marks, 1.13 x 1.0 ft, sitting inside detail viewport `R4`) has dense bands (1, 0): it satisfies that upper bound *vacuously*, because its bands are all too thin to be dense at all. With `SYM-2` rejected, `SYM-22` becomes the top surviving candidate and `perimeter_jamb_symbol` would have named it — publishing a different fabricated count off eight scattered marks in a detail blow-up. That directly contradicts the plan's own success criterion ("the affected object reaches the report as a flagged absence of a name"). The root cause is that a 25% inset box covers a quarter of the area, so a sparse scatter clears the hollowness test by luck (`SYM-22`: 1 of 8 inside, 0.125).
- **Fix:** added the positive-evidence half. A ring is *built from its runs*, so nearly every mark must lie in a dense band — `_PERIMETER_MIN_RUN_COVERAGE`, defined as `1.0 - _PERIMETER_INNER_MAX_FILL`, the same allowance the hollowness test already makes for marks off the boundary. `SYM-2` and the synthetic ring and jamb fixtures all score 1.00; `SYM-22` scores 0.50 and is refused. The clause also subsumes "at least one run exists": a cluster with no dense band at all scores 0.
- **Files modified:** `src/bobbytailor/vision/fusion.py`
- **Verification:** `test_a_sparse_scatter_lying_on_no_run_is_not_a_ring` (synthetic, nine marks in general position), plus `test_no_small_marker_cluster_on_the_plan_page_reads_as_a_perimeter_ring` which fails without it.
- **Committed in:** `8849759` (Task 2 GREEN)

**3. [Rule 1 - Bug] One of my own assertions was too strong for the data**

- **Found during:** Task 2 (GREEN)
- **Issue:** `test_the_ring_test_still_finds_the_one_genuinely_hollow_ring_on_the_page` asserted that every cluster still accepted as a ring is *too large to be a marker*. False: `SYM-12` (0.0 x 2.07 ft) IS a small marker and is kept out of the binder by `_size_uniform`, not by size.
- **Fix:** the assertion now states the true, checkable claim — every surviving ring is excluded from the marker hint by a **pre-existing** filter (size **or** uniformity), never by the ring test — and the failure message names which filter caught each one.
- **Files modified:** `tests/test_phase28_symbol_position_evidence.py`
- **Committed in:** `8849759` (Task 2 GREEN)

**4. [Rule 1 - Bug] The module's self-audit grep found itself**

- **Found during:** Task 1
- **Issue:** the "makes no network call" check scanned its own source for networking library names and matched the line performing the scan — the same trap 28-01, 24-09 and 24-10 each hit.
- **Fix:** rewritten as an `ast` walk over the module's own import statements, asserting every imported top-level module is in an offline allow-list. Strictly stronger than a substring scan and structurally immune to finding itself. The golden-token half keeps the 28-01 idiom of assembling each token from halves.
- **Files modified:** `tests/test_phase28_symbol_position_evidence.py`
- **Committed in:** `00c71c6` (Task 1)

---

**Total deviations:** 1 plan premise falsified + 3 auto-fixed (1 missing critical, 2 bugs).
**Impact on plan:** deviation 2 was required for the plan's own success criterion to hold on real data — without it the fix produced a new unevidenced name rather than an honest absence. No scope creep: the added clause lives inside the same predicate, reuses the same tolerance, and derives its threshold from a constant already in the file.

## Non-vacuity Evidence

- Task 2's RED run failed exactly 5 checks and Task 3's failed exactly 3 — in each case the ones the implementation then turned green, with the "still binds" and "larger count still wins" checks passing in both directions.
- Three constants in the position-evidence module were each mutated (`_DOUBLE_MARK_WIDTHS` 5 → 500, `_EDGE_HUG_FRACTION` 0.05 → 0.5, `_RING_INTERIOR_BAND` 2 → 200); each mutation makes the module fail. The original file was restored and re-run green before commit.
- The two synthetic shapes the module builds carry identical mark counts by construction, asserted directly, so no check in the module can be satisfied by a count alone.

## Issues Encountered

- **The full offline suite outran the tool's timeout twice.** The first attempt was killed by the harness mid-run after ~55 minutes. It was re-launched orphaned (`nohup ... &` in a subshell — `setsid` does not exist on this macOS) writing to a log, and polled in the foreground until the process exited: 1:04:20 wall, `2234 passed, 1 skipped, 2 deselected`.
- **The plan's `measured_facts` viewport labels differ slightly from the segmenter's.** `R1` (`OVERALL FLOOR PLAN / SCALE: 1" = 40'-0"`) is typed `unknown`, not `main_plan`, and page 0 has six regions, not five (`R6` is an unnamed 1 1/2"=1'-0" detail). Neither changes any conclusion — every assertion resolves regions at runtime and refers to them by id.
- **`.planning/paid-run-evidence/` verified untouched** — `git status --porcelain` over that path returned `0` before every commit and after the last one (T-28-02).

## Risk Warning (CLAUDE.md gitnexus mandate)

The index was re-analysed first (it was stale at `14d4ec0`; now current). `gitnexus impact _library_symbol_bindings --direction upstream` returned **risk: HIGH** — 3 impacted symbols, 3 affected processes, 2 modules (`fuse_sheet` → `_run_sheet_vector` → `_route_deterministic`). `_is_perimeter_ring` returned **LOW** (3 impacted, 2 processes). The HIGH-risk change was made anyway because it *is* the plan's purpose, and it was made minimally: the selection expression changed, every filter ahead of it is untouched, and no other behaviour in `_library_symbol_bindings` moved. The full offline suite at 2234/1/2 with zero regressions is the evidence the blast radius was not disturbed.

## Threat Flags

None. No new network endpoint, auth path, file access pattern or trust-boundary schema change. T-28-06, T-28-07, T-28-08 and T-28-10 are mitigated as planned (a hint may only name a cluster whose layout matches what it asserts; every occupancy threshold is a stated geometric fact; a refusal is logged with candidate ids and the cluster still reaches the ledger; the grid hint carries the same unique-maximum rule). T-28-09 was accepted as planned — the O(n²) closest-pair loop over 56 instances runs in microseconds. T-28-SC is trivially met: this plan installed no package.

## Known Stubs

None.

## User Setup Required

None — no external service configuration, no package installed, no paid API touched.

## Next Phase Readiness

- **28-07 must not claim the tie rule fixed Crow.** Deviation 1 falsified that premise: there was no tie on that sheet. The honest phase-gate claim is "a filled lattice can no longer be named a perimeter object, on this drawing, asserted by position" plus "a tied binding is refused on both hints, asserted on synthetic candidates".
- **Phase 25 inherits an honest gap, with evidence attached.** The bollard-scale cluster on Crow page 0 is now unnamed rather than misnamed, and its measured properties are committed: 56 instances at 0.80 x 0.87 ft on a 14x4 lattice, 97.2 pt column pitch, 87 pt minimum spacing, all in `R1`. Whatever detector Phase 25 builds can be judged against that geometry instead of against a count.
- **No accuracy figure was produced and none can be.** `score_report_dir.py` re-scores frozen artifacts and returns the same numbers whatever this code does. A post-fix Crow number requires a paid run — a human spend decision, not this phase's output. The naive metric is *expected* to move against this change, since a coincidental name was removed.
- **28-05 should note the new refusal path.** A cluster whose hint was refused now reaches `_fuse_symbol_groups` with no `library_bindings` entry, so it flows to the unnamed-geometry ledger — relevant to how `region_ref` is threaded for a row that has a region but no name.

## Self-Check: PASSED

Both claimed files exist on disk; all five claimed commit hashes resolve in `git log`.
`git status --porcelain .planning/paid-run-evidence/` returns `0` — the frozen evidence tree is
byte-unchanged (T-28-02). `grep -c 'ANTHROPIC' tests/test_phase28_symbol_position_evidence.py`
returns `0`.

---
*Phase: 28-accuracy-remediation-crow-defects*
*Completed: 2026-08-06*

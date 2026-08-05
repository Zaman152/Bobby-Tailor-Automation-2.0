---
phase: 24-binding-determinism-text-anchored-labeling
plan: 02
subsystem: vision-fusion
tags: [precedence, determinism, wall-classes, audit-trail, fusion_rejected, pytest]

# Dependency graph
requires:
  - phase: 23-measurement-engine-completion
    provides: "C3a withdraw-on-reinstate semantics layered on fusion_rejected, and the _fuse_rooms label_override_blocked record shape this plan mirrors"
provides:
  - "_fuse_wall_classes precedence inversion — a printed-thickness match outranks a vision label unconditionally"
  - "_squash_wall_name — a case/separator agreement check that is deliberately NOT a name canonicaliser"
  - "name_source values that distinguish the three naming authorities (vision / naming_library / naming_library_thickness)"
  - "map_wall_classes_from_library 4th return field — the printed thickness that decided a confident bind"
  - "fusion_rejected records with reason wall_class_thickness_bind_outranks_label, carrying both answers plus the thickness evidence"
  - "tests/test_fusion.py::test_wall_class_label_invariance — the free V4-DET-02 half of the phase determinism harness"
affects: [24-03 canonical naming, 24-04 unnamed-geometry ledger, 24-05 vocabulary persistence, 24-10 phase gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deterministic-leads precedence: printed evidence names the row, a stochastic reading may corroborate or dissent but never rename"
    - "Published dissent: the losing answer reaches the report with the evidence that beat it attached, never a silent drop"
    - "Own-key audit records: a precedence override carries a reason key distinct from every suppression key, so suppression-keyed logic cannot act on it"
    - "Differential determinism testing: hold geometry and library fixed, vary only the model's answer, require the emitted triple SET not to move"

key-files:
  created: []
  modified:
    - src/bobbytailor/vision/fusion.py
    - tests/test_fusion.py
    - .planning/phases/24-binding-determinism-text-anchored-labeling/deferred-items.md

key-decisions:
  - "name_source keeps its two existing strings meaning exactly what they meant and adds a third (naming_library_thickness) rather than renaming the old cases — and the new value is registered in _NAME_AUTHORITY at rank 2, the SAME rank as naming_library, so the inversion cannot silently re-order region-sharing arbitration"
  - "The agreement check is a case/separator squash and nothing more. Plural folding and synonym folding are 24-03's canonical_library_name to own; a second folding rule in fusion is how the two drift apart"
  - "A confident=True thickness bind that DISAGREES with a vision label flags the row. Two naming authorities disagreeing about a material classification is exactly what flag-don't-guess exists for; the deterministic name still publishes, so nothing is guessed"
  - "The precedence record carries its own reason key (wall_class_thickness_bind_outranks_label). C3a's reinstatement pass acts on suppression records, and reusing superseded_by_room_fill would make it try to un-reject a row that was never suppressed"
  - "The invariance differential asserts a SET across two variants, never a golden wall area — a golden total here would convert a determinism check into an accuracy check"
  - "The unmatched wall class is asserted as a stated residual rather than silently excluded from the comparison, so the scope of the invariance claim stays honest"

requirements-completed: []
# HONEST SCOPE NOTE: this plan delivers the DECISION half of V4-DET-02. The wall bind is now
# invariant GIVEN its object list. It is not invariant end to end, because
# map_wall_classes_from_library's `wall_objects` argument comes from
# _wall_objects_from_vocabulary(vocabulary) and that vocabulary is re-derived from the API on
# every run (24-RESEARCH defect F3). 24-03 folds the name form and 24-05 stabilises the object
# list; all three are required before V4-DET-02 holds end to end. The phase gate (24-10) verifies
# the whole requirement. REQUIREMENTS.md was deliberately NOT ticked here.

coverage:
  - id: P1
    description: "A printed-thickness match outranks a contradicting vision label, unconditionally"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_fusion.py#test_thickness_outranks_vision"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_a_thickness_bind_is_no_longer_reachable_only_through_an_elif"
        status: pass
    human_judgment: false
  - id: P2
    description: "A vision label may corroborate a deterministic bind (raising confidence, clearing review) but never override it"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_fusion.py#test_an_agreeing_vision_label_corroborates_the_thickness_bind"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_the_agreement_check_is_a_squash_and_not_a_fuzzy_matcher"
        status: pass
    human_judgment: false
  - id: P3
    description: "A hint bind does not override a reading, but the disagreement flags the row; a hint bind names the class when vision is silent; neither reaches the unlabeled branch unchanged"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_fusion.py#test_a_hint_bind_does_not_override_a_vision_label_but_flags_the_row"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_a_hint_bind_names_the_class_when_vision_is_silent_and_stays_flagged"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_no_bind_and_no_label_still_reaches_the_unlabeled_branch"
        status: pass
    human_judgment: false
  - id: P4
    description: "A CMU/masonry object still cannot bind the dominant-LF perimeter class AFTER the inversion (T-24-08)"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_fusion.py#test_masonry_never_dominant"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_masonry_never_dominant_when_it_is_the_only_class"
        status: pass
    human_judgment: false
  - id: P5
    description: "Every precedence override appends one fusion_rejected record carrying both answers and the thickness evidence; agreement and silence append nothing (T-24-06)"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_fusion.py#test_wall_label_disagreement_audited"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_agreement_and_silence_append_nothing_to_the_audit_trail"
        status: pass
      - kind: integration
        ref: "tests/test_fusion.py#test_the_precedence_record_reaches_the_sheet_audit_list_through_fuse_sheet"
        status: pass
      - kind: integration
        ref: "python3 -m pytest tests/test_reporter_accuracy.py -x -q (green — the report aggregation reads the record unchanged)"
        status: pass
    human_judgment: false
  - id: P6
    description: "The precedence record does not reuse a C3a suppression reason key (T-24-07)"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_fusion.py#test_the_precedence_record_does_not_reuse_a_c3a_suppression_key"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_the_precedence_record_uses_the_fuse_rooms_field_names"
        status: pass
    human_judgment: false
  - id: P7
    description: "Two schema-legal label variants over one fixed geometry bundle emit an identical (name, quantity, unit) triple SET"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_fusion.py#test_wall_class_label_invariance"
        status: pass
      - kind: other
        ref: "mutation check — reverting the precedence to `bind_confident and not has_label` makes the differential FAIL (CMU Wall 2,196 SF vs 106,992 SF across the two variants)"
        status: pass
    human_judgment: false
  - id: P8
    description: "The differential SKIPS rather than passes when its evidence is absent, and its premise (the two saved runs really disagreed) is itself asserted"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_fusion.py#test_the_invariance_fixture_skips_rather_than_passes_without_its_evidence"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_the_two_recorded_runs_really_did_differ_in_the_naming_layer"
        status: pass
    human_judgment: false

# Metrics
duration: 3h 45m
completed: 2026-08-05
status: complete
---

# Phase 24 Plan 02: Wall-Class Precedence Inversion Summary

**The drawing's own printed thickness now names a wall class and a stochastic reading may only agree with it, so the same geometry can no longer publish as CMU on one run and tilt-up on the next — and every reading that lost reaches the report with the evidence that beat it attached.**

## Performance

- **Duration:** 3h 45m (three full 47-min suites, one per commit, dominate it)
- **Started:** 2026-08-05
- **Completed:** 2026-08-05
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- **The inversion itself.** `map_wall_classes_from_library` was already a complete zero-API classifier — printed-thickness match within `_WALL_THICKNESS_TOL_IN = 1.5`, plus the guard forbidding a masonry object from binding the dominant-LF perimeter class. It sat in an `elif` **behind** the vision label. The rule V4-DET-02 asks for was already written and merely demoted; this plan promoted it. No new classification logic was invented.
- **The dissent is published.** `_fuse_wall_classes` now takes the sheet's existing `rejected` list and appends one record per override carrying both answers plus the printed and measured thicknesses. Nothing is dropped so that the trail can look tidy.
- **The flip is mutation-checked, not asserted on faith.** Reverting the precedence to the pre-24-02 order makes `test_wall_class_label_invariance` fail, publishing `CMU Wall` at **2,196 SF** in variant A and **106,992 SF** in variant B — the same shape as the documented 8 ↔ 11,294 SF flip. The test catches the real defect.
- **A vacuous test was caught before it shipped.** The skip-proof guard initially reported as *skipped* itself, because `pytest.skip` raises `Skipped`, which derives from `BaseException`, not `Exception` — so `pytest.raises(Exception)` let it escape and the guard earned a green tick for having checked nothing.

## Task Commits

Each task was committed atomically:

1. **Task 1: Invert the precedence — deterministic evidence becomes primary** — `a56d877` (feat)
2. **Task 2: Audit the vision/deterministic disagreement instead of discarding it** — `236e295` (feat)
3. **Task 3: The wall-label invariance differential** — `7e3c278` (test)

## Files Created/Modified

- `src/bobbytailor/vision/fusion.py`
  - `_NAME_SOURCE_VISION` / `_NAME_SOURCE_LIBRARY` / `_NAME_SOURCE_WALL_THICKNESS` — the three naming authorities, with the first two keeping their exact prior strings and meanings.
  - `_squash_wall_name` + `_WALL_NAME_SQUASH_RE` — the agreement check.
  - `_NAME_AUTHORITY` gains `naming_library_thickness` at rank 2.
  - `map_wall_classes_from_library` returns a 4-tuple; the 4th field is the printed thickness that decided a confident bind (`None` for a hint bind).
  - `_fuse_wall_classes` — the five-step precedence block replacing the old two-branch `if/elif`, plus a `rejected` parameter, plus `name_source` and the dissent review reason threaded into both emit branches.
  - `_WALL_LABEL_PRECEDENCE_REASON` + `_reject_wall_label_override` — the audit record.
  - `fuse_sheet` passes the sheet's `rejected` list into `_fuse_wall_classes`.
- `tests/test_fusion.py` — **20 new tests** in one documented 24-02 section.
- `.planning/phases/.../deferred-items.md` — one out-of-scope finding, logged and not fixed.

## The precedence, top to bottom

| # | Condition | Name comes from | `name_source` | Flagged? |
|---|---|---|---|---|
| 1 | confident thickness bind, no label | thickness bind | `naming_library_thickness` | no |
| 2a | confident bind + AGREEING label | thickness bind | `naming_library_thickness` | no — confidence raised, review reason cleared |
| 2b | confident bind + DISSENTING label | thickness bind | `naming_library_thickness` | **yes** — both answers named on the row, one record in `fusion_rejected` |
| 3 | no confident bind + label | vision label | `vision` | only when a hint bind disagreed |
| 4 | hint bind, vision silent | hint bind | `naming_library` | yes (unchanged) |
| 5 | neither | candidate id | *(absent)* | yes — 24-04 owns this branch |

## Decisions Made

- **`name_source` is extended, not rewritten.** `vision` and `naming_library` keep their exact prior strings and meanings; `naming_library_thickness` splits out the case that used to hide inside `naming_library`. Critically, the new value is registered in `_NAME_AUTHORITY` **at rank 2 — the same rank as `naming_library`**. Omitting it would have dropped a thickness-bound wall row to the unknown-source default of 4, *below* `learned`, silently re-ordering `_share_rank`'s region-sharing arbitration. A precedence inversion that quietly demotes its own winner in a neighbouring arbitration would be worse than the defect.
- **The agreement check is a squash and nothing more.** It answers "did these two authorities say the same thing?", never "which library object is this?". It deliberately does **not** fold `Metal Downspout`/`Metal Downspouts` or `Aluminum Storefront`/`Aluminum Storefront/Curtain Wall` — that is 24-03's `canonical_library_name` to own, and a second folding rule living in fusion is precisely how the two drift apart. A test pins the non-folding.
- **A disagreement flags the row.** The deterministic name still publishes (nothing is guessed), but two naming authorities disagreeing about a material classification is exactly the case flag-don't-guess exists for, and the plan's own behaviour bullet already required flagging for the *weaker* hint-bind disagreement — a strong disagreement must flag too, or the flagging rule is backwards.
- **The precedence record carries its own reason key.** C3a's `_reinstate_orphaned_supersessions` acts on suppression records; reusing `superseded_by_room_fill` would make it try to un-reject a row that was never suppressed. Asserted directly rather than left to the suite.
- **The audit list is optional.** Omitting it is behaviourally identical minus the record, so the audit can never become a correctness dependency — a trail the code needs is a trail nobody dares change.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Missing Critical] The new `name_source` value had to be registered in `_NAME_AUTHORITY`**

- **Found during:** Task 1, reading `_share_rank` before changing the emitted `name_source`.
- **Issue:** The plan asks for a `name_source` that distinguishes a thickness bind from a hint bind from a vision label. `_share_rank` looks `name_source` up in `_NAME_AUTHORITY` to decide which component **anchors a shared measured region**, defaulting an unknown source to rank 4 — below `learned` (3). Emitting a new string without registering it would have made every thickness-bound wall row the *least* authoritative claimant on a shared region: the exact opposite of what the inversion means, in a code path the plan never mentions.
- **Fix:** `naming_library_thickness` registered at rank **2**, identical to `naming_library`, so arbitration ordering is provably unchanged while the artifact still distinguishes the authorities.
- **Files modified:** `src/bobbytailor/vision/fusion.py`
- **Verification:** full suite unchanged at zero regressions across the commit; `_share_rank`'s behaviour is exercised by the one-area-one-item arbitration tests.
- **Committed in:** `a56d877`

**2. [Rule 2 — Missing Critical] A dissenting vision label flags the row**

- **Found during:** Task 1, reconciling the plan's behaviour bullets.
- **Issue:** The plan's bullet 3 requires a row to be flagged when a *hint* bind disagrees with a vision label. It is silent on the stronger case — a *thickness* bind disagreeing — which would have left the more serious disagreement unflagged while the weaker one was flagged.
- **Fix:** both disagreements set `needs_review` and name **both** answers in `review_reason`. The name never moves; only the flag is added.
- **Files modified:** `src/bobbytailor/vision/fusion.py`
- **Verification:** `test_thickness_outranks_vision`, `test_a_hint_bind_does_not_override_a_vision_label_but_flags_the_row`
- **Committed in:** `a56d877`

**3. [Rule 1 — Bug] The skip-proof guard passed for having checked nothing**

- **Found during:** Task 3, first run of the new tests.
- **Issue:** `test_the_invariance_fixture_skips_rather_than_passes_without_its_evidence` used `pytest.raises(Exception)`. `pytest.skip` raises `Skipped`, which derives from `BaseException`, **not** `Exception` — so the skip escaped the context manager and the guard itself reported as `skipped`. A green run containing a test that verified nothing, which is the precise anti-pattern `test_phase23_acceptance.py` rule 3 forbids and the same class of mistake 24-01 caught in its own masking test.
- **Fix:** `pytest.raises(pytest.skip.Exception)`, with the reason recorded in-file.
- **Files modified:** `tests/test_fusion.py`
- **Verification:** the guard now reports **PASSED**, confirmed under `-v`.
- **Committed in:** `7e3c278`

**4. [Rule 1 — Bug] The monkeypatch landed on the wrong module object**

- **Found during:** Task 3, same test.
- **Issue:** `monkeypatch.setattr("tests.test_fusion._PAID_RUN_EVIDENCE", ...)` did not take — this file is imported under more than one module name across the suite, so the patch landed on a different module object and the differential ran against the **real** evidence directory, reporting `DID NOT RAISE`.
- **Fix:** patched through `test_wall_class_label_invariance.__globals__`, which is the dict the function actually resolves against, with the reasoning recorded in-file.
- **Files modified:** `tests/test_fusion.py`
- **Committed in:** `7e3c278`

**5. [Process] Test-helper thicknesses are read back off the bundle, not restated**

- **Found during:** Task 3.
- **Issue:** `_emit_wall_classes` fed `map_wall_classes_from_library` a restated `_PRECEDENCE_THICKNESS_IN` constant. A fixture could then claim a thickness its own geometry does not measure, and the invariance test's third class had no entry in it at all.
- **Fix:** the helper now calls `_wall_thickness_in_by_class(bundle)` — the same function production uses. The two are numerically identical for the existing fixtures by construction (`fpp = 1.0`, `thickness_pt = inches / 12`), so no Task 1 assertion changed.
- **Files modified:** `tests/test_fusion.py`
- **Committed in:** `7e3c278`

### Deferred, NOT fixed (logged in `deferred-items.md`)

**`_min_confidence(x, None)` collapses every deterministically-named wall row to `low`.** `_fuse_wall_classes` passes `vision_conf=None` when no vision label exists, and `_min_confidence` ranks an absent value as `low` — so a *confident printed-thickness bind*, the most authoritative naming evidence the system has, publishes with `confidence: "low"`. This is **pre-existing** (the pre-24-02 `elif` branch passed the same `None`), it is outside this plan's fence ("a precedence change, not a rewrite of the emitter"), and fixing it would change the confidence of every library-bound wall row. It is pinned honestly rather than hidden: `test_an_agreeing_vision_label_corroborates_the_thickness_bind` asserts the corroboration **raise by rank** instead of pinning two strings, so the day this is fixed the test still passes and still means what it says. Suggested owner: 24-04 or the 24-10 gate.

---

**Total deviations:** 5 (2 missing-critical, 2 bugs, 1 process) + 1 deferred
**Impact on plan:** every deviation strengthens a stated invariant of the plan itself — arbitration ordering unchanged by the inversion, disagreements flagged consistently, no test passing for having looked at nothing. No scope creep, no new package, no new public surface beyond the precedence block and its audit record.

## Residual non-determinism — named, not hidden

This plan makes the wall bind invariant **given its object list**. It cannot make it invariant end to end. `map_wall_classes_from_library`'s `wall_objects` argument comes from `_wall_objects_from_vocabulary(vocabulary)` (`fusion.py:1361`) and that vocabulary is re-derived from the API on every run — 24-RESEARCH defect **F3**, visible directly in the saved evidence:

| Run | Storefront object | Downspout object | Retaining wall unit |
|---|---|---|---|
| 14:19 | `Aluminum Storefront` | `Metal Downspout` | LF |
| 18:13 | `Aluminum Storefront/Curtain Wall` | `Metal Downspouts` | SF |

**24-03** folds the name form (`canonical_library_name`) and **24-05** stabilises the object list. All three are required before V4-DET-02 holds end to end, which is why `REQUIREMENTS.md` was deliberately not ticked here. `test_wall_class_label_invariance` asserts this residual explicitly — its third wall class has no thickness match, so vision still names it and its triple **does** vary between the two variants. Asserting the residual is what keeps the invariance claim above honest rather than quietly scoped to whatever happened to pass.

**Also explicitly out of scope, per the plan:** the 8 ↔ 11,294 SF wall-area *values*. Those are measurement outcomes. Phase 24 owns which class is called CMU, not what CMU measures.

## Measurements taken this plan (all FREE, zero API)

**Mutation check** — the differential against the pre-24-02 precedence:

| Variant | Under the inversion | Under the old `elif` order |
|---|---|---|
| A (14:19 names) | `CMU Wall` 2,196 SF · `Tilt Up Wall` 106,992 SF | `CMU Wall` **2,196 SF** |
| B (18:13 names, assignment flipped) | identical set | `CMU Wall` **106,992 SF** |

A 49× swing on identical geometry, caused only by the model's answer changing. That is the defect, reproduced on demand and then closed.

**Free fusion probe, Crow page 0** (`scripts/fusion_probe.py … --json`, exit 0) still reports the wall classes it did before, with thickness data intact: TC1 8.8" / 1714 LF, TC2 9.6" / 1113.5 LF, TC3 11.2" / 778 LF, TC4 4.8" / 415.1 LF, TC5 8.0" / 313.5 LF, TC6 3.2" / 105.5 LF.

## GitNexus (CLAUDE.md, mandatory)

- **Before editing `_fuse_wall_classes`:** `impact(_fuse_wall_classes, direction=upstream)` → **risk HIGH**, 3 impacted, 1 direct caller (`fuse_sheet`), 3 affected processes (`_run_sheet_vector`, `fuse_sheet`, `run_sheet`), 2 modules (Vision direct, Pipeline indirect). **⚠️ HIGH risk warned before a line was changed**, as the plan requires. Empirically the blast radius held: the full suite moved only by the count of tests added, at every one of the three commits.
- **`detect_changes()` before each commit:** run before all three — risk **low**, **0** affected processes each time.
- The index remains stale (`c4f6e7d` vs HEAD). Re-running `npx gitnexus analyze` is left to the phase orchestrator, since re-indexing mid-plan would invalidate the impact reading quoted above.

## Test Results

| Gate | Result |
|---|---|
| Baseline (plan entry, post-24-01) | 1972 passed, 1 skipped, 2 deselected |
| Full suite before `a56d877` | **1983 passed**, 1 skipped, 2 deselected (46:58) |
| Full suite before `236e295` | **1989 passed**, 1 skipped, 2 deselected (47:43) |
| Full suite before `7e3c278` | **1992 passed**, 1 skipped, 2 deselected (46:50) |
| `tests/test_fusion.py` + `test_reporter_accuracy.py` + `test_naming_conventions.py` + `test_phase23_acceptance.py` + `test_four_set_coverage.py` | 276 passed |

Net: **+20 tests, 0 regressions.** 1972 + 20 = 1992. The 1 skip is the pre-existing one; the 2 deselected are the paid golden tests, never run.

## Constraint Compliance

| Constraint | Evidence |
|---|---|
| No paid API | The only `golden` occurrences in the new test section are two lines of prose *forbidding* golden assertions; `grep -Ec 'accuracy_gate\|vision_only_benchmark\|golden_convergence\|ANTHROPIC_API_KEY'` over the section → **0**. `.env` never read. No `-m golden` run. |
| Offline gate green | 1992 passed / 1 skipped / 2 deselected, up from the 1972 baseline by exactly the 20 tests added. |
| `test_phase23_acceptance.py` + `test_four_set_coverage.py` green | Explicitly run together (276 passed) and inside every full-suite run. |
| Coincidence trap fenced | `grep -Ec '== *28\b\|== *132\b\|== *136\b\|== *56\b'` over the new section → **0**. No number moved toward golden. |
| No golden total in the differential | `grep -A40 'def test_wall_class_label_invariance' … \| grep -Ec '== *106997\|== *142661\|== *11294'` → **0**. |
| `canonical_library_name` not duplicated | `_squash_wall_name` is case/separator only and a test asserts it does NOT fold plurals or synonyms; 24-03 keeps ownership. |
| No numeric field in a vision schema | No schema file touched. |
| Paid-run evidence untouched | `git status --porcelain .planning/paid-run-evidence/ \| wc -l` → **0**, checked before every commit. The differential opens `takeoff.json` read-only. |
| `uploads/`, `human_inputs/`, `reports/`, `.env` untouched | Not in any commit. |
| No new packages | `git diff --stat requirements.txt setup.py pyproject.toml \| wc -l` → **0**. |
| Python 3.9 | `python3 --version` → 3.9.6; `Optional`/`Tuple` from `typing`, no 3.10+ syntax. |
| No `--no-verify` | All three commits ran normally. |
| GitNexus before editing fusion symbols | `impact` run and HIGH risk warned; `detect-changes` before each commit. |

## Issues Encountered

- **`map_wall_classes_from_library`'s return shape had to widen** to carry the printed thickness the audit record publishes. Rather than break every caller, `_fuse_wall_classes` **indexes** the tuple instead of unpacking it and tolerates a pre-24-02 3-tuple, with a test pinning that tolerance. The existing `tests/test_naming_conventions.py` assertions already index (`mapping["TC2"][0]`, `[2]`) and were untouched.
- **The two saved runs did not differ on the wall-class label itself.** Both named `WALL-TC1` "Tilt Up Wall"; the recorded wall-layer variance is in the *vocabulary* (F3) and in the assignment flip the ground truth documents. The fixture is built from exactly that — names read from the evidence at runtime, assignment inverted per the documented flip — and a companion test asserts the two runs really did publish different name sets, so the differential can never quietly become a comparison of a label set with itself.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

**Blocks nothing; unblocks the honesty of 24-03 and 24-05.** The residual this plan cannot close is now a *runnable assertion* rather than a planning note: when 24-03 lands `canonical_library_name` and 24-05 persists the vocabulary, `test_wall_class_label_invariance`'s third-class residual assertion is the thing that should start failing — that failure is the signal those plans worked. Whoever lands them should expect to update that one assertion deliberately, and should not "fix" it by deleting it.

**For 24-04 (unnamed-geometry ledger):** the else-branch at the bottom of `_fuse_wall_classes` is untouched and still emits `name = candidate_id` with `review_reason: "unlabeled wall thickness class"`. `test_no_bind_and_no_label_still_reaches_the_unlabeled_branch` pins its current shape so 24-04 can change it against a known baseline.

**For 24-10 (phase gate):** `fusion_rejected` now carries a fourth record kind. The gate should read `wall_class_thickness_bind_outranks_label` records as evidence that the precedence fired, and count them — a run with zero of them either had no wall disagreements or lost the wiring.

**Honest expectations to carry into verification:**
- **No accuracy claim is made or measurable here.** Nothing was measured against golden, and nothing may be. Judge this plan on determinism and on the honesty of its audit trail.
- The 49× mutation swing is evidence the test *catches the defect*, not evidence that a paid run's number will move. Which class is called CMU is now stable; what CMU measures is a different question and a different phase.

## Self-Check: PASSED

All claimed files exist on disk (`src/bobbytailor/vision/fusion.py`, `tests/test_fusion.py`, `deferred-items.md`, this SUMMARY). All three claimed commits resolve in `git log` (`a56d877`, `236e295`, `7e3c278`). `.planning/paid-run-evidence/` is untouched (0 porcelain entries).

---
*Phase: 24-binding-determinism-text-anchored-labeling*
*Completed: 2026-08-05*

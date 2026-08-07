---
phase: 28-accuracy-remediation-crow-defects
plan: 04
subsystem: vision-fusion
tags: [wall-classes, thickness-binding, uniqueness, masonry-guard, flag-dont-guess, fusion_rejected, crow]

# Dependency graph
requires:
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 02
    provides: "the precedence inversion (a printed-thickness match outranks a vision label), the four-tuple bind shape whose fourth slot carries the deciding thickness, and the `wall_class_thickness_bind_outranks_label` audit record this plan's refusal record is modelled on"
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 04
    provides: "the unnamed-geometry ledger a class nothing evidenced falls through to"
provides:
  - "`map_wall_classes_from_library` pass 1 rebuilt as a bipartite (object, class) candidacy — a confident bind requires MUTUAL uniqueness, and the result no longer depends on vocabulary order"
  - "`contested` — an optional out-dict reporting every class whose thickness match was refused, with the contesting object names and the other classes one object also matched"
  - "`_MASONRY_MAX_LF_SHARE` + `_wall_class_lf_share` + `_masonry_bind_forbidden` — a dimensionless LF-share masonry guard applied at BOTH the thickness pass and the hint pass, beside the unchanged rank guard"
  - "`_WALL_THICKNESS_BIND_CONTESTED_REASON` + `_reject_contested_wall_thickness_bind` — a refusal record distinct by key from an override record"
  - "an unnamed-geometry ledger detail that distinguishes a contested class from an unmatched one"
  - "tests/test_phase28_wall_class_binding.py — 36 free checks, the ambiguity measured on the real Crow plan page"
affects: [28-05, 28-06, 28-07, 25]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "A match is evidence of IDENTITY only when it discriminates; a match two candidates satisfy identifies neither, on whichever axis the candidates lie"
    - "Inside a tolerance, 'nearer' is the noise the tolerance exists to absorb — reading it back as a preference is reading signal out of noise"
    - "A refusal is a refusal to IDENTIFY, never a deletion: the losing object is not consumed and the measured length is not lost"
    - "A threshold that states a fact about a shape is asserted to be scale-invariant, which no threshold derived from a particular drawing's footage could survive"
    - "The plan's premise is re-measured before the code moves, and the measurement is committed as a runnable check"

key-files:
  created:
    - tests/test_phase28_wall_class_binding.py
  modified:
    - src/bobbytailor/vision/fusion.py

key-decisions:
  - "Uniqueness is MUTUAL, not one-sided. The plan asked for the object axis (two objects, one thickness). The real sheet exhibits the class axis (one object, three classes) and the plan's own argument applies to it word for word — implementing only the named half would have left the defect the plan exists to fix in place."
  - "Pass 1 is a bipartite candidacy, not a loop. The old object-outer loop could not ask the uniqueness question, because by the time an object had taken a class the class was gone from every later object's view. Rewriting the shape is what made the question askable — and removed the vocabulary-order dependence as a side effect."
  - "`contested` is an optional OUT-PARAMETER, not a widened return. Fourteen call sites index the four-tuple; changing the return type would have broken every one of them for an explanation none of them wants."
  - "`_MASONRY_MAX_LF_SHARE = 0.25` states a fact about what a masonry wall IS and is asserted scale-invariant. It is NOT tuned toward any class, and it is reported below that it does not fire on Crow."
  - "The refusal carries its OWN reason key. An override says the printed thickness beat the reading; a refusal says the printed thickness proved nothing and the reading stands. A reader who cannot tell them apart by key alone cannot count either."
  - "V4-FIX-03 is ADVANCED, not completed. The mis-binding is removed and flagged; 'CMU Wall binds the CORRECT class' is not proved and cannot be without a paid run and an evidenced masonry binder."

patterns-established:
  - "Falsify-before-you-fix, continued: the plan's stated mechanism was tested against the frozen evidence and the real geometry BEFORE the code changed, and the finding is a committed assertion rather than a note."
  - "Apply a stated principle to every axis it covers, not only the axis the plan named — and say in the summary that the extra axis is where the real defect lived."
  - "A threshold's independence from any drawing is proved by scaling the drawing, not asserted in a comment."

# V4-FIX-03 reads: "CMU Wall binds the correct thickness class (11,286 SF vs golden 2,204; ~313 LF
# bound where golden implies ~61)." The class it wrongly bound is now REFUSED and the refusal is
# audited — measured on the real geometry, TC5 is contested and no longer confidently named. What
# the requirement's wording additionally asks — that CMU bind the *correct* class — is not
# delivered: with the thickness route refused, `CMU Wall` reaches pass 2's masonry-by-hint rule,
# which hands it the smallest remaining class on no evidence beyond "masonry is small". That is a
# flagged hint bind, not a demonstrated correct one, and it is named as a residual below. Ticking
# the requirement would claim a correctness this plan measured to be absent. 28-07 is its closer.
requirements-completed: []
requirements-advanced: [V4-FIX-03]

coverage:
  - id: D1
    description: "The ambiguity is measured on the real drawing before anything is changed: an 8\" object lands inside the 1.5\" tolerance of three of Crow's thirteen wall classes, whose lengths differ by more than 2x"
    requirement: "V4-FIX-03"
    verification:
      - kind: integration
        ref: "tests/test_phase28_wall_class_binding.py#test_a_printed_nominal_thickness_is_not_unique_on_the_real_sheet"
        status: pass
      - kind: integration
        ref: "tests/test_phase28_wall_class_binding.py#test_the_silent_tie_break_is_recorded_in_both_saved_runs"
        status: pass
    human_judgment: false
  - id: D2
    description: "A thickness two OBJECTS both print binds neither, a unique match still binds confidently, and the object that lost the contest is not consumed"
    requirement: "V4-FIX-03"
    verification:
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_a_thickness_two_objects_both_print_is_not_unique_and_binds_neither"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_a_thickness_only_one_object_prints_is_unique_and_still_binds"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_an_object_that_lost_a_unique_contest_is_not_consumed"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_the_fourth_slot_is_none_for_everything_that_is_not_a_confident_bind"
        status: pass
    human_judgment: false
  - id: D3
    description: "The same rule on the axis the real sheet exhibits — an object whose printed thickness fits two CLASSES binds neither, and the exactly-agreeing class is not preferred inside the tolerance"
    requirement: "V4-FIX-03"
    verification:
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_an_object_matching_two_classes_is_not_unique_and_binds_neither"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_the_nearer_class_is_not_preferred_inside_the_tolerance"
        status: pass
      - kind: integration
        ref: "tests/test_phase28_wall_class_binding.py#test_the_real_sheet_gives_a_nominal_object_no_confident_class"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_the_bind_does_not_depend_on_the_order_the_objects_arrive_in"
        status: pass
    human_judgment: false
  - id: D4
    description: "A masonry object refuses a large-share class at any rank, still binds a genuinely small one, cannot walk around the guard by taking the hint route, and the rank guard still speaks where the share test is silent"
    requirement: "V4-FIX-03"
    verification:
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_a_masonry_object_refuses_a_large_share_class_that_is_not_the_dominant_one"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_a_masonry_object_still_binds_a_genuinely_small_class"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_the_hint_pass_cannot_walk_around_the_share_guard"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_the_dominant_exclusion_still_holds_where_the_share_test_is_silent"
        status: pass
    human_judgment: false
  - id: D5
    description: "No threshold introduced here is traceable to any Crow quantity — the guard reaches an identical verdict when every length on the sheet is scaled by an arbitrary factor"
    requirement: "V4-FIX-03"
    verification:
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_the_share_guard_binds_no_absolute_length_at_all"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_the_share_threshold_is_a_dimensionless_fraction"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_this_module_states_no_published_takeoff_quantity"
        status: pass
    human_judgment: false
  - id: D6
    description: "A refusal is auditable — the record names the contesting objects and the classes one object also matched — and a contested class reads differently from an unmatched one"
    requirement: "V4-FIX-03"
    verification:
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_a_refused_bind_appends_one_record_naming_the_contesting_evidence"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_a_contested_class_with_a_vision_label_keeps_the_label_and_says_why"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_a_contested_class_with_no_label_says_contested_in_the_ledger"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_an_unmatched_class_still_reads_as_unmatched_not_as_contested"
        status: pass
    human_judgment: false
  - id: D7
    description: "24-02's precedence and its arbitration rank are untouched — an override still fires for a genuinely unique match, silence still appends nothing, and the refusal key is neither the override key nor a C3a suppression key"
    requirement: "V4-FIX-03"
    verification:
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_a_genuinely_unique_match_still_overrides_a_dissenting_label"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_an_uncontested_silent_sheet_appends_nothing_at_all"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_the_thickness_name_source_still_ranks_with_the_naming_library"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_wall_class_binding.py#test_the_refusal_key_does_not_reuse_a_c3a_suppression_key"
        status: pass
      - kind: integration
        ref: "python3 -m pytest tests/test_determinism_harness.py -q → 18 passed, 0 skipped (24-09's residual test unaffected and unedited)"
        status: pass
    human_judgment: false
  - id: D8
    description: "An estimator reading a flagged `CMU Wall` hint bind on a 2.5 LF class, beside a refusal record naming what was contested, acts on it correctly"
    verification: []
    human_judgment: true
    rationale: "How the refusal and the fall-through hint bind read on a client report cannot be seen without a paid run, which is a human spend decision. `score_report_dir.py` re-scores frozen artifacts and returns the same numbers whatever this code does."

# Metrics
duration: 160min
completed: 2026-08-07
status: complete
---

# Phase 28 Plan 04: A Thickness That Does Not Discriminate Summary

**A printed thickness is evidence of dimension and only becomes evidence of identity when exactly one candidate claims it — so `map_wall_classes_from_library` pass 1 is now a mutual-uniqueness test on both axes, the masonry guard tests the size of the wall rather than its rank, and a refused bind reaches the report with the objects that contested it named. Measured on the real Crow geometry: the class that published `CMU Wall` is now CONTESTED and confidently named by nothing.**

## Performance

- **Duration:** 160 min (69 min of it the full offline suite, plus 25 min of gate sweeps, all run in the foreground)
- **Started:** 2026-08-07T00:00Z
- **Completed:** 2026-08-07T02:40Z
- **Tasks:** 3 (all TDD)
- **Files modified:** 2 (1 created, 1 modified)

## What was measured before anything was changed

The plan named a mechanism. It was checked against the frozen evidence and the real
geometry first, and it is **not** the mechanism that fired. Two findings, both free, both
committed as runnable checks.

### 1. The contest is one object against several CLASSES, not two objects against one class

`scripts`-free probe of `tests/fixtures/crow_cass/crow_cass_plans.pdf` page 0, vector geometry
only:

| class | LF | share of all wall linework | LF-weighted mean thickness |
|---|---|---|---|
| TC1 | 1714.0 | 36.63% | 8.80" |
| TC2 | 1113.5 | 23.79% | 9.60" |
| TC3 | 778.0 | 16.62% | 11.20" |
| TC4 | 415.1 | 8.87% | 4.80" |
| **TC5** | **313.5** | **6.70%** | **8.00"** |
| TC6 | 105.5 | 2.25% | 3.20" |
| TC7 | 78.1 | 1.67% | 4.00" |
| TC8 | 51.7 | 1.10% | 5.60" |
| TC9 | 44.2 | 0.94% | 6.40" |
| TC10 | 33.9 | 0.72% | 7.20" |
| TC11 | 24.7 | 0.53% | 10.40" |
| TC12 | 5.0 | 0.11% | 12.00" |
| TC13 | 2.5 | 0.05% | 14.40" |

An object printing a nominal **8"** is within the 1.5" tolerance of **three** of them —
TC1 (8.80"), TC5 (8.00") and TC10 (7.20") — whose lengths differ by a factor of 50. The old
pass took the *nearest*, which is TC5. Inside a tolerance the residual difference is precisely
the noise the tolerance exists to absorb, so "nearest" was reading signal out of noise.

### 2. No second object contested it, and the evidence says so deductively

The saved vocabulary was not persisted in the run artifacts, so this is a deduction from what
the frozen `takeoff.json` files DO record, stated as a chain rather than an assertion:

- exactly one wall class published a thickness bind (`CMU Wall` on TC5, `matched_thickness_in`
  8.0, `class_thickness_in` 8.0, identical in both P24DET runs);
- `Internal Tilt up walls` published with review reason "wall class named by naming library
  (**hint** bind)", so it produced no thickness match;
- `Tilt Up Wall` published `NOT MEASURED / unit_class_conflict`, so it bound no class at all;
- any *other* wall object printing a thickness within 1.5" of a free class would have bound one
  in pass 1 or been assigned one in pass 2, and would therefore have published a wall row. No
  other wall row exists in either run.

So the plan's stated defect — "both object families print 8\", the match is contested between
two objects" — did not occur on this sheet. **The plan's principle is exactly right; the axis it
named is not the axis that failed.** Implementing only the named half would have shipped a
correct rule that left the defect it exists to fix untouched, so both axes were implemented (see
deviation 1).

## Accomplishments

- **Pass 1 is a bipartite candidacy over (object, class) pairs.** A confident bind is recorded
  only when exactly one object claims the class AND that object's printed thickness fits exactly
  one class. The old first-match-wins loop over objects *could not ask* the uniqueness question —
  by the time an object had taken a class, the class was already gone from every later object's
  view — which is why it was never asked. Rewriting the shape is what made the question askable.
- **The bind no longer depends on vocabulary order.** A free side effect of mutual uniqueness:
  a perfect matching is order-independent by construction, and a test reverses the object list and
  requires an identical map. That is a direct contribution to V4-DET-02's end-to-end story, whose
  named residual (24-02) is that the vocabulary is re-derived on every run.
- **A refusal is a refusal to IDENTIFY, never a deletion.** The object that loses a contest is not
  consumed and still reaches pass 2's hint assignment; the class keeps its measured LF and reaches
  either a vision label or the ledger. `matched_thickness_in` stays `None` for everything that is
  not a confident bind, which is the invariant that keeps a non-authoritative bind out of the
  authoritative branch, and it is asserted directly.
- **The masonry guard tests the size of the wall, not its position in a ranking.** The rank test
  could only ever exclude ONE of Crow's thirteen classes. `_MASONRY_MAX_LF_SHARE` refuses any class
  carrying more than a quarter of the sheet's wall linework, at any rank, on both the thickness
  route and the hint route — so the guard cannot be walked around by taking the other door. The
  rank test is kept because it still speaks where the share test is silent (five equal classes,
  none above threshold: a test isolates exactly that case).
- **Nothing here is tuned toward a target.** The share threshold states a fact about what a masonry
  wall is, and its independence from any drawing is *proved* rather than asserted: scaling every
  length on the sheet by an arbitrary factor must produce an identical verdict, which no threshold
  derived from a particular plan's footage could survive. The test module additionally refuses to
  contain any of the four published quantities involved, each assembled from halves so the check
  cannot match itself.
- **The disagreement is recorded instead of decided.** `_WALL_THICKNESS_BIND_CONTESTED_REASON` is
  its own key, carrying the contesting object names, the classes one object also matched, and the
  class's own measured thickness. A contested class named by vision keeps the name, is flagged, and
  the row states what was refused. A contested class nothing names reaches the ledger with a
  sentence that says *contested*, not *unmatched* — two different facts, two different sentences.
- **Full offline suite: 2300 passed, 1 skipped, 2 deselected** in 1:08:40, against a baseline of
  2264/1/2 at `061f3eb`. +36 = exactly this plan's new module, **zero regressions**. Collection
  arithmetic confirms it: 2303 collected − 2 deselected = 2301 = 2300 passed + 1 skipped.

## Task Commits

1. **Task 1: a thickness match that does not discriminate is not evidence** — `b43c8a3` (test, RED) → `991b6cb` (feat, GREEN)
2. **Task 2: a masonry object is a small wall, whatever its rank** — `af644d1` (test, RED) → `a56fbe1` (feat, GREEN)
3. **Task 3: record the refused bind instead of deciding it in silence** — `a235f35` (test, RED) → `4de87bf` (feat, GREEN)

No REFACTOR commit was needed on any task; each GREEN implementation was already at its final shape.

## Files Created/Modified

- `src/bobbytailor/vision/fusion.py`
  - `_MASONRY_MAX_LF_SHARE` beside `_WALL_THICKNESS_TOL_IN`, with the geometric argument in its
    comment and an explicit statement that it is a dimensionless fraction.
  - `_wall_class_lf_share()` — each class's LF as a fraction of the sheet's total; a pure ratio.
  - `_masonry_bind_forbidden()` — the rank guard (unchanged) plus the share guard, with the
    reasoning for keeping both.
  - `map_wall_classes_from_library()` — pass 1 replaced by the bipartite candidacy; a new optional
    `contested` out-dict; the identity-vs-dimension principle stated in the docstring.
  - Pass 2's masonry-by-hint branch routed through the same `_masonry_bind_forbidden` predicate.
  - `_WALL_THICKNESS_BIND_CONTESTED_REASON`, `_contest_sentence()`,
    `_reject_contested_wall_thickness_bind()`.
  - `_fuse_wall_classes()` — a `contested_wall_classes` parameter, the refusal record and row note,
    and the branched ledger detail.
  - `fuse_sheet()` — collects the mapper's contest report and threads it through, so the refusal an
    audit record explains is the SAME refusal the mapper made.
- `tests/test_phase28_wall_class_binding.py` — **new.** 36 checks in five groups: the ambiguity
  measured on the real sheet and read back from the frozen runs, uniqueness on the object axis,
  uniqueness on the class axis, the LF-share masonry guard, the refusal audit trail, and the
  module's own contract (free, offline, golden-free, quantity-free).

## The measured effect on Crow, stated plainly

Run against the real page-0 geometry with the two wall objects the saved runs published rows for
(names taken from the frozen artifacts; the vocabulary itself was not persisted):

| | before | after |
|---|---|---|
| TC5 (313.5 LF, 8.00") | `CMU Wall`, **confident thickness bind**, printed 8.0" | **contested** — `CMU Wall` also matches TC10; no confident bind |
| TC1 (1714.0 LF, 8.80") | `Internal Tilt up walls`, hint bind | unchanged — hint bind |
| `CMU Wall` | consumed by TC5 | not consumed; falls to pass 2 and takes TC13 (2.5 LF) as a **flagged hint bind** |

**The class the defect published under is now refused, and the refusal is audited.** With the
thickness route closed, TC5 is named by whatever the vision pass read it as — in both saved runs,
`tilt-up concrete panel`, which is what the sheet's own printed notes describe throughout
(`TYPICAL S.C.C.P. JOINT DETAIL`, `ALL TILT WALL PANELS SHALL BE CAULKED TO FULL HEIGHT`).

**The LF-share guard did NOT fire on Crow, and that is reported rather than fixed by tuning.** TC5
carries 6.70% of the sheet's wall linework against a 25% cap. Lowering the cap until TC5 were
excluded is precisely the rejected methodology, and it was not done. The guard closes a real hole
(a masonry object could previously take a 40%-share class that merely was not the largest); it is
not what fixed this drawing. **Uniqueness is what fixed this drawing.**

## Decisions Made

- **Uniqueness is mutual.** Both axes, one rule, one sentence in the docstring. See deviation 1.
- **`contested` is an out-parameter.** Fourteen call sites index the four-tuple. Widening the
  return would have broken all of them to deliver an explanation none of them asked for, and the
  plan's own instruction was to keep the tuple shape and carry the contest separately.
- **The nearer candidate is deliberately not preferred, on either axis.** The plan states the
  argument for the object axis; it is identical for the class axis and is quoted in the code.
- **Both masonry guards are kept.** The share test is uninformative on a sheet whose classes are
  all modest; the rank test is nearly useless on a sheet with thirteen of them. A test isolates the
  case where only the rank test speaks, so neither is dead code.
- **The refusal record is emitted whether or not something else names the class.** A refusal is a
  fact about the evidence regardless of what happens next, and the ledger detail alone cannot name
  the contesting objects.
- **The ledger's reason CODE is unchanged; its DETAIL is branched.** `UNNAMED_WALL_CLASS_UNLABELED`
  is read by `reporter.py` and pinned by tests in two other modules. Splitting the code would have
  been a marker change dressed as a wording change; branching the prose distinguishes the two facts
  where a reviewer reads them.

## Deviations from Plan

### Plan premise falsified by measurement

**1. [Rule 2 — Missing Critical] The contest on this sheet is one object against three classes, not two objects against one class**

- **Found during:** the pre-implementation measurement, before any code changed.
- **Plan claimed:** "Crow prints S.C.C.P. tilt panels throughout and both object families print
  8\"." and "check whether any OTHER wall object in `wall_objects` also parses a printed thickness
  within `_WALL_THICKNESS_TOL_IN` of that class's measured thickness."
- **Measured:** an 8" object is within tolerance of **three** of Crow's thirteen classes (TC1 8.80",
  TC5 8.00", TC10 7.20"), and the frozen artifacts show that exactly one thickness bind occurred on
  the sheet — no second object contested it (the deductive chain is above).
- **Why this mattered:** implemented exactly as written, the object-axis test alone would have
  changed nothing on Crow. TC5 would still have been bound confidently by the nearest match, the
  audit record would still have read "deterministic evidence", and the plan's own objective — "stop
  a non-unique printed-thickness match from outranking a vision reading that contradicts it" —
  would have gone unmet by the plan that states it.
- **Fix:** the uniqueness test is **mutual**. A confident bind requires that exactly one object
  claims the class AND that the object's printed thickness fits exactly one class. This is the
  plan's own argument, applied on the axis the plan did not name; nothing was invented and nothing
  was weakened.
- **Files modified:** `src/bobbytailor/vision/fusion.py`
- **Verification:** `test_an_object_matching_two_classes_is_not_unique_and_binds_neither`,
  `test_the_nearer_class_is_not_preferred_inside_the_tolerance`, and
  `test_the_real_sheet_gives_a_nominal_object_no_confident_class` (real geometry). The four
  object-axis checks the plan asked for pass alongside them.
- **Committed in:** `991b6cb` (Task 1 GREEN)

### Plan expectation that did not materialise

**2. The LF-share masonry guard does not fire on the class this plan was written about**

- **Plan expected:** "the one that took `CMU Wall` carries roughly 313 LF at the published height,
  which is a large share of the sheet but not the largest, so the guard never fired."
- **Measured:** 313.5 LF is **6.70%** of the sheet's 4679.7 LF of wall linework. It is the fifth
  largest of thirteen classes and is a *small* share by any threshold that could be argued from the
  construction the plan describes.
- **What was done:** the guard was implemented as specified, with a threshold argued from what a
  masonry wall IS (a room-scale exception inside a shell built of something else) and proved
  scale-invariant. It was **not** lowered until TC5 was excluded — that is the documented, rejected
  methodology, and doing it would have been tuning to golden through an intermediary.
- **Impact:** the guard closes a real hole and is worth having; it is not what fixes this drawing,
  and no commit or assertion in this plan claims that it is.

### The residual this plan does not close

**3. Pass 2's masonry-by-hint rule hands `CMU Wall` the smallest remaining class on no evidence**

- **Found during:** the post-fix measurement on real geometry.
- **Measured:** with the thickness route refused, `CMU Wall` reaches pass 2, where the pre-existing
  rule assigns a masonry object the smallest eligible class — on Crow, TC13 at 2.5 LF. The bind is
  `confident=False` and the published row is flagged `needs_review`, so nothing is silently
  guessed, but "masonry is the smallest class" is an assumption, not evidence.
- **Why it was not auto-fixed here:** this plan's stated fence is uniqueness, the share guard and
  the refusal record; the plan explicitly *keeps* pass 2's masonry assignment and only adds the
  share test to it. Replacing an unevidenced hint rule with an evidence requirement is an
  architectural change to the binder, which is a Rule 4 decision and not this plan's to make.
- **Impact on V4-FIX-03:** this is exactly why the requirement is marked **advanced** rather than
  completed. "CMU Wall no longer binds a class its evidence could not identify" is delivered and
  measured. "CMU Wall binds the *correct* class" is not, and cannot be asserted from anything
  available offline.

---

**Total deviations:** 1 auto-fixed missing-critical (from a falsified premise) + 1 plan expectation
that did not materialise + 1 named residual.
**Impact on plan:** deviation 1 was required for the plan's own objective to hold on the drawing
the plan is about. No scope creep — it is the same predicate, the same tolerance and the same
sentence of reasoning, applied to the second index of the same relation.

## Non-vacuity Evidence

- Each task's RED run failed exactly the checks its GREEN implementation then turned green: 9 of 18
  (task 1), 5 of 8 (task 2), 8 of 18 selected (task 3). The "still binds", "still overrides" and
  "silence appends nothing" guards passed in both directions at every stage.
- The two measured-premise checks (`..._is_not_unique_on_the_real_sheet` and
  `..._recorded_in_both_saved_runs`) **passed at RED**, before any code moved — so the premise is
  recorded as an observation of the pre-fix system, not as a description of the fix.
- The module's real-geometry assertions run the shipped predicate against the actual Crow bundle,
  not a reconstruction of it, so a check cannot pass against geometry the code never sees.
- `test_the_share_guard_binds_no_absolute_length_at_all` is a mutation test in disguise: any
  threshold expressed in feet rather than as a ratio makes it fail.

## Issues Encountered

- **The tool's 10-minute ceiling versus a 69-minute suite.** The full run was launched orphaned
  (`nohup … &`) writing to a log and polled in the foreground with an `until grep` loop until the
  completion line appeared: 1:08:40, `2300 passed, 1 skipped, 2 deselected`. The 25-minute
  four-gate sweep and the 12-minute `test_fusion.py` + `test_naming_conventions.py` regression
  checks hit the same ceiling and were handled the same way.
- **The reported baseline needed reconciling.** 28-03's summary records `2263 passed`, but its
  test-only follow-up commit `8de7ae0` added one check *after* that run, so the true baseline at
  `061f3eb` is **2264/1/2**. Confirmed by collection arithmetic rather than assumed:
  2303 collected − 2 deselected − 36 new = 2265 runnable before = 2264 + 1 skip.
- **`.planning/paid-run-evidence/` verified untouched** — `git status --porcelain` over that path
  returned `0` before every commit and after the last one (T-28-02). The new test module opens
  `takeoff.json` read-only and skips loudly if the tree is absent.
- **24-09's residual test was read before editing and needed no edit.** See below.

## 24-09's residual test: unaffected, and not touched

`tests/test_determinism_harness.py::test_the_residual_a_vision_named_wall_class_still_moves_with_its_label`
pins 24-02's open residual and carries an explicit instruction that closing that residual should
make it fail and that the closer must update it deliberately rather than delete it.

It was read before the change and run after it: **`tests/test_determinism_harness.py` → 18 passed,
0 skipped.** The test is unaffected and **no line of it was changed.**

Why it is unaffected, so the green tick means something: the harness replays committed fixtures in
which the naming-library response is `{"objects": []}`. With an empty vocabulary,
`_wall_objects_from_vocabulary` yields nothing, `map_wall_classes_from_library` returns an empty map
before pass 1 begins, and no contest can arise. The residual it pins — that a wall class with no
thickness match is still named by vision, and its pairing moves with the label — is untouched by a
rule about which thickness matches count, because the harness's classes have no thickness match to
contest in the first place.

## Constraint Compliance

| Constraint | Evidence |
|---|---|
| No paid API | No `-m golden`, no `accuracy_gate.sh`, no `vision_only_benchmark.py`, no `golden_convergence.py`, no `ANTHROPIC_API_KEY`, `.env` never read. The test module asserts its own import set against an offline allow-list via an `ast` walk. |
| Python 3.9 | `python3 --version` → 3.9.6; `Optional` / `Dict` / `List` / `Tuple` from `typing`, no 3.10+ syntax. |
| Offline gate green | 2300 passed / 1 skipped / 2 deselected, up from the 2264 baseline by exactly the 36 checks added. |
| Four named gates green | `test_phase23_acceptance.py`, `test_phase24_acceptance.py`, `test_four_set_coverage.py` and the 24-09 determinism harness run together: **61 passed, 1 skipped** (the pre-existing skip); the harness alone: **18 passed, 0 skipped**. All four are also inside the full suite. |
| Never tune to golden | No wall class is filtered anywhere. `2204`, `61 LF` and `36 ft` appear in no code and no test; `test_this_module_states_no_published_takeoff_quantity` asserts the module contains none of the four published figures, each token assembled from halves. The share threshold is proved scale-invariant. |
| 24-02's inversion not reverted | Thickness still leads. `test_a_genuinely_unique_match_still_overrides_a_dissenting_label` asserts the override still fires and still emits its record; `_NAME_AUTHORITY`'s rank for `naming_library_thickness` is asserted unmoved. |
| Verified with real-PDF geometry, not `score_report_dir.py` | Three checks run against the actual Crow page-0 deterministic bundle; the frozen-artifact check is read-only and asserts a record shape, never a quantity. |
| `.planning/paid-run-evidence/` read-only | `git status --porcelain .planning/paid-run-evidence/ \| wc -l` → **0**, before every commit and after the last. |
| `uploads/`, `human_inputs/`, `reports/`, `.env` untouched | Not read, not written, in no commit. The real-geometry checks use the committed fixture PDF, not `uploads/`. |
| `AGENTS.md`, `CLAUDE.md`, `tests/fixtures/synthetic/*.pdf` not committed | Those five files carry pre-existing unstaged modifications from before this plan; `git show --stat` over all six commits contains none of them. |
| No new packages | No `requirements.txt` / `setup.py` / `pyproject.toml` change. |
| No `--no-verify` | All six commits ran normally with hooks. |
| GitNexus before editing fusion symbols | Index verified up-to-date at `061f3eb`; `impact` run on both symbols and HIGH risk warned before a line changed; `detect-changes` run before each commit (risk low, 0 affected processes each time). |

## Risk Warning (CLAUDE.md gitnexus mandate)

`gitnexus impact map_wall_classes_from_library --direction upstream` → **risk HIGH** (3 impacted,
1 direct caller `fuse_sheet`, 3 affected processes `_run_sheet_vector` / `fuse_sheet` /
`_route_deterministic`, 2 modules). `_fuse_wall_classes` returned the same profile. **⚠️ HIGH risk
was warned before any edit**, as CLAUDE.md requires. Both changes were made anyway because they
*are* the plan's purpose, and they were made additively: one new optional out-parameter on the
mapper, one new optional parameter on the fuser, one new predicate clause, one new audit record and
one branched sentence. `detect-changes` reported **risk low, 0 affected processes** before every
commit, and the full offline suite at 2300/1/2 with zero regressions is the evidence the blast
radius was not disturbed.

## Threat Flags

None. No new network endpoint, auth path, file access pattern or trust-boundary schema change.

- **T-28-17** (spoofing — a thickness match treated as identity) **mitigated**, on both axes, with
  the real sheet's ambiguity as a committed measurement.
- **T-28-18** (elevation of privilege — the precedence) **mitigated**: the precedence is untouched
  and `_NAME_AUTHORITY`'s rank is asserted unmoved; only which matches earn it changed.
- **T-28-19** (repudiation — silently refused binds) **mitigated**: a distinct reason key carrying
  the contesting object names, the also-matched classes and the measured thickness.
- **T-28-20** (tampering — the LF-share threshold) **mitigated**: argued from construction, stated
  in the constant's comment, proved scale-invariant, and reported above as NOT firing on Crow
  rather than tuned until it did.
- **T-28-21** (tampering — 24-09's residual test) **mitigated**: read before editing, run after,
  unaffected, and not one line changed. The reason it is unaffected is stated so the green tick is
  interpretable.
- **T-28-22** (DoS — the per-class uniqueness scan) **accepted** as planned: thirteen classes
  against a handful of objects; the candidacy is O(objects × classes) and runs in microseconds.
- **T-28-SC** trivially met: no package installed.

## Known Stubs

None.

## User Setup Required

None — no external service configuration, no package installed, no paid API touched.

## Next Phase Readiness

- **28-07 must not claim this plan corrected a number.** What it may claim, and what is asserted:
  a printed thickness that fits several classes no longer names one of them; the class Crow
  published `CMU Wall` under is contested and confidently named by nothing; the refusal is audited
  by its own key. What it may NOT claim: that `CMU Wall` now binds the correct class. See the
  residual above, and mark V4-FIX-03 with that boundary in the same sentence (the 24-10 precedent).
- **28-06 gains a new route to classify.** `fusion_rejected` now carries a fifth record kind,
  `wall_class_thickness_bind_refused_as_contested`, and a wall row named by vision after a refusal
  is a *different* provenance from one named by vision with no bind in sight. A `quantity_route`
  column should distinguish them.
- **28-05 should note the refusal path.** A contested class with no vision label reaches the
  unnamed-geometry ledger, so it has a region and no name — the same shape 28-02's refused symbol
  binding produces, and relevant to how `region_ref` is threaded.
- **A follow-up worth filing: pass 2's masonry-by-hint rule is an unevidenced bind.** It hands a
  masonry object the smallest remaining class because masonry walls are small. That is a
  flag-don't-guess concern of the same family this phase exists to close, it now decides where
  `CMU Wall` lands on Crow, and it is out of this plan's fence.
- **No accuracy figure was produced and none can be.** `score_report_dir.py` re-scores frozen
  artifacts and returns the same numbers whatever this code does. A post-fix Crow number requires a
  paid run, which is a human spend decision. The naive metric is *expected* to move against this
  change: a confidently-wrong 11,286 SF becomes a flagged 90 SF hint bind plus a contested class
  named by a reading. Removing an unevidenced name was the deliverable.

## Self-Check: PASSED

Both claimed files exist on disk (`src/bobbytailor/vision/fusion.py`,
`tests/test_phase28_wall_class_binding.py`, and this SUMMARY). All six claimed commit hashes
resolve in `git log` (`b43c8a3`, `991b6cb`, `af644d1`, `a56fbe1`, `a235f35`, `4de87bf`).
`git status --porcelain .planning/paid-run-evidence/` returns `0` — the frozen evidence tree is
byte-unchanged (T-28-02).

---
*Phase: 28-accuracy-remediation-crow-defects*
*Completed: 2026-08-07*

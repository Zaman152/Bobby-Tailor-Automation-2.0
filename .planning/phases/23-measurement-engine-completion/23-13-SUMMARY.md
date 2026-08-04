---
phase: 23-measurement-engine-completion
plan: 13
subsystem: vision/fusion + deterministic/room_fill
tags: [SP-9, SP-10, wall-area, basis-binder-registry, one-area-one-item, multiplier, D-08, D-10, INV-00, INV-01, INV-02, V4-MEAS-01, V4-MEAS-02]
status: complete

requires:
  - phase: 23-09
    provides: "region_perimeters + region_shape_ratios on every fill, and MAX_HONEST_SHAPE_RATIO — the published threshold wall_perimeter_for_unit consumes"
  - phase: 23-11
    provides: "extent_ratio on every fill (the validation signal the new selector prefers), and the 1692-passed offline discipline"
  - phase: 23-12
    provides: "the is_typical flag the arbitration inherits, and the 1719-passed baseline this plan holds green"
provides:
  - "room_fill.wall_perimeter_for_unit — the billable perimeter under the blind shape gate; a leaking dominant region returns ZERO with the ratio named"
  - "room_fill.wall_area_for_unit — the one named perimeter × height anchor"
  - "room_fill.drawing_ceiling_heights + resolve_drawing_height — the unit's own RCP clip answers the height; AFF mounting tags rejected; project resolver a flagged fallback"
  - "room_fill.PARTITION_CONVENTION — board faces, read off the take-off's own markup (D-08 resolved from DATA)"
  - "fusion.BASIS_BINDERS + register_basis_binder — THE basis-to-binder registry replacing the _ROOM_FILL_BASES frozenset (SP-9)"
  - "fusion._bind_wall_area — wall_area finally binds: perimeter × drawing height × unit count"
  - "fusion._suppress_superseded_wall_items + _arbitrate_one_area_one_item — a measured region backs at most one line item; every suppression audited in fusion_rejected"
  - "fusion._multiplier_review_reason + the units-not-doors marker — the D-10 flag, exact on the four defective sheets"
  - "takeoff_pipeline._room_mix_meta_payload — the structural 'disputed' census-vs-manifest bit"
  - "select_fill_for_basis — ONE coordinated change: extent-ratio selection, ambiguity refusal, flag-intact availability"
affects:
  - "23-14 (elevation facade) — registers its binder in BASIS_BINDERS; the arbitration already covers whatever it emits; it must NOT add a parallel gate"
  - "23-15 (naming + linear binder) — registers 'linear' in BASIS_BINDERS; typical_detail suppression is already wired; DEF-23-13A ((t)/(ris) abbreviation tags) is its scope"
  - "23-16 (record) — the ~2× story correction now has committed flags to cite; the doc correction is still owed"
  - "Phase 24 — the Crow footprint-six-items symptom is defused here and scored there"

tech-stack:
  added: []
  patterns:
    - "a new measure basis REGISTERS a binder in one registry; a parallel frozenset gate is a structural defect (SP-9, D-03)"
    - "arbitration lands in the SAME commit as the binder it protects — a double-count landmine is defused as it is armed, never after (R5)"
    - "a height multiplying a quantity carries its source, and any source that is not the drawing's own tag (or learned) flags with the source named"
    - "a suppressed component goes to the rejected list with a reason naming the survivor; nothing vanishes silently (T-23-54)"
    - "a count above one is a number the drawing being measured does not contain — never high-confidence (SP-10)"
    - "a domain convention (partition billing) is read off the estimator's own data, quoted, and named on every row that uses it — never assumed and never fitted"

key-files:
  created: []
  modified:
    - src/bobbytailor/deterministic/room_fill.py
    - src/bobbytailor/vision/fusion.py
    - src/bobbytailor/pipeline/takeoff_pipeline.py
    - tests/test_room_fill.py
    - tests/test_fusion.py
    - .planning/phases/23-measurement-engine-completion/deferred-items.md

key-decisions:
  - "D-08 partition convention resolved from DATA, and it is NOT ambiguous: the take-off's legend label ('Gyp Wall … SF') states no convention, but the estimator's own Gyp Wall markup traces the bedroom/bath partition on BOTH faces — parallel strokes 6.5-8.3 pt apart (one wall thickness at 1/4\"=1'-0\") on ID-407, and again on ID-411 and ID-413. Board faces it is; summing each region's outer perimeter implements exactly that, and every wall row names it."
  - "Tasks 2 and 3 were committed as ONE commit (857357d), deviating from one-commit-per-task, because the plan's own hard constraint makes the ordering load-bearing: arbitration lands WITH the first new binder or the six-items defect multiplies through the new bases."
  - "The multiplier flag keys off a STRUCTURAL 'disputed' bit (census vs manifest cross-check computed in _room_mix_meta_payload) plus explicit manifest-only counts above one — NOT a blanket count>1, which would have flagged all nine census-confirmed sheets and violated D-10's 'exactly those four'."
  - "The wall binder refuses a bare perimeter_lf with no per-region geometry: billing it would bypass the shape gate. INV-01 §8 case 7's fixture therefore carries real region lists in the test."
  - "A room-fill wall row supersedes the same-named thickness-class row even when the room-fill row is a flagged zero: an honest flagged gap beats a confident wrong number (the 2,745 SF centreline figure), which is the point of the phase."

requirements-completed: [V4-MEAS-01]
requirements-advanced: [V4-MEAS-02]

coverage:
  - id: T1
    description: "Measured room geometry binds to a wall-area line item; the height comes from the drawing being measured and anything else flags"
    requirement: V4-MEAS-01
    verification:
      - kind: integration
        ref: "tests/test_fusion.py::test_wall_area_finally_binds_on_the_real_moxy_bundle + ::test_a_wall_binds_a_real_quantity_where_the_architectural_fill_is_honest — real PDF, the gate is open"
        status: pass
      - kind: integration
        ref: "tests/test_room_fill.py::test_every_prototype_reports_its_height_from_the_drawing_never_fifteen — all 16 prototypes, poisoned 15 ft answer deliberately armed and beaten"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py::test_a_measured_wall_binds_perimeter_times_height_times_units — INV-01 §8 case 7, 60×9×26=14,040, needs_review False"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py::test_the_fifteen_foot_plan_height_multiplies_but_flags + ::test_no_height_ships_the_perimeter_with_quantity_none_never_a_guess"
        status: pass
    human_judgment: false
  - id: T2
    description: "A leaking fill produces a flagged row, not a fabricated linear-foot figure"
    requirement: V4-MEAS-01
    verification:
      - kind: integration
        ref: "tests/test_room_fill.py::test_the_leaking_architectural_fill_refuses_with_a_reason[23,27,29] — the 8.62/9.04/8.54 signature, zero + reason"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py::test_a_degenerate_fill_yields_a_flagged_zero_row_that_exists — the row MUST appear"
        status: pass
    human_judgment: false
  - id: T3
    description: "One registry answers every basis; a measured region backs at most one line item; every suppression is audited"
    requirement: V4-MEAS-01
    verification:
      - kind: unit
        ref: "tests/test_fusion.py::test_registering_a_new_basis_routes_to_the_stub_binder + ::test_the_enclosed_region_bases_route_to_the_existing_binder"
        status: pass
      - kind: integration
        ref: "tests/test_fusion.py::test_on_the_real_crow_bundle_the_footprint_value_backs_one_line_item — the six-items defect reproduced and defused; COUNT asserted, not a name"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py::test_a_room_fill_wall_item_supersedes_the_thickness_class_estimate + ::test_a_deliberately_shared_area_survives_as_two_items_marked_deliberate + ::test_a_typical_detail_run_never_sums_with_the_main_plan_run"
        status: pass
    human_judgment: false
  - id: T4
    description: "The multiplier is visible, cross-checked, confidence-adjusted; the disagreement flag is exact"
    requirement: V4-MEAS-02
    verification:
      - kind: integration
        ref: "tests/test_fusion.py::test_the_multiplier_flag_fires_on_exactly_the_four_defective_sheets — real bundle + real census: fires on ID-412/416/420/422, clear on the nine, asserted per sheet AND as the exact set"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py::test_a_count_above_one_downgrades_confidence_and_records_the_source + ::test_a_count_of_one_does_not_downgrade + ::test_a_disputed_count_appends_the_units_not_doors_sentence"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py::test_two_validating_fills_of_one_name_return_nothing_with_an_ambiguity_flag + ::test_the_validated_fill_beats_a_clean_fill_with_no_extent_ratio + ::test_a_single_flagged_candidate_is_returned_with_its_flag_intact"
        status: pass
    human_judgment: false

metrics:
  duration: ~2h45m
  completed: 2026-08-04
  tasks: 4
  commits: 3
  tests_added: 45
  suite: "1764 passed, 2 deselected (baseline 1719)"
---

# Phase 23 Plan 13: Wall Binder + One-Area-One-Item Arbitration Summary

**Wall area finally binds — perimeter × height × unit count, through a basis-to-binder registry
that replaced the frozenset gate — and a measured region can no longer back six line items at
once. On the real Crow bundle the footprint value that backed SIX items backs exactly ONE, with
five audited suppressions; on the real Moxy bundle every prototype's wall height comes from its
own drawing (9'-0", BUNK A's 9'-8") with the poisoned 15-ft roof-plan answer deliberately armed
and beaten; the three leaking architectural fills refuse with the 8.62/9.04/8.54 signature named
instead of fabricating linear feet; and the multiplier-review flag fires on exactly
ID-412/416/420/422 and none of the nine census-confirmed sheets — with `git diff human_inputs/`
empty, because the four wrong counts are flagged, never edited.**

## Performance

- **Duration:** ~2h45m active (plus three full-suite gates at ~28-30 min each)
- **Tasks:** 4 of 4 — 3 commits (Tasks 2+3 deliberately share one; see Deviations 1)
- **Files:** 0 created, 5 code/test files modified + 1 planning doc

## What shipped

### Task 1 — the primitives, and a height read from the drawing itself (`af1c7b1`)

`wall_perimeter_for_unit` sums the per-region perimeters whose blind shape ratio sits at or under
the published `MAX_HONEST_SHAPE_RATIO`; annotation cells above it are dropped AND named; a
dominant region over the threshold — the INV-01 architectural-leak signature — returns **zero
with the ratio named**, so the caller flags instead of billing fabricated linear feet.
`wall_area_for_unit` is the one named `perimeter × height` anchor.

`drawing_ceiling_heights` scans text lines fully inside a clip, accepts feet-and-inches tokens in
the 7-12 ft ceiling band, and REJECTS any span carrying the AFF marker (`8'-1"AFF` is a towel
bar, not a ceiling — and it is in-band, so the marker, not the band, is what excludes it).
`resolve_drawing_height` returns the TALLER tag as `"drawing"` (the RCP prints the room height
and the lower bath/entry soffit; the wall boarded full height is the tall one), else the project
resolver's answer with its source carried, else `(None, "")` so the caller flags.

The pipeline stamps the height per plan name **from the RCP sibling clip** — mirroring how the
extent bound reads the AR sibling — because an architectural clip is full of room dimensions
(`10'-10 3/8"`) that land in the ceiling band and would be mistaken for heights. Measured on the
real PDF with the poisoned project answer armed (15 ft, source `"plan"`): all 16 prototypes, every
fill, `wall_height_source == "drawing"`, never 15.

**D-08, resolved from DATA and NOT ambiguous:** the take-off's legend label is silent — it reads
just `Gyp Wall … SF` — but the estimator's own markup answers the question. On ID-407 (KING A)
the Gyp Wall trace runs along BOTH faces of the bedroom/bath partition: parallel strokes at
x 426.5 / 433.0 pt and y 579.0 / 587.3 pt — 6.5-8.3 pt apart, one wall thickness at 1/4" = 1'-0"
— and the same double-face tracing repeats on ID-411 (offsets ~1.3 pt) and ID-413 (offsets
7.5 / 6.9 pt). **The convention is board faces: a shared partition bills once per side, the unit
envelope once.** Summing each enclosed region's outer perimeter implements exactly that; the
convention is published as `PARTITION_CONVENTION` and named on every wall row's formula.

### Tasks 2+3 — the registry, the binder, and the arbitration, in ONE change (`857357d`)

`BASIS_BINDERS` replaces the `_ROOM_FILL_BASES` frozenset: `ceiling_area` / `roof_area` /
`floor_area` register today's enclosed-area binder (behaviour pinned unchanged on the real Moxy
bundle — KING A's ceiling still binds 229.4 SF × 26 census units), and `wall_area` registers the
new branch. A stub binder registered against a new basis routes through the same loop; the
verification one-liner prints `registry only` — no `_ELEVATION_AREA_BASES`, no `_LINEAR_BASES`,
and no surviving reference to the old frozenset.

The wall binder flag-don't-guesses three ways: a leaking fill emits a **flagged zero row that
exists** (a missing row reads as "not required"; a flagged zero reads as "we could not measure
this"); no trustworthy height ships the measured perimeter with `quantity=None`, never a guessed
height; and a height from any source but the drawing's own tag or a learned value multiplies but
FLAGS with the source named — the 15-ft `CLEAR REQ'D` trap can no longer arrive silently.

The arbitration landed in the same commit, as the plan's constraint demands:

- `_suppress_superseded_wall_items` — a wall item measured from an actual enclosed region
  supersedes the same-named thickness-class estimate, which goes to `fusion_rejected` with
  `superseded_by_room_fill` and its quantity preserved for audit. Provenance merging cannot do
  this: both rows are `geometry`, so `merge_with_provenance` would drop one silently.
- `_arbitrate_one_area_one_item` — components sharing a `region_ref` (and unit) are one measured
  region: the first survives, the rest land in `fusion_rejected` with `one_area_one_item` and the
  survivor named — unless a component declares `shared_area`, in which case both survive and the
  sharing is recorded as **deliberate** with the partner names. A `typical_detail` row of the
  same name as a main-plan row is suppressed with `typical_detail_not_summed` — the 23-12
  `is_typical` flag wired in so 23-15's binder inherits it for free.

**The acceptance evidence:** on the real Crow bundle (fixture PDF, measured footprint, the
five floor/roof vocabulary names plus Building Footprint), the value that backed **six** line
items backs exactly **one** — asserted as a COUNT, not as any particular winner — with five
suppressions each carrying a reason. `git log -1 --stat` on `857357d` shows the binder and the
arbitration in the same commit.

### Task 4 — one coordinated selector change, and an honest multiplier (`c6db659`)

`select_fill_for_basis` changed once, coherently: prefer the fill whose extent ratio is closest
to one (tie-break by candidate id); two same-discipline fills both validating return nothing plus
an ambiguity flag that surfaces as an item-coverage record — never a silent smaller-area pick,
whose rationale was the falsified opposite-hand misdiagnosis. Wall area stays on the
architectural drawing (`BASIS_PLAN_KIND['wall_area'] == 'AR'` — `discipline unchanged`), and the
23-03 availability repair is preserved: all-flagged returns the smallest flagged candidate WITH
its flag.

The multiplier is now honest three ways: `confidence` downgrades high→medium whenever a known
count is above one (a number the drawing being measured does not contain); the count source is
on every row; and the units-not-doors review sentence — naming the measured extent ratio where
one exists — fires when the count is structurally **disputed** (`_room_mix_meta_payload`'s
census-vs-manifest bit) or manifest-only above one.

**The D-10 acceptance, measured on the real bundle with the real census:**

| fires | clear |
|---|---|
| ID-412 (KING SUITE C — census 1 vs manifest 2) | ID-407/408/409 (census 26/15/5) |
| ID-416 (BUNK A — census 1 vs manifest 2) | ID-410/411 (abbreviation match, counts AGREE) |
| ID-420 (ACC QQ RIS — manifest-only 2) | ID-413/414/415 (census 90/6/15) |
| ID-422 (ACC BUNK — manifest-only 2) | ID-417 (census 1) |

Exactly those four, and none of the nine. `git diff --stat human_inputs/` is **empty**.

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest -q` after each commit | **1739 / 1755 / 1764 passed, 2 deselected** (baseline 1719; +45) |
| Four-set gate `tests/test_four_set_coverage.py` | **14 passed**, standalone, after every task |
| Registry one-liner (`_ELEVATION_AREA_BASES`/`_LINEAR_BASES` absent) | `registry only` |
| `BASIS_PLAN_KIND['wall_area'] == 'AR'` | `discipline unchanged` |
| 16 prototype heights, poisoned 15-ft answer armed | all `drawing`-sourced; 9.0 (15 sheets), 9.667 (BUNK A); never 15 |
| AR leak signature refusal (p23/27/29) | zero + ratio named |
| Crow footprint value after arbitration | backs **1** line item; 5 audited suppressions |
| Multiplier flag | fires p28/32/36/38; clear p23-27, 29-31, 33 — the exact set |
| `git log 857357d --stat` | binder + arbitration in ONE commit |
| `git diff --stat human_inputs/` | **EMPTY** |
| `git diff --stat uploads/ reports/ docs/PIPELINE-GROUND-TRUTH.md` | **EMPTY** |
| `ast.parse(..., feature_version=(3,9))` | py39 ok on all modified files |
| `gitnexus detect-changes` before each commit | run: MEDIUM / LOW / HIGH (surfaced below) |

**No paid command was run.** `pytest -m golden`, `scripts/accuracy_gate.sh`,
`scripts/vision_only_benchmark.py` and `scripts/golden_convergence.py` were not executed; `.env`
was not read. Every number above came from a free offline probe or the offline suite.

### Impact analysis (CLAUDE.md), run before editing

| Symbol | Risk | Note |
|---|---|---|
| `_fuse_room_fills` | **HIGH** | 1 direct caller (`fuse_sheet`), 3 processes (`_run_sheet_vector`, `fuse_sheet`, `run_sheet`) |
| `_fuse_wall_classes` | **HIGH** | same fuse chain |
| `select_fill_for_basis` | **HIGH** | feeds `_fuse_room_fills` |
| `_measure_room_fills` | **HIGH** | 8 execution flows (as in 23-11) |
| `fuse_sheet`, `_resolve_project_wall_height` | LOW | |

**Those HIGHs are hereby surfaced, as CLAUDE.md requires** — and were anticipated by the plan
("expect HIGH/CRITICAL — fuse_sheet is the core"). Mitigated, not accepted: the sixteen pinned
real-PDF areas are byte-identical (the 23-09 equality test passes untouched), the real-bundle
ceiling binding is pinned unchanged through the registry, the full suite and the four-set gate
were green before every commit, and the arbitration shipped inside the same commit as the binder
it protects. The Task 4 `detect-changes` also read HIGH (6 processes) for the same chain.

## Deviations from Plan

### 1. [Decision — mandated by the plan itself] Tasks 2 and 3 share one commit

The plan instructs one commit per task AND that "arbitration lands WITH this binder, in the same
change. Not after." — and Task 3's own acceptance requires `git log -1 --stat` to show binder and
arbitration together. The constraint wins: `857357d` carries both. Committing Task 2 alone would
have armed the six-items defect through the new wall basis with nothing defusing it.

### 2. [Measurement wins over the plan literal] BUNK A's ceiling is 9'-8", not 9'-0"

The acceptance says "every Moxy reflected-ceiling prototype reports a wall height of nine feet".
Fifteen do. **Page 32 (BUNK A) prints `9'-8"`** inside its RCP clip — measured, standalone, no
AFF marker — so the shipped test pins 9.667 there, per the 23-09 rule that the pre-change
measurement outranks a plan literal. What the acceptance actually protects holds everywhere: the
source is the DRAWING, and the value is never the roof-plan 15.

### 3. [Measurement wins over the plan literal] Page 33's architectural fill is honest

The acceptance asks that "the four Moxy prototypes measured in INV-01 §4 return … ZERO plus a
reason from their architectural fill". INV-01 §4's own data says otherwise for one of them:
BUNK B's AR ratio is **4.37** — inside the honest band — and 23-09 recorded the same ("it is not
a detector that fires everywhere"). The tests pin zero+reason on pages 23/27/29 (8.62/9.04/8.54)
and a **positive billable perimeter on page 33's AR fill**, which is the leak signature
reproduced exactly as measured.

### 4. [Superseded test rewritten in-plan] One, not two

`test_fuse_binds_wall_area_and_floor_roof_from_vocabulary` asserted that BOTH footprint-bound
items survive — the precise one-region-many-items shape this plan abolishes. Rewritten in this
plan (the 23-09 precedent: a red suite across plans camouflages real regressions) to assert the
new contract: one survivor, one audited suppression. The plan's verification budgeted "two
superseded tests … 23-16 rewrites"; only this one existed.

### 5. [Design decision under D-10] The multiplier flag is structural, not blanket

INV-02 step 6's literal rule ("ratio available and count above one → append a review reason")
would flag all nine census-confirmed sheets (QQ A × 90, KING A × 26 …), violating the same plan's
"exactly those four". Resolved by conditioning on evidence of a PROBLEM: a structural
`disputed` bit (census vs manifest disagreement, computed in `_room_mix_meta_payload` rather than
grepped from note prose) or a manifest-only count above one that nothing in the drawings
confirms. A bare `room_mix` with no meta (legacy callers, synthetic case 7) has nothing to
cross-check and does not fire. The confidence downgrade above one **is** blanket, as specified.

### 6. [Honest noise, logged] ID-419 also fires the marker — DEF-23-13A

ACC KING TUB's count (3) is manifest-only because the census tag `king (t)` = 3 fails the
word-prefix abbreviation match, so its row carries the marker although the drawings likely
confirm the count. Outside the plan's 13 pinned sheets; the abbreviation gap is a naming rule and
belongs to 23-15. Logged as **DEF-23-13A**.

### 7. [Scope boundary — logged, NOT fixed] The suite still rewrites three synthetic fixture PDFs

`tests/fixtures/synthetic/{dimensions,floorplan,symbols}_synthetic.pdf` come back modified after
any full-suite run. Pre-existing (23-08 dev 6 … 23-12 dev 4), unrelated, reverted rather than
committed — three times.

---

**Total deviations:** 1 plan-mandated commit merge, 2 measurement-wins corrections, 1 superseded
test rewritten, 1 acceptance-driven design decision, 1 deferred discovery, 1 logged and not fixed.

## Issues Encountered

**The take-off's markup answered a question its text could not.** The legend label carries no
convention, and a text search for "both sides"/"per face" finds only architect notes about door
hardware. The estimator's own traced polylines — parallel strokes one wall thickness apart on
three separate sheets — are the data D-08 asked for. No golden quantity was consulted, and no
ratio was tried against a total.

**A blanket multiplier rule would have failed the acceptance that mandated it.** The same plan
document specifies both "append when ratio available and count above one" and "fires on exactly
four sheets" — mutually inconsistent on the real data (nine clean sheets have counts above one).
The real-bundle probe surfaced this before any code was written; Deviation 5 is the
reconciliation.

**The module-scoped real-bundle fixture keeps the cost bounded.** `test_fusion.py` now measures
all 16 prototype sheets plus the real room-mix resolution once (~2.5 min) and every fusion
assertion — registry routing, wall binding, the 13-sheet multiplier matrix — reads the same
measurement. Suite: 26m35s → ~30m20s.

## Known Stubs

None. **Deliberately absent, with named owners:** no elevation-area or linear binder is
registered (`23-14`, `23-15` register theirs — the registry and the arbitration are already
waiting for them), and no production caller declares `shared_area` yet (the declaration channel
is exercised synthetically; the first real declared sharing arrives with whichever plan binds a
finish over a slab).

## Threat Flags

None — no new network, auth, filesystem or schema surface. The take-off PDF was read only by a
scratchpad probe outside the repo (T-23-48 holds: `grep -rn "takeoff|Take off" src/` stays clean).

Registered mitigations, all delivered:

- **T-23-50 (double counting when a new binder emits a same-named item)** — supersession +
  one-area-one-item in the SAME commit as the binder; every suppression in `fusion_rejected`;
  synthetic case 10 and the real-Crow COUNT assertion pin it.
- **T-23-51 (a wrong wall height at high confidence because its source is not the default)** —
  per-drawing tag first with the AFF exclusion; any source outside {drawing, learned} flags with
  the source named; the armed 15-ft answer loses on all sixteen real sheets.
- **T-23-52 (an unverifiable human multiplier presented as confident)** — confidence downgraded
  above one, the source on every row, the units-not-doors sentence with the measured ratio.
- **T-23-53 (a leaking fill produces a fabricated linear-foot figure)** — the blind shape gate
  returns zero with the ratio named; the architectural discipline is deliberately kept.
- **T-23-54 (a suppressed duplicate vanishes without explanation)** — every suppression carries
  reason + survivor + preserved quantity in the rejected list.

## Commits

| Task | Commit | Description |
|---|---|---|
| 1 | `af1c7b1` | Billable perimeter, wall area, and a height read from the drawing itself |
| 2+3 | `857357d` | Wall binder through the SP-9 registry + one-area-one-item arbitration, in ONE change |
| 4 | `c6db659` | One coordinated fill-selector change + the honest multiplier |

## Requirement status

- **V4-MEAS-01 — COMPLETE.** "Room fills bind to takeoff line items for ceiling area (RCP basis)
  AND wall area (perimeter × height, AR basis)" — both halves now exist, on real PDFs, through
  one registry, with the honest outcomes (flagged zeros on leaking AR fills) the investigation
  predicted.
- **V4-MEAS-02 — advanced, not completed.** The multiplier half of the ~2× story is delivered
  exact (the flag fires on precisely the four sheets, the counts are never edited), but the
  requirement's clip half is still open behind **DEF-23-SP4**, and `docs/PIPELINE-GROUND-TRUTH.md`
  §14.2's correction is 23-16's.

## What this unblocks

- **23-14** registers its elevation-area binder in `BASIS_BINDERS` and inherits arbitration for
  free. It must not add a gate; the registry test will catch it if it tries.
- **23-15** registers `linear`, inherits `typical_detail` suppression, and owns DEF-23-13A (the
  `(t)`/`(ris)` abbreviation tags whose counts currently fall back to the manifest flagged).
- **23-16** corrects the record with committed evidence to cite: the ~2× flags are now in the
  suite, sheet-exact.

## Self-Check: PASSED

- `src/bobbytailor/deterministic/room_fill.py` — FOUND
- `src/bobbytailor/vision/fusion.py` — FOUND
- `src/bobbytailor/pipeline/takeoff_pipeline.py` — FOUND
- `tests/test_room_fill.py` / `tests/test_fusion.py` — FOUND
- commit `af1c7b1` (Task 1) — FOUND
- commit `857357d` (Tasks 2+3, binder + arbitration together) — FOUND
- commit `c6db659` (Task 4) — FOUND
- `git diff --stat human_inputs/ uploads/ reports/ docs/PIPELINE-GROUND-TRUTH.md` — EMPTY

---
phase: 23-measurement-engine-completion
plan: 15
subsystem: pipeline/calculator + pipeline/takeoff_pipeline + vision/fusion + deterministic/component_library + pipeline/aggregator
tags: [SP-7, linear-binder, phantom-kill, unit-guard, ambiguity-gate, canonical-naming, INV-04, INV-06, D-06, D-07, D-09, V4-MEAS-03, V4-MEAS-05, T-23-60, T-23-61, T-23-62, T-23-63]
status: complete

requires:
  - phase: 23-12
    provides: "extract_rail_runs / extract_linetype_runs / run_scale_fpp — the position-validated selectors this plan gives call sites, and the is_typical stamp"
  - phase: 23-13
    provides: "BASIS_BINDERS — the SP-9 registry the linear binder registers through; typical_detail_not_summed arbitration inherited for free"
  - phase: 23-14
    provides: "the dispatcher pattern (register + once-guard + backstop) the linear binder mirrors, and the 1810-passed baseline held green"
provides:
  - "calculator._apply_formula LF and SF branches guard on the INCOMING unit (_LENGTH_UNITS / _AREA_UNITS): a pipe diameter in inches can never again be stamped as linear feet; the detail-sheet callout guard covers guard_rail/hand_rail/striping/trench_drain"
  - "takeoff_pipeline._measure_linear_runs — both 23-12 selectors on every sheet UNGATED by sheet type; linetype runs at their own drawing's scale via run_scale_fpp, rail runs per rotation-aware callout cell; bundle keys linear_runs + sheet_linear_phrases + shx_labels"
  - "fusion._fuse_linear_runs registered under BASIS_BINDERS['linear'] — title-resolution naming, SHX → sheet-note → flag priority, the SP-7c ambiguity gate, one-viewport billing, typical never summed with main-plan; runs are groundable registry candidates (kind linear_run)"
  - "component_library._linear_phrases_from_notes — MATERIAL+HEAD linear phrases from a sheet's own notes (Gas Piping → linear/LF, source sheet_note, no model call)"
  - "aggregator.canonical_library_name — one canonical name FORM: a library-verbatim name is rewritten to the static map's form when the words match modulo spacing (Guardrail → Guard Rail), applied to the naming path AND the expected-items placeholders"
affects:
  - "23-16 (record) — the phantom kill and the linear binder are committed evidence for the doc correction"
  - "Phase 24 — naming Crow's rails among the 246 groundable p2 candidates is text-anchored Set-of-Mark scope; the binder and the flag contract are already waiting"

tech-stack:
  added: []
  patterns:
    - "a formula branch guards on the INCOMING UNIT: an item type never implies a unit, and the no-formula sentinel plus the existing downstream drop kills a phantom with no new gate"
    - "the phantom kill and the measurement route land in ONE commit, so the item is never simultaneously absent and wrong"
    - "a new measure basis REGISTERS in BASIS_BINDERS with a once-guard and a fuse_sheet backstop — the 23-14 dispatcher shape, no parallel frozenset"
    - "naming is text-anchored with a closed priority (drawing's own title → SHX annot → sheet's own note → flag) and an exactly-one gate; names are never round-robined and a glyph is never read"
    - "exactly ONE viewport is billed per linear object: a typical detail is never summed with a main plan, and two drawings of one object are never summed with each other"

key-files:
  created: []
  modified:
    - src/bobbytailor/pipeline/calculator.py
    - src/bobbytailor/pipeline/takeoff_pipeline.py
    - src/bobbytailor/vision/fusion.py
    - src/bobbytailor/deterministic/component_library.py
    - src/bobbytailor/pipeline/aggregator.py
    - tests/test_calculator_accuracy.py
    - tests/test_fusion.py
    - tests/test_component_library.py

key-decisions:
  - "canonical_library_name normalises the FORM of one item's name, never renames one item to another: blanket ITEM_NAME_MAP routing mangled 'Fiber Cement Panel' → 'Electrical Panels' and 'Tilt Up Wall' → 'Exterior Tilt Up Wall' (both caught by existing tests); the shipped rule rewrites only when the map's canonical form is the same words modulo spacing/separators/case"
  - "NO mask rects are passed to the run selectors: a false table detection on Bob's A3.0 reports a 'schedule' bbox covering the ENTIRE roof plan, and masking with it deletes every gas segment (measured: 14 runs → 0). The selectors' own defences are the ones 23-12 position-validated WITHOUT masks; masked viewports still never OWN a run's scale"
  - "the typical-detail reference is the sheet's COARSEST printed callout (largest ft/in — the main drawing; a detail is a blow-up), not the resolved page scale: Bob's A3.0 still resolves a detail's 1.0 ft/in page scale, which flagged the roof plan's own gas run as typical while passing the curb detail as main-plan — exactly inverted"
  - "title-based selection uses signature-free runs only and the phrase gate uses signature families only, so the same geometry found by both selectors can never be billed twice"
  - "_LINEAR_RUNS_PER_CLIP = 40, longest first — a bound on bundle/registry size (T-23-46 discipline), not a tuning knob; the measurable objects are the long runs"

requirements-completed: [V4-MEAS-03, V4-MEAS-05]

coverage:
  - id: T1
    description: "A pipe diameter printed in inches never becomes a length in linear feet, and a detail-sheet spec is never a quantity"
    requirement: V4-MEAS-05
    verification:
      - kind: unit
        ref: "tests/test_calculator_accuracy.py::test_a_pipe_diameter_in_inches_never_becomes_linear_feet + ::test_a_rail_diameter_measurement_produces_no_row + ::test_a_detail_sheet_dimension_is_a_spec_not_a_run"
        status: pass
      - kind: unit
        ref: "tests/test_calculator_accuracy.py::test_a_rail_length_in_linear_feet_still_gets_its_formula + ::test_pipe_run_and_lintel_run_calculators_are_unaffected (regressions)"
        status: pass
      - kind: integration
        ref: "tests/test_calculator_accuracy.py::test_no_rail_row_with_an_inch_raw_unit_survives_to_calculations_csv — the seven INV-06 phantom rows re-run through the calculator and the reporter's own CSV writer into a tmp run dir; filtering for rail rows with inch raw units yields NOTHING"
        status: pass
    human_judgment: false
  - id: T2
    description: "A linear-basis item harvested from a sheet's own notes gets its basis and unit with no model call, in one canonical name form"
    requirement: V4-MEAS-03
    verification:
      - kind: integration
        ref: "tests/test_component_library.py::test_bobs_roof_plan_yields_a_gas_piping_linear_entry (real PDF) + ::test_crow_rail_entries_are_unchanged_linear_lf (real PDF)"
        status: pass
      - kind: unit
        ref: "tests/test_component_library.py::test_a_gas_piping_note_classifies_itself_linear_lf + ::test_equipment_fragments_and_discharge_notes_are_not_head_nouns + ::test_a_library_verbatim_rail_name_produces_the_spaced_canonical_form"
        status: pass
    human_judgment: false
  - id: T3
    description: "Measured runs bind through the registry, flagged when the multiplier or the name is unknown, and never double count"
    requirement: V4-MEAS-05
    verification:
      - kind: unit
        ref: "tests/test_fusion.py::test_the_linear_basis_routes_through_the_registry_only + ::test_a_stair_rail_titled_run_binds_per_instance_and_flagged + ::test_a_typical_run_and_a_main_plan_run_for_one_object_do_not_sum + ::test_two_families_and_two_labels_flag_and_never_assign_a_name + ::test_an_shx_comment_annotation_names_the_family_it_overlaps + ::test_a_linear_run_is_a_groundable_candidate"
        status: pass
      - kind: integration
        ref: "tests/test_fusion.py::test_crow_detail_sheet_bundle_carries_linear_run_candidates + ::test_crow_emits_at_most_one_guard_rail_row_naming_one_viewport (real PDF)"
        status: pass
    human_judgment: false
  - id: T4
    description: "Bob's gas run reaches a line item inside its band, named from the sheet's own note"
    requirement: V4-MEAS-03
    verification:
      - kind: integration
        ref: "tests/test_fusion.py::test_bobs_gas_run_lands_in_its_band_named_from_the_sheets_own_note — 877.6 LF ∈ [840, 935] asserted as a BAND, name_source sheet_note, provenance geometry + ::test_bobs_sheet_note_phrase_is_harvested_onto_the_bundle"
        status: pass
    human_judgment: false

metrics:
  duration: ~1h45m
  completed: 2026-08-04
  tasks: 3
  commits: 2
  tests_added: 21
  suite: "1831 passed, 2 deselected (baseline 1810)"
---

# Phase 23 Plan 15: Linear Binder + Phantom Rail Kill Summary

**The 5.8-LF rail figure is dead at the unit, not by a name filter: both formula branches of
`_apply_formula` now guard on the incoming unit, so a 1 1/2" pipe O.D. returns inches with the
no-formula sentinel and all seven INV-06 phantom rows vanish through the drop that already
existed — landed in the SAME commit as the measurement route, so rails were never simultaneously
absent and wrong. Basis `linear` finally has a consumer: `_fuse_linear_runs` registers in the SP-9
registry, and Bob's gas main — measured 877.6 LF at its own drawing's printed 3/32" scale — reaches
a line item named `Gas Piping` from the sheet's own general note, with no model call anywhere in
the path. Rails ship the D-09 contract: a run titled after its own drawing binds per-instance with
`needs_review` and no unit count, a typical detail is never summed with a main plan, and where the
sheet's text cannot name a run the row flags instead of guessing.**

## Performance

- **Duration:** ~1h45m active (one 36-min full-suite gate + the standalone four-set gate)
- **Started:** 2026-08-04T05:37:51Z — **Completed:** 2026-08-04T07:20Z
- **Tasks:** 3 of 3 — 2 commits (Tasks 1+3 deliberately share one; see Deviations 1)
- **Files:** 0 created, 8 modified

## What shipped

### Task 1 — unit-aware formula branches + the widened detail guard (in `9a0a45d`)

`_LENGTH_UNITS` / `_AREA_UNITS` at module level; the LF branch (the exact INV-06 defect at the old
`calculator.py:1263-1266`) and the SF branch return `(value, unit, "no formula")` when the incoming
unit is not of their dimension. `_calculate_from_measurement` already drops no-formula rows, so the
seven saved phantom rows (five guard_rail + two hand_rail, every one a pipe O.D. in inches off
`page_0003.png`) disappear with no other change. The detail-sheet callout guard now covers
`guard_rail`, `hand_rail`, `striping`, `trench_drain` beside the five item types it had — a
dimension annotation on a DETAIL sheet is a specification, not a run. The pipe-run and lintel-run
calculators pass `"lf"` explicitly and are pinned unaffected.

### Task 2 — linear-phrase classification + one canonical name form (`339ebd5`)

`harvest_from_notes` gains the MATERIAL+HEAD rule: a closed material vocabulary (GAS, STORM,
SANITARY, SEWER, WATER, FUEL, IRRIGATION, STEEL, COPPER, PVC, HDPE) followed by a linear head noun,
with a follower guard that rejects a head noun modifying a further noun. Measured across all four
plan sets: **exactly one new entry** — Bob's `Gas Piping` (linear, LF, `sheet_note`) — and zero
false positives; `CONDUIT OR PIPE`, `EXHAUST DUCT`, the condensate discharge note and
`STORM WATER POLLUTION PREVENTION PLAN` are all pinned rejected.

`aggregator.canonical_library_name` closes SP-7a: the library-verbatim naming path and the
expected-items completeness placeholders both route through the ONE static map when the map's
canonical form is the same words modulo spacing — `Guardrail`/`Handrail` become the spaced forms
the map already produces, while genuinely different names stay verbatim (see Deviations 3).

### Task 3 — the linear binder, the ambiguity gate, the typical-detail rule (`9a0a45d`)

`_measure_linear_runs` runs both 23-12 selectors on every sheet, ungated by sheet type: linetype
runs whole-page (their four gates fired zero times across the 76 non-gas pages) with each run
resolved to its own drawing's callout scale through `run_scale_fpp` or flagged unmeasured; rail
runs inside rotation-aware callout cell clips at each callout's own scale, capped at the 40 longest
per clip. Every run is a groundable `LIN-n` registry candidate; the sheet's own note phrases and
SHX comment annotations ride the bundle as the naming context.

`_fuse_linear_runs` is reached ONLY through `BASIS_BINDERS["linear"]` (registered dispatcher +
fuse_sheet backstop, both converging on a once-guard — the 23-14 shape, no parallel frozenset).
Naming priority: the drawing's OWN title resolving to a linear object (library resolver, then the
one static map — `STAIR RAIL` → `Hand Rail`); for signature families an overlapping SHX annot, then
the sheet's own note phrase under the SP-7c gate (exactly one family AND exactly one label, else
the quantity ships flagged with a reason naming both counts — never round-robined). Exactly one
viewport is billed per object — main-plan preferred over typical, others named in the flag — and
the emitted `typical_detail` key hands the 23-13 arbitration its never-sum suppression for free.

Measured on the real PDFs, zero API:

| Result | Value |
|---|---|
| Bob's gas | **877.6 LF ∈ [840, 935]**, `Gas Piping`, `sheet_note`, confident |
| Bob's curb detail | `Curb & Gutter` 34.8 LF, per-instance, FLAGGED typical, count unknown |
| Crow p2 bundle | **246 groundable linear-run candidates** (was: no geometry at all) |
| Crow guard-rail rows | ≤ 1, and no confidently-wrong figure anywhere |

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest -q` | **1831 passed, 2 deselected** (baseline 1810; +21) |
| Four-set gate (`test_four_set_coverage`) | **14 passed**, standalone after the suite |
| Targeted files (fusion / pipeline / calculator / library / aggregator / open_runs) | 120 + 152 passed |
| Phantom direct-call | `_apply_formula('guard_rail', 1.5, 'in', …)` → `(1.5, 'in', 'no formula')`; `_calculate_from_measurement(...)` → `None` |
| Bob's gas band | 877.6 ∈ [840, 935] at the printed 10.667 ft/in |
| `git log -1 --stat 9a0a45d` | phantom kill (calculator.py) + measurement route (takeoff_pipeline.py, fusion.py) in ONE commit |
| `git diff --diff-filter=D HEAD~2 HEAD` | no deletions |
| `git diff --stat uploads/ human_inputs/ reports/ docs/PIPELINE-GROUND-TRUTH.md` | **EMPTY** |
| `ast.parse(..., feature_version=(3,9))` | py39 ok on every modified file |

**No paid command was run.** `pytest -m golden`, `accuracy_gate.sh`, `vision_only_benchmark.py`
and `golden_convergence.py` were not executed; `.env` was not read. Nothing asserts against Guard
Rail 420.35 / Hand Rail 438.80 (the multiplier is not printed — D-07/R4), and Bob's band is a band.

### Impact analysis (CLAUDE.md), run before editing

| Symbol | Risk | Note |
|---|---|---|
| `_calculate_from_measurement` | **CRITICAL** | 5 processes (run_project chain) |
| `_apply_formula` | **HIGH** | 6 direct callers, 4 processes |
| `aggregate_takeoff`, `_fuse_room_fills`, `build_registry` | **HIGH** | fuse/aggregate chains |
| `fuse_sheet`, `_deterministic_bundle`, `resolve_library_name`, `harvest_from_notes` | LOW | |

`gitnexus detect-changes` before committing read **HIGH** (10 files, 89 symbols, 14 processes).
**Those HIGH/CRITICAL results are hereby surfaced, as CLAUDE.md requires.** Mitigated, not
accepted: the formula guards are pinned by direct-call regressions on every explicit-`lf` caller;
every fusion/aggregator change is additive (new bundle keys, a new registry kind, one added ctx
key) with the canonicalisation constrained to formatting-equality; and the full 1831-test suite
plus the four-set gate were green on the exact tree both commits were cut from. The index was
refreshed with `npx gitnexus analyze` after the commits.

## Deviations from Plan

### 1. [Plan-mandated commit merge] Tasks 1 and 3 share one commit; one suite gate covered both commits

The plan's hard constraint — "the measurement route and the phantom kill land in the SAME commit"
— outranks one-commit-per-task, exactly as 23-13's arbitration constraint did: `9a0a45d` carries
calculator + pipeline + fusion, and Task 3's own acceptance requires it. Consequently the two
commits were cut back-to-back from ONE fully-gated tree (suite + four-set gate); the intermediate
Task-2-only state was verified by its targeted files (55 passed) rather than a second 36-minute
full run.

### 2. [Rule 1 — fixed at the measured cause] No mask rects to the run selectors

The plan said nothing about masks; the first wiring passed the bundle's mask-viewport rects and
Bob's gas went 14 runs → **0**, because a false table detection reports a "schedule" bbox covering
the ENTIRE A3.0 roof plan. The selectors ship without masks — the configuration 23-12
position-validated (four gates, zero false positives across 76 pages) — and masked viewports still
never OWN a run's scale in `run_scale_fpp`. The underlying schedule misdetection is pre-existing
and out of scope.

### 3. [Design decision, forced by two failing tests] Canonicalisation is formatting-equality only

The plan's literal "route library names through the SAME normalisation" as a blanket
ITEM_NAME_MAP pass renames distinct items: `Fiber Cement Panel` → `Electrical Panels` (the exact
mangling the legend-verbatim comment documents) and `Tilt Up Wall` → `Exterior Tilt Up Wall`
(caught by an existing completeness test). What SP-7a actually needs is one canonical name FORM —
the map's form wins only when it is the same words modulo spacing/separators/case. `Guardrail` /
`Handrail` converge; novel vocabulary stays verbatim. The plan's "two name pins updated" were not
needed — every existing pin already used the canonical form and passed unchanged.

### 4. [Rule 1 — fixed at the measured cause] The typical-flag reference is the coarsest printed callout

The 23-12 `is_typical` contract compares a run's callout scale to "the resolved page scale" — but
Bob's A3.0 still RESOLVES at a detail's 1.0 ft/in, which inverted the flag on the real sheet: the
roof plan's own gas run read "typical" while the curb detail passed as main-plan. The shipped
reference is the sheet's coarsest printed callout (largest ft/in = the main drawing; a detail is a
blow-up), falling back to the resolved scale only when no callout exists. A coarser inset (a
vicinity map) can only ADD flags, never remove one.

### 5. [Honest outcome, documented] Crow's rails surface as flagged blanks, not bound rows

No viewport title on the real A-401 sheet resolves to Guard Rail — the estimator's five marks live
in `ENLARGED RAMP PLAN` and `STAIR PLAN` (titles that name no object), and the `STAIR RAIL` detail
yields no chainable run at its own callout cell. Among the 246 candidates nothing deterministic
distinguishes the five rail runs from stair stringers and dock linework, so per flag-don't-guess
the binder emits NOTHING confidently wrong: `Guard Rail` / `Hand Rail` appear as
`expected-not-measured` flagged blanks from the library completeness path, and the at-most-one-row
acceptance holds. The phantom 5.8 LF is dead; naming the runs is exactly Phase 24's text-anchored
Set-of-Mark scope, and the binder plus the D-09 flag contract are already waiting for it (proven
by the synthetic stair-rail binding and by Bob's real curb detail, which does bind per-instance
flagged).

### 6. [Discovered honest row] Bob's gains a flagged Curb & Gutter per-instance row

`CURB DETAIL` title-resolves to the library's `Curb & Gutter`; 34.8 LF of detail linework ships
per-instance, FLAGGED typical with the count-unknown reason — the D-09 contract shape appearing on
a drawing set the plan never mentioned. Left in deliberately: it is a review row, not a confident
number.

### 7. [Scope boundary — logged, NOT fixed] The suite still rewrites three synthetic fixture PDFs

`tests/fixtures/synthetic/{dimensions,floorplan,symbols}_synthetic.pdf` came back modified after
the full-suite run (23-08 dev 6 … 23-14 dev 10). Reverted, never committed.

---

**Total deviations:** 1 plan-mandated commit merge, 2 fixed at their measured cause (Rule 1),
1 design decision forced by failing tests, 1 honest outcome documented, 1 discovered honest row,
1 pre-existing recurrence.

## Issues Encountered

**The resolved page scale is not a safe reference for anything on Bob's A3.0.** Even after the
23-02/23-07 parser fixes, `resolve_scale_v2` still lands on the vent-pipe detail's 1.0 ft/in for
the page while `run_scale_fpp` correctly resolves 10.667 for the gas runs — two answers on one
sheet. Every 23-15 measurement therefore rides per-run/per-callout scales; the page figure is used
for nothing but a last-resort typical reference.

**A giant false "schedule" viewport can silently delete a whole drawing's geometry.** Bob's A3.0
carries a table-detection bbox spanning the entire roof plan. Any new measurement path that
inherits the mask list uncritically loses everything under it — worth remembering for every future
selector call site.

## Known Stubs

None in the shipped paths. **Deliberately absent, with named owners:** no deterministic rail
naming on Crow (Phase 24, text-anchored labelling — Deviation 5); no instance-count source for
rails (the multiplier is not printed on the drawings; the row ships flagged per D-09); the
pre-existing schedule misdetection on Bob's A3.0 (out of scope, documented above).

## Threat Flags

None — no new network, auth, filesystem or schema surface. Registered mitigations, all delivered:

- **T-23-60 (a dimension in one unit published as a quantity in another)** — both formula branches
  guard on the incoming unit and return the no-formula sentinel the downstream gate already drops;
  the detail-sheet guard widened to the four missing item types; pinned by direct-call assertions
  and the calculations.csv filter test.
- **T-23-61 (a run named by a guess among several labels)** — the SP-7c gate binds only on exactly
  one family and exactly one label; otherwise flagged and unnamed, round-robin forbidden and
  pinned.
- **T-23-62 (the same rail counted from a typical detail and a main plan)** — one-viewport billing
  in the binder + the `typical_detail` key feeding the 23-13 arbitration; pinned by the no-sum
  test and the at-most-one-row assertion on the real sheet.
- **T-23-63 (a published quantity hiding an unknown instance count)** — the count-unknown case
  ships `needs_review` with a reason stating what was measured and what the sheet does not state;
  the flag landed with the binder, in the same commit.
- **T-23-64 (a run measured at a borrowed page scale)** — inherited from 23-12 and wired through:
  a run with no containing callout stays flagged and unmeasured, and the bundle's coverage note
  counts them.

## Commits

| Task | Commit | Description |
|---|---|---|
| 2 | `339ebd5` | Linear-phrase basis classification + one canonical name form |
| 1+3 | `9a0a45d` | Phantom rail LF killed at the unit + measured runs bound through the linear basis, in ONE change |

## Requirement status

- **V4-MEAS-03 — COMPLETE.** The elevation wall-area half landed in 23-14; the civil-linework-LF
  half lands here: Bob's gas main reaches a line item at 877.6 LF from linework on its roof plan,
  named from the sheet's own note, so a set with no floor plan still yields both quantity kinds.
- **V4-MEAS-05 — COMPLETE.** Rail/linework LF is measured FROM LINEWORK end-to-end: the selectors
  measure, the binder emits per-instance flagged rows wherever the drawing's own text names the
  object (synthetic stair rail; Bob's real curb detail), and the honest-failure path — a flagged
  blank, never a guessed or phantom number — is what Crow's rails show until Phase 24's labelling
  names their runs.

## What this unblocks

- **23-16 (record)** — the phantom kill, the band-verified gas binding and the flagged-blank rail
  contract are committed evidence for the ground-truth-doc corrections.
- **Phase 24** — 246 groundable `LIN-n` candidates on Crow p2 with a registry, a binder, an
  ambiguity gate and a flag contract already in place; labelling a run is now a naming problem
  only.

## Self-Check: PASSED

- `src/bobbytailor/pipeline/calculator.py` — FOUND
- `src/bobbytailor/pipeline/takeoff_pipeline.py` — FOUND
- `src/bobbytailor/vision/fusion.py` — FOUND
- `src/bobbytailor/deterministic/component_library.py` — FOUND
- `src/bobbytailor/pipeline/aggregator.py` — FOUND
- commit `339ebd5` (Task 2) — FOUND
- commit `9a0a45d` (Tasks 1+3, phantom kill + measurement route together) — FOUND
- `git diff --stat uploads/ human_inputs/ reports/ docs/PIPELINE-GROUND-TRUTH.md` — EMPTY

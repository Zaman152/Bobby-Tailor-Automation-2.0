---
phase: 23-measurement-engine-completion
plan: 08
subsystem: pipeline/takeoff_pipeline + vision/fusion + deterministic/room_tags
tags: [SP-10, room-mix-census, unit-multiplier, provenance, finish-tags, flagged-zero, D-10, D-03, INV-05]
status: complete

requires:
  - phase: 23-03
    provides: "the coverage_notes / item_coverage record the room-mix flags and the suppressed-code notes are written into"
  - phase: 23-05
    provides: "tag_pairing / finish_tags / room_tags — the pure extractors this plan wires; derive_room_mix's `pages` scope was left for this plan to fill"
  - phase: 23-07
    provides: "the offline suite baseline this plan holds green (1557 passed / 2 deselected)"
provides:
  - "room_tags.resolve_room_mix — the D-10 precedence as a pure function (census wins, manifest fills, disagreement flags, refusal falls back wholesale)"
  - "room_tags.abbreviation_target — a structural, unique-match-only, fail-closed abbreviation matcher (K SUITE B -> KING SUITE B)"
  - "room_tags.RoomMixResolution + UNIT_COUNT_SOURCE_CENSUS / _MANIFEST / _ASSUMED"
  - "TakeoffPipeline._resolve_room_mix replacing _manifest_room_mix, cached per document"
  - "TakeoffPipeline._unit_key_plan_pages — key-plan selection by the drawing's OWN printed title"
  - "bundle key material_tags"
  - "fusion._fuse_material_tags + MaterialTagLedger (run-level cap on distinct flagged codes)"
  - "fuse_sheet(room_mix_meta=..., material_tag_ledger=...)"
  - "component field unit_count_source, written into the formula string"
  - "_fuse_schedules: the finish kind emits 0 SF flagged, never 1 EA"
affects:
  - "23-16 (correct the record) — this plan corrected the pipeline docstring; docs/PIPELINE-GROUND-TRUTH.md:352 BLOCKER A is still 23-16's"
  - "23-14 (elevation facade measurement) — the material-tag rows are the flagged placeholders any measured elevation quantity must replace, not duplicate"
  - "any plan touching _fuse_room_fills — the component now carries unit_count_source and the formula string names it"

tech-stack:
  added: []
  patterns:
    - "select a sheet by the DRAWING TITLE bound to its own scale callout, not by a page-text search — the words KEY PLAN in a title block are not a key plan"
    - "a merged value carries the SOURCE it was merged from, into the formula string and onto the row; a count that cannot say where it came from is unauditable"
    - "flag a disagreement on the ROW THAT USES the number, not only in a run-level log a client never reads"
    - "an abbreviation match is structural (same word count, every word a prefix) and fails closed on ambiguity — an expansion dictionary would be our vocabulary, not the drawing's"
    - "cap a review queue by DISTINCT CODE across the run, not by row per sheet: the cap must be a run-level guarantee or it is no cap"
    - "a suppressed item is recorded as UNMEASURED, never omitted — omission is indistinguishable from zero"
    - "two paths that express the same idea emit ONE component contract (D-03), asserted field-by-field in a test"

key-files:
  created: []
  modified:
    - src/bobbytailor/deterministic/room_tags.py
    - src/bobbytailor/deterministic/tables.py
    - src/bobbytailor/pipeline/takeoff_pipeline.py
    - src/bobbytailor/vision/fusion.py
    - tests/test_room_tags.py
    - tests/test_takeoff_pipeline.py
    - tests/test_fusion.py

key-decisions:
  - "A unit key plan is identified by its own printed DRAWING TITLE matching `KEY PLAN`, read through extract_printed_scales — i.e. a title bound to a scale callout. Measured: Moxy pages 7 and 8 title seven drawings `LEVEL nn KEY PLAN`, and no other sheet in any of the four sets titles a drawing that way. Page index 3 prints the words KEY PLAN in its title block and is correctly NOT selected, because its drawings are building elevations. A page-text search would have taken it."
  - "The census is scoped to those pages only. The whole-document default refuses on Moxy (275 tags / 237 distinct / 18 duplicates) and that refusal is correct — 23-05 deliberately left the scoping to this plan because it is sheet classification, not tag reading."
  - "abbreviation_target was added (deviation 1) because without it the census supersedes nothing for KING SUITE A/B/C — the key plan tags them `K SUITE n` and the prototype sheet titles them `KING SUITE n`. The rule is prefix-per-word with identical word count and a unique match, and every use is flagged. It surfaced a real disagreement (K SUITE C: drawings 1, manifest 2) that exact matching would have hidden."
  - "The alias targets are the document's own prototype plan titles plus the manifest names, in that order of intent: a plans-only run with NO manifest still resolves the abbreviation, because both sides are the drawing's vocabulary."
  - "_fuse_material_tags emits one row per (code, sheet) and the ledger caps DISTINCT CODES across the run. Emitting one row per code per RUN would have made the plan's own page-18 acceptance criterion unsatisfiable (WC-7 also appears on page 16) and would have stranded seven of page 18's tag positions — the workspace needs THAT sheet's positions to place THAT sheet's shapes."
  - "A count with no stated source but a known value reports `manifest`, not blank: that is what a bare room_mix always was. `assumed` is reserved for the no-count case and is never published by the resolver — publishing an assumed count would be inventing a multiplier."
  - "human_inputs/moxy_knoxville.json was NOT edited. `git diff --stat human_inputs/` is empty and a test asserts the manifest value is used verbatim where the drawings are silent."

requirements-completed: []
requirements-advanced: [V4-MEAS-04]

coverage:
  - id: T1
    description: "The unit multiplier is read from the plans the drawings contain, not supplied by a human"
    requirement: V4-MEAS-04
    verification:
      - kind: integration
        ref: "tests/test_takeoff_pipeline.py::TestResolveRoomMix::test_moxy_key_plans_are_found_and_resolve_the_multiplier — real PDF, pages [7, 8] selected structurally, 4 of 4 multipliers sourced unit_tag_census"
        status: pass
      - kind: integration
        ref: "tests/test_room_tags.py::test_moxy_resolves_four_of_four_multipliers_from_the_drawings"
        status: pass
      - kind: unit
        ref: "tests/test_takeoff_pipeline.py::TestResolveRoomMix::test_a_key_plan_is_identified_by_its_own_printed_drawing_title (+ ::test_the_unrecoverable_multiplier_function_is_gone)"
        status: pass
    human_judgment: false
  - id: T2
    description: "Every unit count carries its source, and a count derived from the drawings outranks a manifest entry"
    requirement: V4-MEAS-04
    verification:
      - kind: unit
        ref: "tests/test_room_tags.py::test_the_census_wins_where_it_has_a_count + ::test_an_unknown_name_reports_assumed_rather_than_a_missing_source"
        status: pass
      - kind: unit
        ref: "tests/test_takeoff_pipeline.py::TestResolveRoomMix::test_the_census_supersedes_the_manifest_and_says_so"
        status: pass
    human_judgment: false
  - id: T3
    description: "Where the manifest and the drawings disagree, the disagreement is flagged, not silently resolved"
    requirement: V4-MEAS-04
    verification:
      - kind: integration
        ref: "tests/test_room_tags.py::test_moxy_has_a_real_disagreement_and_it_is_visible — real PDF, BUNK A drawings 1 vs manifest 2"
        status: pass
      - kind: unit
        ref: "tests/test_room_tags.py::test_a_disagreement_is_flagged_naming_both_numbers_and_both_sources"
        status: pass
      - kind: integration
        ref: "tests/test_room_tags.py::test_moxy_names_the_census_cannot_reach_are_flagged_as_human_supplied"
        status: pass
    human_judgment: false
  - id: T4
    description: "A census that cannot be trusted refuses wholesale and never degrades into a partial count"
    requirement: V4-MEAS-04
    verification:
      - kind: unit
        ref: "tests/test_takeoff_pipeline.py::TestResolveRoomMix::test_a_refused_census_falls_back_to_the_manifest_never_to_a_partial — stubbed duplicate-number refusal"
        status: pass
      - kind: unit
        ref: "tests/test_room_tags.py::test_a_refusal_falls_back_wholesale_and_never_to_a_partial_census"
        status: pass
    human_judgment: false
  - id: T5
    description: "A finish code called out on a sheet appears as a named, flagged, zero-quantity row carrying its tag positions"
    requirement: V4-MEAS-04
    verification:
      - kind: integration
        ref: "tests/test_fusion.py::test_moxy_elevation_sheet_emits_one_flagged_row_per_wall_covering_code — real PDF page 18, set {WC-6, WC-7}, positions inside the page rect"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py::test_a_called_out_finish_code_becomes_a_named_flagged_zero_row + ::test_the_row_carries_the_tag_positions_the_workspace_pre_places"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py::test_no_finish_row_ever_carries_a_quantity_above_zero"
        status: pass
    human_judgment: false
  - id: T6
    description: "No area is synthesized for a finish code, and a masked tag never becomes a row"
    requirement: V4-MEAS-04
    verification:
      - kind: unit
        ref: "tests/test_fusion.py::test_a_tag_inside_a_schedule_or_legend_mask_never_becomes_a_row — T-23-30"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py::test_two_sheets_sharing_a_code_group_under_one_ledger_entry + ::test_a_suppressed_code_is_recorded_as_unmeasured_and_not_as_zero — T-23-31"
        status: pass
    human_judgment: false
  - id: T7
    description: "A finish-schedule row never reports one each, and the change is scoped to the finish kind"
    requirement: V4-MEAS-04
    verification:
      - kind: unit
        ref: "tests/test_fusion.py::test_a_finish_schedule_row_never_reports_one_each + ::test_a_door_kind_and_a_keynote_kind_are_untouched"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py::test_the_two_finish_paths_emit_one_contract — D-03, field by field"
        status: pass
      - kind: integration
        ref: "tests/test_fusion.py::test_no_real_plan_set_produces_a_finish_schedule — all four uploads/ PDFs in one test"
        status: pass
    human_judgment: false

metrics:
  duration: ~2h05m
  completed: 2026-08-03
  tasks: 3
  commits: 3
  tests_added: 44
  suite: "1601 passed, 2 deselected (baseline 1557)"
---

# Phase 23 Plan 08: Room-Mix Census + Finish-Tag Rows Summary

**The multiplier the pipeline's own docstring called unrecoverable is now read off the drawings on
every run: 11 of Moxy's 15 unit types come from a blind census of two key plans, 4 of 4 golden
multipliers exact, each count stamped with its source — and the one place the drawings and the
human input disagree is now a flag on the row that uses the number rather than a silence. Separately,
ten wall-covering codes that produced NO ROW AT ALL now produce ten named, flagged, zero-quantity
rows seeded with their tag positions. No square foot was invented anywhere.**

## Performance

- **Duration:** ~2h05m
- **Tasks:** 3 of 3 (3 commits, one per task)
- **Files modified:** 7 (4 modules, 3 test files) — 1,489 insertions, 21 deletions, 0 files created

## The result, measured on the real PDFs (zero API)

### The multiplier, end to end through `TakeoffPipeline._resolve_room_mix`

```
key plan pages: [7, 8]          <- selected from the printed drawing titles alone
resolve 22.3s   counts=40  flags=8  refused=False

   qq a           90   unit_tag_census        king suite b   2    unit_tag_census
   king a         26   unit_tag_census        king suite c   1    unit_tag_census
   k suite b      2    unit_tag_census        bunk a         1    unit_tag_census
   bunk b         1    unit_tag_census        acc king tub   3    manifest
```

Four of four golden multipliers, sourced from the drawings, derived before any comparison was made.
Eleven of the manifest's fifteen unit types are now drawing-derived; the remaining four (the ADA/ACC
prototypes, which carry no matching key-plan tag) stay manifest-sourced **and say so on their rows**.

Two of the eight flags are disagreements with the estimator's own file:

| Name | Drawings | `human_inputs/moxy_knoxville.json` | Outcome |
|---|---|---|---|
| `BUNK A` | 1 | 2 | census published, **flagged**, manifest not edited |
| `KING SUITE C` | 1 | 2 | census published, **flagged**, manifest not edited |

The other six flags say a count is *not* derived from the drawings, or record an abbreviation match.
**No corrected total is asserted anywhere** — per the phase's never-tune-to-golden rule, correcting
these counts will legitimately move Gyp Ceiling *away* from golden and that is fine.

### Key-plan selection is structural, and it discriminates

```
p3   titles=['BUILDING ELEVATION SOUTH SUMMIT HILL DR', ...]   -> NOT a key plan
p7   titles=['ID-001 LEVEL 01 KEY PLAN', ... x4]               -> key plan
p8   titles=['ID-002 LEVEL 05 KEY PLAN', ... x3]               -> key plan
p9   titles=['ID-100 LEVEL 1 LOBBY AR PLAN', ...]              -> NOT a key plan
```

Moxy page 3 prints the words `KEY PLAN` in its title block. A page-text search selects it; the
drawing-title test does not, which is the whole reason the test is the drawing title.

### The finish codes, on the real elevation sheet

`_deterministic_bundle(page 18)` → `material_tags: 38`, WC set `{WC-6, WC-7}` — **exactly the
estimator's own Legend box** (INV-05 §2 Key A) — fusing to ten flagged rows:

```
WC-7 (7 tags)  WD-5 (8)  WD-3 (5)  PT-6 (2)  WC-6 (5)
WD-6 (1)       WD-4 (6)  PT-5 (1)  PT-4 (2)  ST-2 (1)      every quantity: 0
```

Each row carries `tag_positions_pt` — point rectangles inside the page, asserted — so the reports
workspace can pre-place the measurement shapes. That is the point: a flagged named row is a task a
human closes in seconds, and an absent row is invisible.

## What shipped

**`room_tags.resolve_room_mix` — the D-10 precedence, as a pure function.** The in-plan census wins
wherever it has a count; the manifest fills only names the drawings never state; where both carry a
count and they differ the census value is published *and* a flag names both numbers and both sources;
where the census refuses, the manifest is used **wholesale** with the refusal quoted. A partial census
is unreachable by construction (T-23-18) — a wrong multiplier is not one wrong row, it scales Gyp
Ceiling, Gyp Wall, Guestroom-Wall Covering and Doors at once.

**`room_tags.abbreviation_target` — structural, unique-match-only, fail-closed.** A key plan tags
`K SUITE B` and the prototype sheet titles the same unit `KING SUITE B`. The rule is: same word count,
every word of the short name a prefix of the corresponding word of the long one, and exactly one
candidate. It cannot merge `king a` with `king b`, cannot reach `ada king ris` from `ada (ris)`, and
returns an explicit *ambiguous* signal instead of picking when two full names both admit the
abbreviation. Nothing in it knows that `K` means `KING`; an expansion dictionary would be our
vocabulary rather than the drawing's.

**`TakeoffPipeline._resolve_room_mix` replaced `_manifest_room_mix`, docstring and all.** The
docstring that asserted the mix "is routinely not in the drawing set at all … so no reading of the
plan can recover it" is gone; its successor states the evidence — 214 tags, 214 distinct numbers,
4 of 4 — and points at INV-05 §2 Key B and at 23-16 for the ground-truth document. The resolution is
computed **once per document** (22 s: selection reads every sheet's drawing titles) and cached.

**Every count now carries `unit_count_source`** into the row and into the formula string
(`… × 90 units (unit count source: unit_tag_census)`), which is threat T-23-32: a count that silently
switches provenance between runs is unauditable. Any disagreement note rides on the row that *uses*
the number, so a client sees it where it matters.

**`_fuse_material_tags` reports a printed callout and cannot report an area.** Quantity zero, unit SF,
`provenance="text_layer"` (the code is printed, not guessed), low confidence, `needs_review`, a reason
naming the code, the tag count and the sheet, and the tag positions. `MaterialTagLedger` caps how many
**distinct codes** may ever open a review row across a run (T-23-31), and a suppressed code leaves a
coverage note saying it is *unmeasured, not zero* — the one failure mode this whole phase exists to
abolish. **There is no code path from this function to a non-zero quantity, and a test asserts it.**

**A finish-schedule row is a type declaration.** `_fuse_schedules` emitted `1 EA` for every row, so a
parsed finish schedule would have landed `WC-1` as one each — a fabricated unit on a fabricated
number, rendered as a completed line item. The finish kind now emits the *same shape* as the
material-tag path (0 SF, flagged, room tag in the reason, `FINISH-` candidate id,
`tag_positions_pt`), and a test compares the two contracts field by field (D-03). Door and keynote
kinds are byte-identical to before, asserted.

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest -q` | **1601 passed, 2 deselected** (baseline 1557) |
| Four-set gate `tests/test_four_set_coverage.py` | green, unchanged (inside the full run) |
| Plan-scope files (`test_room_tags` / `test_takeoff_pipeline` / `test_fusion`) | **183 passed** (38 / 79 / 66) |
| Moxy key-plan selection, real PDF | `[7, 8]` — p3's title-block "KEY PLAN" correctly rejected |
| Moxy resolved mix, real PDF | 4 of 4 multipliers, source `unit_tag_census`; 8 flags; 2 real disagreements |
| Moxy page 18 bundle, real PDF | 38 material tags, WC set `{WC-6, WC-7}` = the estimator's legend |
| Moxy page 18 fused rows | 10 flagged rows, **every quantity 0**, every `tag_positions_pt` inside the page rect |
| `finish` schedule kind on all four real sets | **zero**, re-verified this run (Moxy door / Crow door / Bob's door+keynote / Chelsea none) |
| `git diff --stat human_inputs/` | **EMPTY** |
| `ast.parse(..., feature_version=(3,9))` on all four modules | `py39 ok` |
| `python3 -c "... assert not hasattr(T,'_manifest_room_mix') ..."` | prints `replaced` |
| `gitnexus detect-changes` | run before each commit |

**No paid command was run.** `pytest -m golden`, `scripts/accuracy_gate.sh`,
`scripts/vision_only_benchmark.py` and `scripts/golden_convergence.py` were not executed; `.env` was
not read. Every number above came from a free offline probe or the offline suite.

### Impact analysis (CLAUDE.md), run before editing

| Symbol | Risk | Direct callers | Processes |
|---|---|---|---|
| `_manifest_room_mix` | LOW | 1 (`_run_sheet_vector`) | 2 |
| `_deterministic_bundle` | LOW | 1 (`_run_sheet_vector`) | 2 |
| `fuse_sheet` | LOW | 1 | 2 |
| `_fuse_schedules` | **HIGH** | 1 | 3, across 2 modules |

**`_fuse_schedules` reported HIGH and is flagged here as CLAUDE.md requires.** The change was made
anyway, deliberately and narrowly: it is gated on `kind == "finish"`, a kind that fires on **zero of
the four real plan sets** (re-verified this run), so the real blast radius is the synthetic fixture in
`tests/test_tables.py` plus the new tests. Door and keynote behaviour is pinned unchanged by
`test_a_door_kind_and_a_keynote_kind_are_untouched`, and the whole suite is green.

## Deviations from Plan

### 1. [Rule 2 — missing critical functionality] The census supersedes nothing without an abbreviation match

- **Found during:** Task 1, comparing the census keys with the prototype plan titles.
- **Issue:** the plan's precedence is "the census WINS where it has a count **for that name**", and it
  is silent on what happens when the two sides print the same unit under different names. Measured:
  the key plans tag `K SUITE A/B/C` and the prototype sheets title those exact units
  `KING SUITE A/B/C`. Under exact-name matching the census count for a suite is published under a key
  nothing looks up, the manifest's value is used instead, and the whole point — that a number the
  drawing contains must never require a human — silently fails for three unit types.
- **Fix:** `abbreviation_target`, a structural prefix-per-word matcher with identical word count and a
  unique-match requirement, matching against the document's own **prototype plan titles** first (so a
  plans-only run with no manifest resolves it too) and the manifest names second. Every use is
  flagged, ambiguity is reported rather than resolved, and a test pins each failure mode.
- **Why it earns its place:** it surfaced a disagreement exact matching would have buried —
  `K SUITE C`: drawings 1, manifest 2. Flag fired, manifest untouched.
- **Commit:** `10ac6cb`

### 2. [Rule 1 — the plan's two acceptance criteria were mutually exclusive] One row per (code, sheet)

- **Found during:** Task 2, writing the page-18 assertion.
- **Issue:** the plan asks for "one row per distinct wall-covering code on **that sheet**" for page 18
  *and* for "two sheets carrying the same code emit a grouped result … rather than one row per sheet".
  `WC-7` appears on page 16 **and** page 18. Under one-row-per-code-per-run, page 18 emits only
  `WC-6` and the first criterion fails.
- **Fix:** one row per **(code, sheet)**, with `MaterialTagLedger` capping the number of **distinct
  codes** that may ever open a review row across the run. Grouping is by code — that is what the cap
  counts — and the ledger records every sheet a code appeared on.
- **Why this is also the better product:** `WC-7` has 1 tag on page 16 and 7 on page 18. A single row
  carrying page 16's lone position would leave seven of page 18's shapes unplaced in the workspace,
  which is the opposite of the flagged row's purpose.
- **Commit:** `373c1bd`

### 3. [Decision] `assumed` is a consumer's answer, never a published count

The must-have names three sources. The resolver publishes only two: a count is `unit_tag_census` or
`manifest`. `assumed` is what `_fuse_room_fills` reports when it finds **no** entry — the measured
prototype stands for one unit and the row already says so. Publishing an assumed count from the
resolver would be inventing a multiplier, which is the failure the census exists to remove.

### 4. [Decision] A bare `room_mix` with no meta reports `manifest`

A caller passing `room_mix` without `room_mix_meta` (every pre-existing call site and test) gets
`unit_count_source: "manifest"`, because that is precisely what a bare room mix always was — the
estimator's declaration. The alternative, a blank source, would defeat T-23-32 on exactly the path
that needs it most.

### 5. [Scope boundary — logged, NOT fixed] The four-set finish-schedule guard costs ~5 minutes

`test_no_real_plan_set_produces_a_finish_schedule` runs `extract_schedules` over all four real PDFs
(83 pages of `page.find_tables()`) and takes **315 s** on its own; the full suite moved from ~10 min
to **25m31s**. The plan requires the guard across all four sets in one test and it is genuinely
load-bearing — it is the only thing that will tell us the day the dead `finish` vocabulary starts
firing. Recorded here rather than trimmed, because trimming it to Moxy alone would be a runtime
optimisation bought with coverage. A future plan may want a session-scoped cached whole-document
schedule scan shared with `test_tables`.

### 6. [Scope boundary — logged, NOT fixed] Running the suite rewrites three synthetic fixture PDFs

`tests/fixtures/synthetic/{dimensions,floorplan,symbols}_synthetic.pdf` come back modified after any
full-suite run (regenerated with fresh PDF timestamps). Pre-existing, unrelated to this plan, and
reverted rather than committed. Not fixed here.

---

**Total deviations:** 2 auto-fixed (1× Rule 1, 1× Rule 2), 2 decisions recorded, 2 logged and not
fixed.

## Issues Encountered

**The room-mix resolution costs 22 s per document.** Selecting the key plans reads every sheet's
printed drawing titles (0.4 s over 40 pages), the census itself reads two sheets with masks (5.5 s),
and collecting the prototype plan titles for the abbreviation targets reads all 40 pages again
(15.7 s). It is computed once and cached per `pdf_path`; a per-sheet call would have paid it forty
times, and a test asserts the document is scanned exactly once.

**The census key is the drawing's name, not the estimator's.** `counts` is therefore a LOOKUP TABLE
keyed by every name a count is known by — `k suite b` and `king suite b` both resolve to 2 — and
summing `counts.values()` is meaningless. Stated in the dataclass docstring because the shape invites
the mistake.

## Known Stubs

None. Every module is exercised against the real Moxy PDF, no threshold moved without a test that
fails when it does, and no value on any path in this plan can become a non-zero quantity without a
human measurement.

**What is deliberately still zero:** WC-1…WC-10 have no area, and must not be given one. INV-05 §3
seeded a flood fill at every WC tag and every fill leaked to the clip edge at four to ten times the
estimator's figure, because an elevation's wall face is bounded above and below and open laterally —
it is not a closed ink region. The 7,432.05 SF those legends sum to appears in **no module and no
test in this plan**. The rows are flagged placeholders for the human measure workspace, and 23-14
must replace them rather than duplicate them.

## Threat Flags

None — no new network, auth, filesystem or schema surface. No new file is read or written; the PDF
the project was already reading is read on two more sheets.

Registered mitigations, all delivered:

- **T-23-29 (a crafted key plan inflating a derived unit count)** — the room-number uniqueness gate
  fails closed (23-05), the manifest is retained as a cross-check, and every disagreement is flagged
  with both values named. Pinned by `test_a_refused_census_falls_back_to_the_manifest_never_to_a_partial`
  and `test_a_disagreement_is_flagged_naming_both_numbers_and_both_sources`.
- **T-23-30 (a fabricated wall-covering code creating a phantom review row)** — the schedule,
  title-block and legend masks are supplied by `_deterministic_bundle` and are mandatory; the emitted
  row carries quantity zero, so a false positive costs a review and can never cost a wrong number.
  Pinned by `test_a_tag_inside_a_schedule_or_legend_mask_never_becomes_a_row` and
  `test_no_finish_row_ever_carries_a_quantity_above_zero`.
- **T-23-31 (flooding the review queue)** — `MaterialTagLedger` caps distinct codes at the RUN level,
  and a suppressed code is recorded as unmeasured rather than dropped. Pinned by
  `test_two_sheets_sharing_a_code_group_under_one_ledger_entry` and
  `test_a_suppressed_code_is_recorded_as_unmeasured_and_not_as_zero`.
- **T-23-32 (a count silently switching provenance between runs)** — `unit_count_source` on every row
  and in every formula string; `sources` is never partial. Pinned by
  `test_an_unknown_name_reports_assumed_rather_than_a_missing_source` and the real-PDF source
  assertions.

## Commits

| Task | Commit | Description |
|---|---|---|
| 1 | `10ac6cb` | The unit multiplier comes from the drawings, and disagreement flags |
| 2 | `373c1bd` | A called-out finish code becomes a named flagged row, never an area |
| 3 | `4ce5e5c` | A finish-schedule row is a type declaration, not one each |

## Requirement status

`V4-MEAS-04` is **advanced, not completed** — left unchecked in `REQUIREMENTS.md`, as 23-02 … 23-05
did with theirs.

The requirement reads *"Finish-schedule → room binding (WC-1…WC-10 assigned to the rooms carrying
those finishes)"*. The wiring this plan owed is delivered — the codes now reach a report row — but
the sentence still cannot be ticked:

1. There is **no finish schedule** in the input and the binding as written cannot be built. The
   premise is disproved; 23-16 owns correcting the record.
2. WC-1…WC-10 have **no area**. The rows are honest flagged zeros, not assignments.

Ticking the box would claim a client-visible guarantee no client can see.

## What this unblocks

- **23-14** inherits ten named flagged placeholders on the elevation sheets. Any measured elevation
  quantity must *replace* the matching flagged row, not sit beside it.
- **23-16** can cite this plan's real-PDF assertions when correcting `docs/PIPELINE-GROUND-TRUTH.md:352`
  "BLOCKER A"; the pipeline half of D-01 is done.
- **The Moxy path has one less human input.** Eleven of fifteen unit types are drawing-derived, and
  the four that are not now say so on their own rows.

**The standing caution applies.** Recovering the multiplier does not make Moxy's numbers correct — it
removes the largest human input and makes two wrong human counts visible. Correcting
`human_inputs/moxy_knoxville.json` is out of scope for this phase, and the corrected counts will move
Gyp Ceiling *away* from golden. That is the phase working as intended.

## Self-Check: PASSED

- `src/bobbytailor/deterministic/room_tags.py` — FOUND
- `src/bobbytailor/deterministic/tables.py` — FOUND
- `src/bobbytailor/pipeline/takeoff_pipeline.py` — FOUND
- `src/bobbytailor/vision/fusion.py` — FOUND
- `tests/test_room_tags.py` — FOUND
- `tests/test_takeoff_pipeline.py` — FOUND
- `tests/test_fusion.py` — FOUND
- commit `10ac6cb` (Task 1) — FOUND
- commit `373c1bd` (Task 2) — FOUND
- commit `4ce5e5c` (Task 3) — FOUND
- `git diff --stat human_inputs/` — EMPTY
</content>
</invoke>

---
phase: 23-measurement-engine-completion
plan: 11
subsystem: deterministic/room_fill
tags: [SP-4, V4-MEAS-02, extent-cross-check, clip, INV-02, D-01, D-07]
status: complete
closed_early: "Task 3 of 4, by orchestrator decision. Tasks 1, 2 and 4 (the geometric clip cell, SP-4) are NOT done and carry forward under DEF-23-SP4."

requires:
  - phase: 23-07
    provides: "the page-space clip discipline _fill_clip_for_title follows — and, as this plan discovered, the change that already removed INV-02 §5's strip collapse"
  - phase: 23-09
    provides: "the sixteen-sheet RCP area baseline this plan holds byte-identical, and the flag-append discipline cross_check_extent inherits"
provides:
  - "room_fill.printed_extent_bound — a drawing's OWN printed overall extent in SF, harvested from the architectural sibling of the same plan name"
  - "room_fill.cross_check_extent + EXTENT_TOLERANCE — a scale-free, building-type-free RATIO replacing the 900 SF guest-room plausibility threshold"
  - "RoomFillResult.bound_sf and .extent_ratio, serialised for the export"
  - "TakeoffPipeline._fill_clip_for_title — ONE definition of a drawing's scale and clip"
  - "measured falsification of the plan's own clip-partition rule (see Deviations)"
affects:
  - "23-13 — a wall binder can now read extent_ratio to decide whether a fill is one unit before billing its perimeter"
  - "23-16 — the superseded ~2x story is corrected in code; the doc correction is still owed"

tech-stack:
  added: []
  patterns:
    - "express a plausibility bound as a RATIO against the drawing's own printed statement of its size, never as a quantity in the unit being measured"
    - "a check that cannot run must say so — an absent bound is NEEDS REVIEW carrying the measurement, never a dropped row"
    - "when a plan's proposed geometric rule is falsified by the fixtures, the measurement wins and the plan stops; it is not widened until the numbers agree"

key-files:
  created: []
  modified:
    - src/bobbytailor/deterministic/room_fill.py
    - src/bobbytailor/pipeline/takeoff_pipeline.py
    - tests/test_room_fill.py

key-decisions:
  - "The extent harvest reads the ARCHITECTURAL sibling of the same plan name, not the union of every sibling and not the drawing's own clip. The plan proposed the union; measured, the union turns ID-415 from 'no bound' (correct) into 9'-0\" x 1'-3\" = 11.2 SF, a bound 25x too small that reports a good 284.3 SF measurement as a 25x overrun."
  - "EXTENT_TOLERANCE = 1.25 is read off the distribution in INV-02 §4 (thirteen sheets 0.976-1.073, a two-plan leak ~2.0), not fitted to any total. It is dimensionless, so the same number governs a 250 SF guest room and a 12,000 SF ballroom — pinned by a test that scales both sides by fifty."
  - "flag_implausible_unit is DELETED rather than repurposed. Its docstring asserted a story three probes falsified; the correction lives in cross_check_extent, where it is read by whoever next asks why the check exists."
  - "Tasks 1, 2 and 4 (the geometric clip cell) are STOPPED, not shipped partially. The plan's stated partition rule is falsified by the fixtures and no variant reaches either the plan's own 2% no-regression bar or the executor's byte-identical bar. Shipping the helpers without the rewire would be untested dead code with invented semantics."
  - "The plan is CLOSED on Task 3 by orchestrator decision rather than re-scoped or retried. SP-4 is blocked behind a DOMAIN question — what a dimension-string corridor should contribute to a room's area — whose answer lives in the take-off documents, not in the plans and not in our judgement. Logged as DEF-23-SP4."
  - "The sixteen pinned RCP areas are LEFT EXACTLY AS THEY ARE. They remain a valid regression guard for the CURRENT clip; they are not a specification a new clip can be measured against, because 14% of one of them is annotation."

requirements-completed: []
requirements-advanced: [V4-MEAS-02]

coverage:
  - id: T1
    description: "A measured area is cross-checked against the drawing's own printed overall dimensions"
    requirement: V4-MEAS-02
    verification:
      - kind: integration
        ref: "tests/test_room_fill.py::test_the_printed_extent_bound_is_the_drawings_own_statement_of_its_size — all sixteen real sheets, reproduces INV-02 §4 sheet for sheet"
        status: pass
      - kind: integration
        ref: "tests/test_room_fill.py::test_thirteen_prototype_sheets_measure_their_own_printed_extent — thirteen ratios inside [0.9, 1.15], none flagged"
        status: pass
      - kind: unit
        ref: "tests/test_room_fill.py::test_the_measured_area_is_checked_against_the_drawings_own_printed_extent + ::test_a_fill_of_twice_its_printed_extent_is_flagged_never_halved"
        status: pass
    human_judgment: false
  - id: T2
    description: "The check flags and never filters — an absent bound cannot drop a measurement"
    requirement: V4-MEAS-02
    verification:
      - kind: integration
        ref: "tests/test_room_fill.py::test_a_sheet_with_no_printed_extent_is_flagged_and_still_reports_its_area[31,36] — ID-415 and ID-420"
        status: pass
      - kind: integration
        ref: "tests/test_room_fill.py::test_a_partial_printed_extent_flags_the_row_rather_than_the_measurement[26] — ID-410's bound is wrong and its area is untouched"
        status: pass
      - kind: unit
        ref: "tests/test_room_fill.py::test_no_printed_extent_flags_and_never_drops_the_measurement"
        status: pass
    human_judgment: false
  - id: T3
    description: "The guest-room-sized plausibility constant is gone and cannot come back"
    requirement: V4-MEAS-02
    verification:
      - kind: unit
        ref: "tests/test_room_fill.py::test_the_guest_room_sized_plausibility_constant_is_gone — asserts the attribute's absence AND greps room_fill for any new *_SF module constant"
        status: pass
      - kind: unit
        ref: "tests/test_room_fill.py::test_the_plausibility_bound_is_a_ratio_and_not_a_size_in_square_feet — scaling both sides by fifty changes no verdict"
        status: pass
    human_judgment: false
  - id: T4
    description: "The geometric viewport-bounded clip cell (SP-4)"
    requirement: V4-MEAS-02
    verification:
      - kind: integration
        ref: "NOT DONE — four prototype variants measured against all sixteen real sheets; best reproduces 4 of 16. Carried forward as DEF-23-SP4. See Deviations 2."
        status: deferred
    human_judgment: true

metrics:
  duration: ~4h
  completed: 2026-08-04
  tasks: 1 of 4 (closed early by orchestrator decision)
  commits: 1
  tests_added: 9
  suite: "1692 passed, 2 deselected (baseline 1683)"
---

# Phase 23 Plan 11: Printed-Extent Cross-Check (V4-MEAS-02) Summary

**The 900 SF "largest plausible guest unit" threshold is gone, replaced by a dimensionless ratio
against the drawing's OWN printed overall dimensions — reproducing INV-02 §4 sheet for sheet on all
sixteen real prototypes, with thirteen ratios inside 0.976-1.073 and the two sheets that print no
dimension pair flagged while still reporting their area. All sixteen pinned RCP areas are
byte-identical. The geometric clip cell is NOT DONE: the plan's own partition rule is falsified by
the fixtures, and the reason is a measurement, not an opinion.**

**The plan is closed on Task 3 alone, by orchestrator decision.** That is deliberate and it is the
right call: Task 3 delivers the contract 23-CONTEXT actually mandated — no guestroom-sized threshold
— while the clip was always labelled a ROBUSTNESS fix rather than a bug fix, because INV-02's three
probes had already exonerated it. SP-4 is blocked behind a question that is not ours to answer, and
it is logged as **DEF-23-SP4**.

## Performance

- **Duration:** ~4h (roughly half of it in read-only probes against the real PDFs, zero API)
- **Tasks:** 1 of 4 (Task 3). Tasks 1, 2 and 4 not done — see Deviations 2 and DEF-23-SP4.
- **Files:** 0 created, 3 modified

## What shipped

### `printed_extent_bound` — the drawing's own statement of its size

`max(printed horizontal dimension) x max(printed vertical dimension)`, harvested with the same
`dimensions.extract_dimension_samples` the scale solver already uses, from the **architectural
sibling of the same plan name**. A reflected-ceiling drawing carries no dimension of its own; on this
drawing set the overall dimensions are printed on the AR plan and nowhere else, and the falsifying
probe in INV-02 relied on exactly that.

The harvest runs **once per sheet**, not once per drawing: it walks every segment on the page, and a
Moxy prototype sheet carries five drawings.

Reproduced against the real PDF, before any golden value was read:

| page | plan | maxH ft | maxV ft | bound SF | RCP fill | ratio |
|---|---|---|---|---|---|---|
| 23 | KING A | 10.86 | 20.59 | 223.7 | 229.4 | 1.025 |
| 24 | KING B | 10.29 | 21.34 | 219.7 | 235.5 | 1.072 |
| 25 | KING C | 10.29 | 20.84 | 214.5 | 217.6 | 1.014 |
| 26 | KING SUITE A | 11.93 | 12.26 | 146.2 | 362.5 | **2.479** |
| 27 | KING SUITE B | 17.00 | 20.59 | 350.1 | 341.7 | 0.976 |
| 28 | KING SUITE C | 17.01 | 26.76 | 455.2 | 458.3 | **1.007** |
| 29 | QQ A | 10.29 | 24.68 | 254.0 | 272.6 | 1.073 |
| 30 | QQ B | 12.62 | 24.68 | 311.5 | 309.5 | 0.994 |
| 31 | QQ C | — | — | **None** | 284.3 | flagged |
| 32 | BUNK A | 17.01 | 26.76 | 455.2 | 454.7 | **0.999** |
| 33 | BUNK B | 10.29 | 26.76 | 275.4 | 274.6 | 0.997 |
| 34 | ADA KING RIS | 17.01 | 20.59 | 350.3 | 347.2 | 0.991 |
| 35 | ACC KING TUB | 17.01 | 20.59 | 350.3 | 347.7 | 0.993 |
| 36 | ACC QQ RIS | — | — | **None** | 451.1 | flagged |
| 37 | ACC QQ TUB | 17.01 | 26.76 | 455.2 | 463.0 | 1.017 |
| 38 | ACC BUNK | 17.01 | 26.76 | 455.2 | 458.5 | 1.007 |

**ID-412 and ID-416 — the two sheets `docs/PIPELINE-GROUND-TRUTH.md` §14.2 accuses the clip of
doubling — are among the tightest fits in the whole set, at 1.007 and 0.999.** The engine measured
those guestrooms correctly; the ~2x arrives one layer later, from a room-mix multiplier. That is now
a committed assertion rather than a paragraph in an investigation.

### `cross_check_extent` — a ratio, and a flag

`EXTENT_TOLERANCE = 1.25`. Read off the **distribution**, not fitted to a total: thirteen honest
sheets land in 0.976-1.073, a genuine two-plan leak reads ~2.0, and ID-410's partial-dimension bound
failure reads 2.479. The constant is dimensionless, so the same number governs a guest room and a
ballroom — pinned by a test that multiplies **both sides by fifty** and asserts no verdict changes.

It is a **FLAG, never a FILTER**. No printed dimension pair means NEEDS REVIEW carrying the measured
area, because two of the sixteen sheets print none and one produced a bound 2.5x too small; a
bound-derived rejection of a good fill would be worse than the bug it is meant to catch (INV-02 risk
2). ID-410 demonstrates the case in the suite: the row is flagged, and `area_sf` is still exactly
362.5.

### The guest-room-shaped constant is deleted, and cannot come back

`TakeoffPipeline._MAX_UNIT_SF = 900.0` and `room_fill.flag_implausible_unit` are both gone. The
constant was wrong twice over: it was a **size in square feet**, so it is right for a guest room and
wrong for a lobby; and it sat on the **wrong side of the room-mix multiplication**, so it saw 458.3
SF and passed it while the 916.6 SF that was actually wrong was produced later, in fusion, where no
guard ever looked (INV-02 §5).

`test_the_guest_room_sized_plausibility_constant_is_gone` asserts the absence **and greps
`room_fill.py` for any new module-level `*_SF` constant**, so the same shape cannot be reintroduced
under a new name.

The superseded docstring — which asserted that a clip overlapping the opposite-hand plan was why
ID-412 read 458 SF — is corrected in `cross_check_extent`, with the three probes that falsified it
named (D-01).

### `_fill_clip_for_title` — one definition

Extracted because the bound is now harvested from one rectangle and the area measured in another; a
second copy of "which scale is this drawing's, and what rectangle is this drawing" would let the two
drift apart silently (D-03).

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest -q` | **1692 passed, 2 deselected** (baseline 1683) |
| Four-set gate `tests/test_four_set_coverage.py` | **14 passed**, run standalone |
| Sixteen-sheet RCP area baseline | **byte-identical, moved = 0** |
| Thirteen sheets with a printed pair | all ratios in **[0.9, 1.15]**, none flagged |
| ID-415 / ID-420 (no printed pair) | `bound_sf is None`, flagged, **area still returned** |
| `_MAX_UNIT_SF` / `flag_implausible_unit` | absent |
| `ast.parse(..., feature_version=(3,9))` | py39 ok on both modified modules |
| `git diff --stat uploads/ human_inputs/ reports/ docs/PIPELINE-GROUND-TRUTH.md` | **EMPTY** |

**No paid command was run.** `pytest -m golden`, `scripts/accuracy_gate.sh`,
`scripts/vision_only_benchmark.py` and `scripts/golden_convergence.py` were not executed; `.env` was
not read. Every number above came from a free offline probe or the offline suite.

### Impact analysis (CLAUDE.md), run before editing

| Symbol | Risk | Direct callers |
|---|---|---|
| `room_fill.flag_implausible_unit` | LOW | 1 (`_measure_room_fills`) + tests |
| `room_fill.measure_enclosed_area` | LOW | `_measure_room_fills`, tests, `scripts/room_probe.py` |

`gitnexus detect-changes` reports **HIGH** across 8 execution flows for `_measure_room_fills`.
**That HIGH is hereby surfaced, as CLAUDE.md requires.** It is mitigated rather than accepted: the
sixteen-sheet real-PDF area baseline is byte-identical, the four-set gate is green, and the clip
recipe was extracted rather than rewritten so the rectangle every downstream flow measures is the
same object it measured before.

## Deviations from Plan

### 1. [Rule 1 — bug caught in-flight] The plan's harvest rule produces a bound 25x too small

- **Found during:** Task 3, probing all sixteen sheets before writing production code.
- **Issue:** the plan says to keep dimension samples "whose text bounding-box centre lies in the
  clip **OR** in any other viewport carrying the same plan name". Implemented literally, ID-415 and
  ID-420 stop returning `None` and start returning **11.2 SF** and **68.3 SF** — bounds built from
  partial interior dimensions (`9'-0"` x `1'-3"`) that a reflected-ceiling plan happens to print.
  Two perfectly good measurements are then reported as **25x** and **6.6x** overruns.
- **Fix:** the harvest reads the **architectural sibling** of the same plan name, and falls back to
  the drawing's own clip only when the set contains no architectural plan of that name (so a lobby
  sheet stays measurable). For an architectural fill the sibling IS its own clip, so the two cases
  are one rule rather than a union. Re-measured: exactly INV-02 §4, including `None` on both sheets.
- **Commit:** `15c48bc`

### 2. [Rule 4 — escalated, and CLOSED by orchestrator decision] The clip-cell partition rule is falsified

Tasks 1, 2 and 4 are **not shipped**, and the plan is closed without them. Four prototypes were built
and measured against all sixteen real prototype sheets; none reaches either the plan's own
no-regression bar (2%) or the executor's byte-identical bar:

| variant | sheets reproducing the pinned RCP area | worst error |
|---|---|---|
| midpoint between anchor centres + ink bbox (the plan's rule) | **4 of 16** | 88% (p38) |
| neighbour-edge cell, no ink tightening | **3 of 16** | 185% (p27) |
| neighbour-edge cell + ink-gutter clustering | **1 of 16** | returns `None` on 2 sheets |
| midpoint cell + gutter-snapped edges | **0 of 16** | degenerate clips |

Three measured facts, any one of which blocks the plan as written:

1. **A plan title is not centred under its drawing.** On ID-412 the RCP title spans x 940-1135 while
   its drawing runs to x ≈ 1373, and the midpoint between the FF and RCP title centres falls at
   733.6 — inside the FF drawing. The midpoint partition therefore **cuts drawings**, which is why
   it reproduces only 4 of 16.
2. **No anchor-derived partition is a guaranteed superset of its drawing.** On ID-407 the RCP
   drawing's regions extend to x = 1626.4, past the FC title's left edge at 1607.8. Even the most
   generous neighbour bound — `[previous anchor.x1, next anchor.x0]` — clips a real region off it.
3. **The sixteen pinned areas are not clip-independent quantities, so equality is unattainable in
   principle.** ID-407's 229.4 SF is the sum of eight regions, three of which are **dimension-string
   corridors** — 13.4 SF at x 1049.5-1060.7 (11 pt wide, 370 pt tall), 8.5 SF at x 1245.2-1254.2 and
   10.8 SF at x 1617.4-1626.4. That is **32.7 SF, 14% of the pinned number**, and whether each one
   is counted depends entirely on where the ±260 pt constant's edge happens to fall. INV-02 §3's own
   sweep says the same thing from the other side: three sheets move 17-20% across a ±80 pt change of
   that constant. **A clip that no longer depends on a width constant cannot reproduce a number that
   does.**

**The resolution: fact 3 is not an engineering obstacle, it is an unanswered domain question.** A
baseline that is 14% composed of dimension-string corridors is not a specification, and pinning any
new clip against it would be fitting geometry to an artefact of the old constant. The question —
*what should a dimension-string corridor contribute to a room's measured area?* — is logged verbatim
as **DEF-23-SP4**, and its answer comes from DATA rather than from a choice: the estimator's own
take-off states what was counted. The first evidence points one way — `ID-411 KING SUITE B`'s golden
**353.4 SF** against printed overall dimensions of `17'-0" x 20'-7 1/8"` = **350.1 SF**, a 0.9%
match, which is what you would see if the estimator measured the room and not its dimension
corridors. (The 350.1 is measured by this plan's own `printed_extent_bound`; the golden figure is
quoted from the orchestrator's reading of the take-off.) One sheet is a coincidence; the pattern
needs confirming across several before anything is pinned, and that means reading the **take-off
documents**, not the plans.

The **sixteen pinned RCP areas are left exactly as they are**. They remain a valid regression guard
for the current clip — which is unchanged by this plan — and 23-09's equality test still passes
untouched.

What was **not** done: no threshold was widened, no baseline literal was rewritten to match a new
output, and no partially-wired helper was committed. Tuning the partition until sixteen numbers
agreed would have been the coincidence trap this phase exists to abolish, in a new costume.

### 3. [Correction to the record] INV-02 §5's strip collapse was already fixed by 23-07

The plan's Task 1 acceptance criterion says `measure_enclosed_area` on Moxy page 14 "returns a RESULT
instead of nothing". Measured today, **it already returns a result**: `LEVEL 07 ROOFTOP BAR - RCP
PLAN`, 77.6 SF over 5 regions. INV-02 §5's `Rect(1691.2, 0.0, 2232.3, 32.9)` was computed in
**drawing space**; plan 23-07 moved the clip construction into page space, where page 14's title sits
near the page BOTTOM and the 620 pt box does not collapse. The residual defect on that sheet is
undermeasurement (77.6 SF of a rooftop bar), not silence.

The second half of that criterion — "its largest region exceeds nine hundred square feet" — was not
reached by any variant. The most generous cell tried (the whole sheet minus its title block) measures
2,689.7 SF across many regions whose **largest is 356.1 SF**. A reflected ceiling plan is subdivided
by its own ceiling grid, so a single enclosed region above 900 SF may not exist on that drawing at
all. The criterion needs re-deriving from the sheet before it can be used as a gate.

### 4. [Scope boundary — logged, NOT fixed] The suite still rewrites three synthetic fixture PDFs

`tests/fixtures/synthetic/{dimensions,floorplan,symbols}_synthetic.pdf` come back modified after any
full-suite run. Pre-existing (23-08 deviation 6, 23-09 deviation 8, 23-10 deviation 5), unrelated,
reverted rather than committed.

---

**Total deviations:** 1 auto-fixed (Rule 1), 1 STOP (Rule 4), 1 correction to the record, 1 logged
and not fixed.

## Issues Encountered

**A synthetic sheet that draws no dimension is now flagged, and that is the feature.**
`test_the_region_bound_is_threaded_and_defaults_to_the_module_constant` asserted
`needs_review is False` on a fixture that draws a room and a scale but no dimension string. Under the
new contract that fixture has nothing to cross-check against, so it is flagged — for exactly one
reason, which the test now asserts by name. A check that cannot run must say so; passing silently is
the failure mode the whole plan exists to remove.

**The prototype work was the deliverable, not a detour.** Four clip variants were built and measured
against sixteen real sheets precisely so that the decision to stop would be a measurement rather than
a judgement. The dimension-corridor finding in Deviation 2 fact 3 came out of that work and is
independently useful: it says the sixteen-sheet baseline is a weaker anchor than it looks, and
whoever fixes the clip will have to decide what those 32.7 SF of annotation cells are worth before
they can pin anything.

## Known Stubs

None. Nothing half-wired was committed: the clip helpers were prototyped in a scratchpad and left
there rather than merged as unused code with invented semantics.

## Threat Flags

None — no new network, auth, filesystem or schema surface. No new file is read or written.

Registered mitigations from the plan's threat model, as they stand:

- **T-23-43 (a crafted printed dimension suppresses or fabricates a plausibility flag)** —
  **delivered.** `cross_check_extent` can only ever *raise* `needs_review`; it has no path that
  clears a flag, drops a row or rewrites `area_sf`, and an absent bound flags rather than passes.
  Pinned by `test_no_printed_extent_flags_and_never_drops_the_measurement` and by
  `test_an_oversize_flag_is_not_erased_by_the_extent_cross_check`.
- **T-23-41, T-23-42, T-23-44** — carried forward with Tasks 1, 2 and 4. No clip geometry changed, so
  none of them is live.

## Commits

| Task | Commit | Description |
|---|---|---|
| 3 | `15c48bc` | Cross-check a fill against the drawing's own printed extent |

## Requirement status

`V4-MEAS-02` is **advanced, not completed** — left unticked. The guest-room-sized plausibility bound
is gone and its scale-free replacement is measured and pinned, which is the requirement's substance.
But the requirement is carried jointly with the geometric clip, and the clip is unfixed. Ticking the
box would claim a generality the engine does not yet have: a lobby still measures 77.6 SF of a
rooftop bar.

## What this unblocks — and what it does not

- **23-13** can read `extent_ratio` to decide whether a fill is one unit before billing its
  perimeter, which is the check INV-01 §4 asked for.
- **23-16** inherits the corrected story in code; `docs/PIPELINE-GROUND-TRUTH.md` §14.2 is still owed
  the same correction.
- **SP-4 is still open, and now has a named blocker.** Nothing in this plan changed a clip. The four
  measured variants, the three falsifying facts and both corrections to the plan's premises are the
  starting point for whoever takes it next — but the first question is not geometric at all, and it
  is recorded as **DEF-23-SP4**: *what should a dimension-string corridor contribute to a room's
  measured area?* Answering it requires the take-off documents. The re-plan is scheduled separately
  once that is settled.
- **DEF-23-10** (the coverage ledger calling a KEPT oversize region "rejected") nominated 23-11 as
  its owner because 23-11 was to open `_measure_room_fills`. That rewire did not happen, so the
  rename carries forward with SP-4; the deferred item has been annotated.

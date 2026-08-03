---
phase: 23-measurement-engine-completion
plan: 10
subsystem: deterministic/open_runs
tags: [SP-5, open-runs, chainer, styled-harvest, viewport-kinds, D-03, D-07, INV-04, INV-06]
status: complete

requires:
  - phase: 23-02
    provides: "the rotation-aware match_scales_to_viewports(page=...) that lets a released region's caption actually bind, and the printed-scale parser the caption band reads"
  - phase: 23-07
    provides: "the page-space clip discipline the chainer's mandatory clip argument follows"
  - phase: 23-09
    provides: "room_fill.to_page_space — THE single rotation transform, reused rather than forked for the title band; and the 1637-passed offline baseline this plan holds green"
provides:
  - "walls._harvest_styled — the segment harvest widened to carry per-segment length, stroke width and stroke colour, with walls._harvest re-expressed as its projection"
  - "walls.StyledSegment / walls.StyledCurve — endpoint-first tuples every existing Segment helper already accepts"
  - "deterministic/open_runs.py — THE one open-polyline run chainer core: OpenRun, extract_open_runs, clamp_run, run_lf"
  - "open_runs.PAIR_OFFSET_MAX_FT bound BY REFERENCE to walls.MIN_THICKNESS_FT, so a rail pair and a wall pair are disjoint by construction"
  - "viewports._title_band / _titleish_text_in_band / _band_printed_fpi — the caption strip at a region's visual bottom edge, in page space"
  - "a one-directional release from the legend/schedule kinds, gated on a caption that names a PLAN and states a scale"
affects:
  - "23-12 (the two selectors) — consumes extract_open_runs + clamp_run + the OpenRun mark_signature/mark_stats carriers; must NOT fork a second chainer"
  - "23-12 — Crow page 2's STAIR PLAN region is now an unmasked drawing at 1/2\" = 1'-0\", so four of the five estimator rail marks are reachable and correctly scaled"
  - "23-13/23-14 — walls._harvest_styled is the harvest to build on; _harvest stays as its projection"

tech-stack:
  added: []
  patterns:
    - "widen a primitive and re-express the old one as a PROJECTION of it, so the old behaviour is byte-identical by construction rather than by inspection"
    - "bind a constant to another module's constant BY REFERENCE when the two bands must stay disjoint — a copied literal drifts"
    - "a classification change that unmasks geometry must be diffed against the DOWNSTREAM measurement, not just against the classification"
    - "a promotion out of a masking kind must be one-directional and require positive evidence, never the absence of a word"
    - "when a plan's proposed rule is falsified by the fixtures, the measurement wins and the rule is re-derived, not widened"

key-files:
  created:
    - src/bobbytailor/deterministic/open_runs.py
    - tests/test_open_runs.py
    - tests/test_viewports.py
  modified:
    - src/bobbytailor/deterministic/walls.py
    - src/bobbytailor/deterministic/viewports.py
    - tests/test_walls.py
    - .planning/phases/23-measurement-engine-completion/deferred-items.md

key-decisions:
  - "INV-06's proposed rule — 'do not call a region a table when it owns a printed drawing scale, because a real table has no drawing scale' — is FALSE on all four plan sets. Five genuine schedule regions own one (Crow p1 GLASS SCHEDULE 20 ft/in, Bob's A8.1 door schedule 2.67, Chelsea p0 0.33, two Moxy p15 regions 4.0), because a schedule shares its sheet with details and the 40 pt proximity halo picks up the neighbour's callout. Shipping it put 429 LF of Bob's door-schedule grid into wall extraction. The scale must sit in the CAPTION BAND, beneath the region and beside its name."
  - "The release from legend/schedule is ONE-DIRECTIONAL and requires BOTH a PLAN name and a scale in the caption band. Nothing in the changed code can newly create a masked kind, so no geometry measured today can be masked out tomorrow by it."
  - "The parallel-pair band's ceiling IS walls.MIN_THICKNESS_FT, imported by reference. INV-06 proposed 0.02-1.00 ft, which overlaps the wall window [0.25, 1.333] ft; the overlap would let one segment pair be claimed as both a rail and a wall."
  - "Pair collapse is restricted to a single 1-degree angle bin rather than INV-06's +/-5 degrees. CAD draws a rail's two faces exactly parallel, and a band that is too tight can only UNDER-collapse — a rail reported at 2x, visibly wrong — whereas one too wide silently HALVES an unrelated pair."
  - "A run's length is its SPAN, bridged gaps included — the opposite of a wall, whose material length excludes its openings. An annotated linetype's break exists so the word can be drawn in it; the pipe runs straight through."
  - "The styled harvester's max_segments cap defaults to None. extract_walls_detailed enforces MAX_SEGMENTS itself AFTER its own minimum-length filter and must keep reaching that check so an over-cap page is FLAGGED 'segment cap exceeded' rather than silently emptied. The chainer, which has no such downstream check, passes the cap in."
  - "Crow page 2 goes from 4 unbound printed-scale labels to 3, not to 0. Zero is arithmetically unreachable from viewports.py: 13 captions, 11 non-title-block regions, one label per region. Logged as DEF-23-11 with the second cause (a symmetric containment margin lets a caption 3-5 pt above a region's top edge be claimed by it)."
  - "Stub closure stays at ONE hop. INV-04 measured 810.7 LF bare, 847.8 with one hop (-4.4% vs the estimator's 886.77) and 897.6 with two (+1.2%) — but hop two demonstrably absorbs leader arrowheads. The +/-5% band is the contract."

requirements-completed: []
requirements-advanced: [V4-MEAS-05]

coverage:
  - id: T1
    description: "A single-stroke open line can be chained into a measurable run, which the wall pairer can never emit"
    requirement: V4-MEAS-05
    verification:
      - kind: unit
        ref: "tests/test_open_runs.py::test_three_collinear_pieces_under_the_gap_tolerance_are_one_run — exact synthetic ground truth, span 220.0 pt, ink 180.0 pt"
        status: pass
      - kind: unit
        ref: "tests/test_open_runs.py::test_the_wall_length_floor_is_not_applied_to_open_runs — twelve 4 pt dashes chain to 224.0 pt; walls' 2 ft floor would delete every one"
        status: pass
      - kind: integration
        ref: "tests/test_open_runs.py::test_crow_page2_reproduces_an_estimator_rail_mark_by_position[3 marks] — real PDF, the estimator's own markup bboxes"
        status: pass
    human_judgment: false
  - id: T2
    description: "Widening the segment harvester to carry width and colour leaves wall output byte-identical"
    requirement: V4-MEAS-05
    verification:
      - kind: unit
        ref: "tests/test_walls.py::test_harvest_is_a_projection_of_the_styled_harvest — element-for-element on a two-pen page"
        status: pass
      - kind: integration
        ref: "four-fixture probe, 83 pages: wall lists, thickness-class mappings, wall_lf_by_class, symbol groups, viewport kinds and scale bindings — diff EMPTY"
        status: pass
      - kind: integration
        ref: "tests/test_walls.py::test_bobs_roof_plan_carries_the_gas_run_stroke_width — 7 747 segments at the 0.48 pt black pen INV-04 §2 recorded"
        status: pass
    human_judgment: false
  - id: T3
    description: "A drawing that merely mentions a schedule in a note is not classified as a schedule"
    requirement: V4-MEAS-05
    verification:
      - kind: integration
        ref: "tests/test_viewports.py::test_the_stair_plan_region_is_not_a_schedule — real PDF, and the note that used to rename it is asserted still present"
        status: pass
      - kind: integration
        ref: "tests/test_viewports.py::test_a_scale_alone_does_not_release_a_table + ::test_bobs_door_schedule_sheet_keeps_its_schedule_regions + ::test_crow_page1_glass_schedule_stays_a_table_despite_owning_a_scale"
        status: pass
      - kind: unit
        ref: "tests/test_viewports.py::test_a_ruled_table_with_no_printed_scale_is_still_a_schedule"
        status: pass
    human_judgment: false
  - id: T4
    description: "Every printed scale label on Crow's detail sheet binds to a viewport"
    requirement: V4-MEAS-05
    verification:
      - kind: integration
        ref: "tests/test_viewports.py::test_the_stair_plan_label_now_binds_to_that_region — STAIR PLAN at 1/2\" = 1'-0\""
        status: pass
      - kind: integration
        ref: "tests/test_viewports.py::test_every_estimator_rail_mark_sits_in_a_measurable_scaled_viewport — all five marks, unmasked, scales {2.0, 4.0}"
        status: pass
      - kind: integration
        ref: "tests/test_viewports.py::test_crow_page2_unbound_label_count — 4 -> 3, with the pigeonhole pinned (13 labels, 11 regions) and the residual logged as DEF-23-11"
        status: pass
    human_judgment: false
  - id: T5
    description: "Chaining is bounded — a hatch field cannot become a run"
    requirement: V4-MEAS-05
    verification:
      - kind: unit
        ref: "tests/test_open_runs.py::test_a_turn_beyond_the_continuity_window_terminates_the_chain — T-23-38"
        status: pass
      - kind: unit
        ref: "tests/test_open_runs.py::test_an_unclipped_or_unscaled_call_returns_nothing — there is no unclipped entry point"
        status: pass
      - kind: unit
        ref: "tests/test_open_runs.py::test_an_over_cap_page_returns_empty_without_raising_and_under_two_seconds + tests/test_walls.py::test_over_cap_page_returns_empty_without_raising_and_bounded — T-23-37"
        status: pass
      - kind: integration
        ref: "tests/test_open_runs.py::test_chaining_a_thirty_three_thousand_segment_page_stays_bounded — Crow page 0, 33 018 segments, 0.32 s"
        status: pass
    human_judgment: false

metrics:
  duration: ~5h
  completed: 2026-08-04
  tasks: 3
  commits: 3
  tests_added: 46
  suite: "1683 passed, 2 deselected (baseline 1637)"
---

# Phase 23 Plan 10: Open-Run Chainer Core (SP-5) Summary

**The measurement primitive that could not exist inside `walls.py` now exists once, outside it: a
single-stroke line is chainable into a measured run, and the module reproduces Crow's estimator's own
rail marks by position to 0.1% — 8.31 LF at `(1605,870)-(1605,1169)` against the answer key's 8.3 at
`(1607,868)-(1607,1169)` — where INV-06's own prototype over-chained the same rail to 12.65. Wall
output is byte-identical across all 83 pages of all four plan sets, and the viewport that holds four
of the five rail marks stopped being a "schedule" because a note inside it mentioned one.**

## Performance

- **Duration:** ~5h
- **Tasks:** 3 of 3 (3 commits, one per task)
- **Files:** 3 created, 4 modified

## What shipped

### 1. `walls._harvest_styled` — the harvest widened, walls untouched

`_harvest` returned bare four-tuples, so neither consumer of SP-5 could see the pen a line was drawn
with. It now carries per-segment **length, stroke width and stroke colour**, and `_harvest` is a
**projection** of it. That is the whole mitigation for the blast radius: `gitnexus impact _harvest`
reports **HIGH**, three affected processes across two modules, and wall behaviour is byte-identical
*by construction* rather than by inspection.

`StyledSegment` puts the four endpoint fields first, so `_seg_len`, `_seg_mid` and `_angle_bin` accept
one unchanged — the widening costs the rest of the module nothing.

Width and colour are rounded to four decimals so a pen is an **equality key** rather than a tolerance:
one authored `0.48` comes back from the content stream as `0.47999998927116394`. On Bob's A3.0 roof
plan the 0.48 pt black pen INV-04 §2 recorded for the gas run is a group of **7 747 segments** — style
is genuinely carried, not merely plumbed.

The resource-exhaustion cap now lives in the styled harvester as an opt-in `max_segments`. It defaults
**off**, deliberately: `extract_walls_detailed` enforces `MAX_SEGMENTS` itself *after* its own
minimum-length filter, and an over-cap page must still reach that check so it is flagged
`"segment cap exceeded"` instead of coming back silently empty. The chainer, which has no such
downstream check, passes the cap in.

### 2. `open_runs.py` — ONE chainer, not two

INV-04 proposed `linetype_runs.py`; INV-06 proposed `linear_runs.py`. They are the same capability and
this is the one module (D-03). Neither could reuse the wall pairer: `walls` needs **two** parallel
faces at a 3"–16" offset before it emits anything, so a single-stroke pipe run can never come out of
it, and `MIN_WALL_SEG_FT = 2 ft` (~36 pt at 1/4") would discard the 3 pt exploded dashes an annotated
linetype is *made of* before pairing is even attempted.

The pipeline: harvest through `_harvest_styled` → keep segments whose midpoint is in the clip → bin by
angle → group by perpendicular offset → project and **merge across bridged gaps** → **collapse
parallel pairs** → **chain with a 20° direction-continuity constraint** over a hash grid → **absorb
short free-ended stubs with one hop**. `clamp_run` trims to an arc-length window, which is what
INV-04's mark clamp and a rail detail's printed extent both need.

Three things in it are load-bearing and non-obvious:

- **Length is stored in POINTS.** `length_lf(feet_per_point)` converts late, so a run recomputes
  instantly when a scale is corrected. A test pins that two scales return lengths in the ratio of the
  scales.
- **A bridged gap counts as LENGTH.** A wall's material length excludes its openings, because a
  doorway is not wall. A linetype's break is the opposite: the pipe runs straight through, and the gap
  exists only so the word can be drawn in it. A run's length is its **span**.
- **`PAIR_OFFSET_MAX_FT` IS `walls.MIN_THICKNESS_FT`, imported by reference.** INV-06 proposed
  0.02–1.00 ft, which overlaps the wall window [0.25, 1.333] ft; a pair in the overlap could be
  claimed as a rail *and* as a wall. Bound by reference, the two bands cannot drift apart in a future
  edit (T-23-40). A test asserts the identity, not the value.

Every constant carries the observed number it came from and the physical reason for its margin.
`MIN_INK_FRACTION` flags — never deletes — a run that is mostly bridged gap: Bob's GAS linetype
measures ~0.70, while a run bridging a 48 pt gap between two 3 pt dashes measures 0.12.

### 3. A drawing that mentions a schedule is not a schedule

Crow's **STAIR PLAN** drawing — which holds four of the five estimator rail marks — was classified
`schedule` because it contains the in-drawing note `SEE CONC. DOOR OPENING SCHEDULE`. `schedule` sits
in `takeoff_pipeline._MASK_VIEWPORT_KINDS` **and** `printed_scale._MASK_KINDS`, so that one word
masked the drawing's geometry out of every measurement *and* barred it from owning a printed scale.

A region the table test calls a table is now **released** when its **title band** — the caption strip
at its visual bottom edge, taken in page space via `room_fill.to_page_space` so a `/Rotate 270` sheet
is read the way a human reads it — carries a **drawing caption**: a `PLAN` name *and* a printed scale.
The release is strictly one-directional; nothing in the changed code can newly create a masked kind.

## The result, measured on the real PDFs (zero API)

### All five rail marks are now reachable and correctly scaled

```
GUARD  mark ( 273, 167)-(1229, 167) -> R1 kind=detail masked=False bound_fpi=4.0
GUARD  mark (1771, 869)-(1771,1168) -> R7 kind=detail masked=False bound_fpi=2.0
GUARD  mark (1607, 870)-(1607,1169) -> R7 kind=detail masked=False bound_fpi=2.0
HAND   mark (1783, 937)-(1783,1315) -> R7 kind=detail masked=False bound_fpi=2.0
HAND   mark (1591, 936)-(1591,1315) -> R7 kind=detail masked=False bound_fpi=2.0
```

`fpi 2.0` is 1/2" = 1'-0" and `fpi 4.0` is 1/4" = 1'-0" — exactly the two scales INV-06 §1.3 measured
those marks at. R7 was `schedule` with `printed_fpi=None` before this plan.

### The chainer reproduces the estimator's marks by position

Run against the answer key read out of the take-off PDF's coloured markup — never against the stamped
420.35 / 438.80 LF totals, which are a per-instance length times a multiplier the drawings do not
print (INV-06 §4 risk 1):

| estimator mark | key LF | shipped module | shipped bbox |
|---|---|---|---|
| `(1607,868)-(1607,1169)` | 8.3 | **8.31** paired | `(1605,870)-(1605,1169)` |
| `(1766,869)-(1767,1168)` | 8.3 | **8.29** paired | `(1769,870)-(1769,1168)` |
| `(275,167)-(1229,167)` | 53.1 | **53.00** | `(275,155)-(1229,155)` |

INV-06's own scratchpad prototype **over-chained the first two to 12.65 and 12.63 LF** — right bbox,
wrong length. The shipped module lands on 8.31 / 8.29 because the collinear merge runs before
chaining and the pairing band is tighter.

### Bounded work on the dense page

```
crow p0 FULL PAGE    segs=33018  runs=987   0.32s
bobs p3 FULL PAGE    segs=44886  runs=267   0.27s
```

The whole-page clip is not how the module is used — it is the worst case the guards must survive.
The 987 junk runs it produces on Crow page 0 are the documented reason chaining is only ever offered
inside a clip (INV-06 risk 4 / T-23-38).

### The four-fixture diff — walls extracted WITH the kind-derived mask

83 pages of Moxy / Crow / Bob's / Chelsea, comparing viewport kinds, printed-scale bindings, resolved
page scales, symbol groups, unmasked wall lists **and** wall lists extracted with the
`_MASK_VIEWPORT_KINDS` mask the pipeline builds from those kinds:

| measure | pages changed |
|---|---|
| unmasked wall lists + thickness classes | **0** |
| `wall_lf_by_class` | **0** |
| symbol groups | **0** |
| resolved page scale (`main_fpi`, `fpp`) | **0** |
| **masked** wall lists | **1** — Crow p2 |
| viewport kinds | **1** — Crow p2 `R7 schedule -> detail` |
| scale bindings | **1** — Crow p2, unbound 4 -> 3 |

Exactly the delta the plan named, and nothing else. Crow p2's masked wall count moves 83 → 118
because the STAIR PLAN drawing is a drawing again and its own linework is measured — that is the
change, not a leak.

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest -q` | **1683 passed, 2 deselected** (baseline 1637) |
| Four-set gate `tests/test_four_set_coverage.py` | **14 passed**, run standalone after the final commit |
| `tests/test_walls.py` | 30 passed (24 pre-existing + 6 added) |
| `tests/test_open_runs.py` | 29 passed (new file) |
| `tests/test_viewports.py` | 11 passed (new file) |
| Four-fixture probe diff, 83 pages, incl. masked walls | **1 page** — Crow p2, as designed |
| `_harvest` is a projection / `MAX_SEGMENTS == 200000` | `projected, cap intact` |
| `ast.parse(..., feature_version=(3,9))` | `py39 ok` on `walls.py`, `open_runs.py`, `viewports.py` |
| `gitnexus detect-changes` | run before each commit |
| `git diff --stat uploads/ human_inputs/ reports/ docs/PIPELINE-GROUND-TRUTH.md` | **EMPTY** |

**No paid command was run.** `pytest -m golden`, `scripts/accuracy_gate.sh`,
`scripts/vision_only_benchmark.py` and `scripts/golden_convergence.py` were not executed; `.env` was
not read. Every number above came from a free offline probe or the offline suite.

### Impact analysis (CLAUDE.md), run before editing

| Symbol | Risk | Direct callers | Processes affected |
|---|---|---|---|
| `walls._harvest` | **HIGH** | 1 (`extract_walls_detailed`) | 3 (`_deterministic_bundle`, `extract_walls_detailed`, `_run_sheet_vector`) |
| `walls.extract_walls` | **HIGH** | 1 | 3 |
| `viewports._make_region` | **CRITICAL** | 1 (`_segment_viewports_inner`) | 6 (`solve_page_viewports`, `_deterministic_bundle`, `extract_material_tags_for_doc`, `page_measurable_signal`, …) |

**Both HIGH and CRITICAL risks are hereby surfaced, as CLAUDE.md requires.** They were mitigated, not
accepted:

- `_harvest` — re-expressed as a pure projection of the widened harvester, plus an element-for-element
  equality test and a byte-identical 83-page four-fixture diff. Nothing downstream can observe the
  widening.
- `_make_region` — the change is one-directional (it can only *release* a region from a masking kind,
  never create one), and it was diffed against the DOWNSTREAM measurement rather than against the
  classification alone. That diff is what caught the regression described below.

## Deviations from Plan

### 1. [Rule 1 — bug caught in-flight] The plan's own promotion rule leaks table linework

- **Found during:** Task 3, by extending the four-fixture probe to extract walls **with** the mask the
  pipeline derives from viewport kinds. The first probe compared only *unmasked* walls and reported a
  clean bill of health, which was worthless: a promotion changes what the mask *contains*, so the
  regression is invisible unless the mask is applied.
- **Issue:** the plan and INV-06 §2 step 6 both say *"do NOT assign the legend or schedule kind when
  the region has its own printed drawing scale — a real table has no drawing scale"*. Measured, that
  premise is **false on every one of the four plan sets**:

  ```
  Crow    p1  R1  'GLASS SCHEDULE / EXTERIOR FINISH SCHEDULE'      printed_fpi = 20.0
  Bob's   p5  R1  '... FINISH HARDWARE ... SCHEDULE ...'  (A8.1)   printed_fpi = 2.667
  Chelsea p0  R2  'SCHEDULE / SCHEDULE / SCHEDULE'                 printed_fpi = 0.333
  Moxy    p15 R2  'SCHEDULE DOOR ARCHITECTURAL'                    printed_fpi = 4.0
  Moxy    p15 R3  'SCHEDULE DOOR ARCHITECTURAL'                    printed_fpi = 4.0
  ```

  A schedule shares its sheet with details, and the existing 40 pt proximity halo happily picks up a
  neighbour's callout. Implementing the rule as written released all five and put **429 LF of TC1**
  from Bob's A8.1 door-schedule grid straight into wall extraction (0 → 49 walls on that page), with
  smaller leaks on Crow p1/p3, Chelsea p0 and Moxy p15. That is threat **T-23-40** firing exactly as
  registered.
- **Fix:** the scale evidence must sit in the **caption band** — beneath the region, beside its name —
  not in a proximity halo, and it must be accompanied by a `PLAN` name. The release is now gated on
  both. Re-measured: **one** kind change across 83 pages, and the five schedule regions above all stay
  schedules. Three of them are pinned as regression tests.
- **Why it matters beyond the bug:** the plan's own anti-regression instruction said to "diff the
  wall, symbol and scale outputs on all four fixtures". Doing that literally — on the *unmasked*
  outputs — passes clean while shipping the leak. The diff has to be taken through the mask the
  classification feeds.
- **Commit:** `5535300`

### 2. [Decision] Crow page 2 goes from 4 unbound labels to 3, not to 0

The plan's acceptance criterion asks for 0, following INV-06 §3.5. Zero is **arithmetically
unreachable** from `viewports.py`: `match_scales_to_viewports` keeps at most one label per region, and
Crow page 2 draws **13** captioned details into **11** non-title-block regions. Two labels cannot bind
however the kinds are assigned.

The third has a separate cause, diagnosed and logged: `_contains(..., margin=6.0)` is symmetric, so a
caption sitting a few points *above* a region's top edge is treated as inside it. R4's top is `623`
and `RAMP RAIL SECTION`'s caption is at `y=620`; R12's top is `1450` and `Z-GUARD DETAIL`'s is at
`y=1445`. Both captions are claimed by the drawing *below* them, which already owns a nearer label.

Both fixes live in `printed_scale.py`, which this plan does not touch, and neither blocks 23-12 — all
five rail marks are already in unmasked, correctly-scaled viewports. Logged as **DEF-23-11**. The test
pins `3`, `13` and `11` together so the pigeonhole cannot silently change.

### 3. [Decision] The pairing angle window is 1°, not INV-06's ±5°

Offsets are only comparable within one angle bin (a perpendicular offset measured against a direction
5° away is meaningless for a point 2 000 pt from the origin). CAD draws a rail's two faces exactly
parallel, so 1° is ample — and the error directions are asymmetric: a band that is too tight can only
**under**-collapse, reporting a rail at 2× where a human sees it immediately, whereas one too wide
silently **halves** an unrelated pair. Tighter is the safe direction.

### 4. [Decision] `clamp_run` is a public helper, not an inlined step

The plan lists "clamp" inside the core pipeline. It ships as a tested public function instead, because
both selectors clamp for different reasons — INV-04 §3 S7 clamps to `[first_mark - pitch, last_mark +
pitch]`, and a rail selector clamps to a detail's printed extent — and neither should re-derive
polyline arc-length arithmetic. The default extraction path does not clamp, because the merge already
bounds every span to its observed ink.

### 5. [Scope boundary — logged, NOT fixed] The suite still rewrites three synthetic fixture PDFs

`tests/fixtures/synthetic/{dimensions,floorplan,symbols}_synthetic.pdf` come back modified after any
full-suite run. Pre-existing (23-08 deviation 6, 23-09 deviation 8), unrelated, reverted rather than
committed.

---

**Total deviations:** 1 auto-fixed (Rule 1), 3 decisions recorded, 1 logged and not fixed.

## Issues Encountered

**The probe that would have passed.** The first four-fixture diff — viewport kinds, scale bindings,
resolved scales, symbol groups and *unmasked* wall lists — reported `walls: 0` changed and would have
been quoted as proof. It was measuring the wrong thing. Only after adding a second wall extraction
that applies `_MASK_VIEWPORT_KINDS` did the 429 LF leak on Bob's A8.1 appear. A classification change
has to be diffed against what it classifies *for*.

**The chainer passed 24 synthetic tests on the first run, which meant nothing.** What established that
it works is the real-PDF position table: the module was written from INV-06's *description* and then
compared against the estimator's markup bboxes it had never seen. That it lands on 8.31 / 8.29 where
INV-06's independent prototype landed on 12.65 / 12.63 is the only evidence that matters, and it is
evidence about the algorithm, not about the tests.

**Both edits were flagged HIGH/CRITICAL before a line was written.** The projection pattern for
`_harvest` and the one-directional constraint on `_make_region` were chosen *because* of those
ratings, not retro-fitted after them.

## Known Stubs

None in the shipped code paths.

**Deliberately absent, with a named owner:** `OpenRun.mark_signature`, `mark_stats`, `scale_fpi`,
`viewport_title` and `is_typical` are carrier fields the core never fills. They are stamped by the two
selectors in **23-12** — the annotated-linetype selector, which recognises a `— GAS —` mark and its
pitch statistics, and the rail selector, which stamps the owning viewport's title and scale. Nothing
in this plan reads a glyph or names a run, and no LF quantity is emitted anywhere: `extract_open_runs`
has **no call site in `src/` yet**. That is intentional — a chainer that also decided what a run was
called would be the fork this plan exists to prevent.

## Threat Flags

None — no new network, auth, filesystem or schema surface. No new file is read or written.

Registered mitigations, all delivered:

- **T-23-37 (crafted page with hundreds of thousands of micro-segments)** — the cap is carried into
  the styled harvester and passed by the chainer; the harvest abandons the page mid-walk rather than
  after it; chaining is a bounded hash-grid pass. Pinned by two bounded-work tests (< 2 s on an
  over-cap page) and measured on real ink at 0.32 s for Crow page 0's 33 018 segments.
- **T-23-38 (combinatorial explosion on an unclipped dense page)** — `clip_pt` is a required
  positional argument with no default and no unclipped entry point; a missing or malformed clip
  returns `[]`. Pinned by `test_an_unclipped_or_unscaled_call_returns_nothing`.
- **T-23-39 (the harvester widening silently moving wall output)** — `_harvest` is a projection,
  asserted element-for-element, plus an 83-page byte-identical four-fixture diff.
- **T-23-40 (promotion letting table linework into wall extraction)** — **this mitigation fired on
  real data during this plan** and is the reason deviation 1 exists. The shipped gate needs a caption
  band naming a PLAN *and* stating a scale; the four-fixture masked-wall diff is recorded above; three
  real schedule regions and two synthetic tables are pinned as negative tests.

## Commits

| Task | Commit | Description |
|---|---|---|
| 1 | `bfe0d64` | A styled harvester, with walls as its projection |
| 2 | `69040b3` | The ONE open-polyline run chainer core (SP-5) |
| 3 | `5535300` | A drawing that mentions a schedule is not a schedule |

## Requirement status

`V4-MEAS-05` ("Rail/linework LF measured from linework") is **advanced, not completed** — left
unticked. The measurement primitive exists and is position-validated, but **no LF quantity reaches a
line item**: `basis: linear` still has no consumer in `fusion.py`, and `extract_open_runs` has no call
site in `src/`. 23-12 owns the selectors and 23-13 the binder. Ticking the box would claim a row no
client can see.

## What this unblocks

- **23-12 (the two selectors)** inherits `extract_open_runs`, `clamp_run` and the `OpenRun` mark
  carriers. It must call them, not fork them — that is the entire point of D-03 and the reason this
  plan built one core for two investigations. It also inherits Crow page 2's STAIR PLAN region as an
  unmasked drawing bound to 1/2" = 1'-0", so four of the five estimator rail marks are finally
  measurable at the right scale.
- **23-13 / 23-14** inherit `_harvest_styled` as the harvest to build on, and the standing rule that
  `_harvest` stays its projection.
- **DEF-23-11** carries the three still-unbound Crow captions and their two distinct causes to
  whichever plan next opens `printed_scale.match_scales_to_viewports`.

**The standing caution applies to the rails.** Measuring a run is not counting the runs. Crow's golden
Guard Rail 420.35 LF and Hand Rail 438.80 LF are ~6× and ~21× what is actually drawn; the instance
multiplier is not printed on the sheets and is not recoverable from the linework. When 23-12 emits
these, it must emit per-instance LF with `unit_count=None` and `needs_review=True`. Tuning a
multiplier until a total reads 420 would be the coincidence trap this phase exists to abolish.

## Self-Check: PASSED

- `src/bobbytailor/deterministic/open_runs.py` — FOUND
- `src/bobbytailor/deterministic/walls.py` — FOUND
- `src/bobbytailor/deterministic/viewports.py` — FOUND
- `tests/test_open_runs.py` — FOUND
- `tests/test_viewports.py` — FOUND
- `tests/test_walls.py` — FOUND
- commit `bfe0d64` (Task 1) — FOUND
- commit `69040b3` (Task 2) — FOUND
- commit `5535300` (Task 3) — FOUND
- `git diff --stat uploads/ human_inputs/ reports/ .env docs/PIPELINE-GROUND-TRUTH.md` — EMPTY

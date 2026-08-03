---
phase: 23-measurement-engine-completion
plan: 09
subsystem: deterministic/room_fill
tags: [SP-3, region-geometry, perimeter, shape-ratio, contour-trace, D-03, D-07, INV-01, INV-02, INV-05]
status: complete

requires:
  - phase: 23-07
    provides: "max_region_sf threaded through _measure_room_fills, and the page-space clip that makes every real-PDF assertion here measure the right rectangle"
  - phase: 23-03
    provides: "the dropped_regions out-list and the MEASURED_PARTIAL coverage disposition the oversize register still feeds"
  - phase: 23-08
    provides: "the offline suite baseline this plan holds green (1601 passed / 2 deselected)"
provides:
  - "room_fill.label_mask + LabelledMask — THE one connected-component labeller, keeping labels, per-component counts, topmost-leftmost seed index and edge-touch flags"
  - "room_fill.free_mask — the ink/free classification as a single bytes.translate"
  - "room_fill._trace_outer_contour — Moore-neighbour outer-ring trace with a first-transition stopping criterion and a hard iteration cap"
  - "room_fill._simplify_ring / _douglas_peucker / _ring_length — closed-ring-safe simplification"
  - "room_fill.MAX_HONEST_SHAPE_RATIO = 8.0, with its geometric rationale"
  - "FilledRegion.perimeter_lf + .shape_ratio"
  - "RoomFillResult.perimeter_lf + .region_perimeters + .region_shape_ratios, all three in to_dict()"
  - "measure_enclosed_area: the linear scale factor beside the area factor, and oversize regions KEPT AND FLAGGED"
  - "flag_implausible_unit preserves an existing review reason instead of overwriting it"
affects:
  - "23-13 (wall-area binder) — consumes region_perimeters + region_shape_ratios; MAX_HONEST_SHAPE_RATIO is the published threshold for wall_perimeter_for_unit"
  - "23-14 (elevation facade) — label_mask is the silhouette-complement labeller; it must not fork its own copy"
  - "23-11 (geometric clip cell) — inherits DEF-23-10, the ledger wording for a region that is now kept rather than rejected"
  - "23-16 — the two tests that encoded the drop-the-oversize-region story were rewritten HERE, not left red"

tech-stack:
  added: []
  patterns:
    - "one labeller, three consumers: label a clip ONCE and hand the labels out, rather than answering each geometric question with its own pass"
    - "a perimeter must be traced from the SAME mask its area was counted from, so the two can never describe different regions"
    - "a blind validator is computed from geometry alone and its threshold is read off observed values with a stated margin — never fitted to make a total match"
    - "an implausible measurement is kept and flagged; deleting it makes it indistinguishable from a genuine zero"
    - "a flag must never overwrite another flag"
    - "when a real-PDF assertion and a plan literal disagree, the pre-change probe output wins — the literal is not the ground truth"

key-files:
  created: []
  modified:
    - src/bobbytailor/deterministic/room_fill.py
    - tests/test_room_fill.py
    - .planning/phases/23-measurement-engine-completion/deferred-items.md

key-decisions:
  - "The trace's stopping criterion is repetition of the FIRST TRANSITION, not 'back at the seed facing west'. The textbook phrasing assumes the ring passes through the seed the way the walk left it; on Moxy page 35 (ACC KING TUB RCP, dominant 184.3 SF region) it re-enters the seed heading SOUTH, so the initial state lies on the walk's tail, never recurs, and the walk ran 1.18 M steps to its cap and reported NO perimeter for that room. Found by a real-PDF assertion, not by a unit test."
  - "MAX_HONEST_SHAPE_RATIO = 8.0 is read off geometry: 4.00 a square, 4.24-5.08 every honest room INV-01 measured, 8.54-9.04 the leaking AR fills, 11.6-13.4 annotation cells. Roughly a 2x margin on the worst honest room and still below the best leak. It is NOT applied to area and is not consumed by anything in this plan — 23-13 owns its use."
  - "The plan's sixteenth pinned literal (451.0) is wrong; the shipped engine measures ACC QQ RIS at 451.1, which is also what INV-01 section 1 recorded. The test pins 451.1, the value the PRE-CHANGE probe produced. Pinning 451.0 would have required moving a measurement to match a document."
  - "The P/A band of 0.20-0.45 per foot is asserted only over the 150-400 SF room sizes it was quoted for. P/A equals the shape ratio divided by sqrt(A), so it is the same statement scaled by size; KING A's dominant region is 121.8 SF, where an honest ratio of 5.08 gives 0.46 by arithmetic. Widening the band to swallow that would be fitting a threshold to an output. The identity is pinned instead."
  - "The three currently-shipped tests encoding the drop-the-oversize-region story were REWRITTEN in this plan rather than left failing for 23-16. A red suite for seven plans masks every real regression that lands in between."
  - "free_mask uses bytes.translate instead of a per-pixel Python loop: identical bits, 19-page Moxy probe 83 s -> 75 s. Taken because the labeller is the acknowledged dominant cost (T-23-33) and the render resolution constant is explicitly not raised to compensate (R11)."
  - "The dropped_regions parameter keeps its name even though nothing is dropped any more. Renaming it is a caller-side change in takeoff_pipeline.py, which this plan is scoped out of — logged as DEF-23-10 for 23-11."

requirements-completed: []
requirements-advanced: [V4-MEAS-01]

coverage:
  - id: T1
    description: "A measured region reports its perimeter, traced from the same mask its area came from"
    requirement: V4-MEAS-01
    verification:
      - kind: unit
        ref: "tests/test_room_fill.py::test_perimeter_of_a_known_rectangle — 10' x 20' at 1/4\", 60 LF and 200 SF both within 2%"
        status: pass
      - kind: integration
        ref: "tests/test_room_fill.py::test_every_prototype_sheet_reports_a_perimeter_at_all — real PDF, all 16 Moxy prototypes, every region non-zero"
        status: pass
      - kind: unit
        ref: "tests/test_room_fill.py::test_the_per_region_lists_are_parallel_to_the_region_list"
        status: pass
    human_judgment: false
  - id: T2
    description: "An interior hole — a furniture outline or a room number — does not inflate the perimeter"
    requirement: V4-MEAS-01
    verification:
      - kind: unit
        ref: "tests/test_room_fill.py::test_perimeter_ignores_an_interior_hole — the same room with and without a 2' block at its centre"
        status: pass
      - kind: unit
        ref: "tests/test_room_fill.py::test_the_trace_walks_the_outer_ring_and_ignores_an_interior_hole — exact pixel ground truth"
        status: pass
    human_judgment: false
  - id: T3
    description: "Perimeter scales linearly with the drawing scale while area scales quadratically"
    requirement: V4-MEAS-01
    verification:
      - kind: unit
        ref: "tests/test_room_fill.py::test_perimeter_scales_linearly_while_area_scales_quadratically — one page, two scales, x2 and x4"
        status: pass
    human_judgment: false
  - id: T4
    description: "A blind shape ratio separates honest rooms from leaking fills and from annotation cells, with no golden number consulted"
    requirement: V4-MEAS-01
    verification:
      - kind: unit
        ref: "tests/test_room_fill.py::test_shape_ratio_of_a_square_is_four + ::test_the_shape_ratio_of_a_sliver_exceeds_eight"
        status: pass
      - kind: integration
        ref: "tests/test_room_fill.py::test_the_dominant_ceiling_region_has_the_shape_of_a_room[23,27,29,33] — real PDF, every ratio in [4, 6]"
        status: pass
      - kind: integration
        ref: "tests/test_room_fill.py::test_the_architectural_fill_reproduces_its_leak_signature[23,27,29] — real PDF, 8.62 / 9.04 / 8.54"
        status: pass
    human_judgment: false
  - id: T5
    description: "Adding perimeter does not move any measured area by a single decimal"
    requirement: V4-MEAS-01
    verification:
      - kind: integration
        ref: "tests/test_room_fill.py::test_the_sixteen_sheet_moxy_area_baseline_is_byte_identical — 16 pinned literals, equality not approx"
        status: pass
      - kind: integration
        ref: "offline probe diff over 19 RCP fills (Moxy pages 12, 21-38) including per-region lists — EMPTY"
        status: pass
    human_judgment: false
  - id: T6
    description: "A region larger than one guest room is kept and flagged, never dropped"
    requirement: V4-MEAS-01
    verification:
      - kind: unit
        ref: "tests/test_room_fill.py::test_an_oversize_region_is_kept_and_flagged_never_dropped"
        status: pass
      - kind: unit
        ref: "tests/test_room_fill.py::test_the_oversize_register_still_records_the_area_for_the_ledger — T-23-36"
        status: pass
      - kind: integration
        ref: "tests/test_room_fill.py::test_the_region_bound_is_threaded_and_defaults_to_the_module_constant — a tighter bound flags, it does not delete"
        status: pass
    human_judgment: false
  - id: T7
    description: "One labeller serves every consumer; the ring cannot collapse; a degenerate trace flags rather than loops"
    requirement: V4-MEAS-01
    verification:
      - kind: unit
        ref: "tests/test_room_fill.py::test_label_regions_is_a_projection_over_the_one_labeller — D-03, asserted on the source"
        status: pass
      - kind: unit
        ref: "tests/test_room_fill.py::test_plain_simplification_of_a_closed_ring_collapses_it + ::test_the_ring_safe_simplifier_does_not_collapse_a_traced_square"
        status: pass
      - kind: unit
        ref: "tests/test_room_fill.py::test_the_iteration_cap_flags_rather_than_looping + ::test_an_isolated_pixel_terminates_instead_of_spinning — T-23-34"
        status: pass
    human_judgment: false

metrics:
  duration: ~2h20m
  completed: 2026-08-03
  tasks: 3
  commits: 3
  tests_added: 30
  suite: "1637 passed, 2 deselected (baseline 1601)"
---

# Phase 23 Plan 09: Region Geometry Primitive (SP-3) Summary

**The perimeter primitive that did not exist anywhere in the package now exists once, is traced from
the same mask every area is counted from, and reports a blind shape ratio that reproduces INV-01's
independently-prototyped leak signature to the second decimal — 8.62 / 9.04 / 8.54 on the three
leaking architectural fills, 4.01–5.28 on all sixteen honest reflected-ceiling rooms — while every
one of nineteen shipped Moxy areas is byte-identical to the pre-change run. A region too large for a
guest room is now kept and flagged instead of deleting the whole drawing's measurement.**

## Performance

- **Duration:** ~2h20m
- **Tasks:** 3 of 3 (3 commits, one per task)
- **Files modified:** 2 code/test files + 1 planning doc — 977 insertions, 81 deletions, 0 created

## The result, measured on the real PDFs (zero API)

`_measure_room_fills` unbound, Moxy pages 12 and 21–38, RCP and AR, no manifest, no API key:

```
pg   kind  name              area     P_lf   ratio     P/A
23   RCP   KING A           229.4    271.7    5.08   0.461     <- INV-01 prototype: 5.08
23   AR    KING A           193.2    174.2    8.62   0.655     <- INV-01 prototype: 8.62
27   RCP   KING SUITE B     341.7    263.4    4.25   0.288     <- INV-01 prototype: 4.24
27   AR    KING SUITE B     369.9    361.7    9.04   0.573     <- INV-01 prototype: 9.04
29   RCP   QQ A             272.6    253.5    4.64   0.369     <- INV-01 prototype: 4.64
29   AR    QQ A             275.8    295.6    8.54   0.646     <- INV-01 prototype: 8.54
33   RCP   BUNK B           274.6    208.0    4.84   0.365     <- INV-01 prototype: 4.84
33   AR    BUNK B           337.0    371.3    4.37   0.345     <- INV-01 prototype: 4.37
```

Every dominant reflected-ceiling shape ratio across all sixteen prototypes falls in **4.01–5.28**
(4.00 is a perfect square). Every value INV-01 §4 produced from a throwaway scratchpad prototype is
reproduced by the shipped module — which is the only evidence that matters here, because the two were
written independently and neither consulted a golden quantity to get there.

The same blind number exposes the architectural raster leak on the sheets where it leaks, and stays
quiet on the sheets where it does not (`BUNK B` AR = 4.37, `ACC KING TUB` AR = 4.71). It is not a
detector that fires everywhere.

### Area did not move

```
$ diff baseline_rcp.json task3_rcp.json      # 19 RCP fills, area_sf AND per-region lists
(empty)
```

Sixteen of those are additionally pinned as literals in the suite — as **equality**, not `approx` —
so a future refactor that moves one fails loudly:

```
229.4  235.5  217.6  362.5  341.7  458.3  272.6  309.5
284.3  454.7  274.6  347.2  347.7  451.1  463.0  458.5
```

## What shipped

**`label_mask` — THE labeller (D-03).** The previous implementation built a labelled bitmap in a
`seen` bytearray and threw it away, returning only counts. That single fact is why no perimeter
primitive existed anywhere in the package (INV-01 §3): the geometry was computed and discarded on
every fill the engine had ever run. It now returns the label array, per-component pixel counts, each
component's topmost-then-leftmost seed index and each component's edge-touch flag. Three consumers
share it — the enclosed-void consumer that already existed, the contour consumer added here, and the
silhouette-complement consumer 23-14 will add — so a clip is labelled **once**, which is also the
performance strategy for the wide-format elevation clips (R11). `_label_regions` survives as a thin
projection over it and a test asserts on the source that the breadth-first search exists in one place.

Connectivity stays 4-way. 8-way labelling of free space would merge a room with the outside through
a single diagonal pixel gap and the room would vanish; that is asserted.

**`_trace_outer_contour` — Moore-neighbour tracing, outer ring only.** Seeded at the seed
`label_mask` already recorded, with an initial backtrack of west (which is background by
construction, because a member to the west would itself have been the topmost-leftmost pixel). It
walks one ring from outside, so a furniture block or a room-number text box inside a room contributes
nothing — asserted by tracing the same shape with and without a hole and getting the identical
length.

**The traced method is the only one implemented.** INV-05 §3 measured the naive alternative — counting
raster boundary pixels — at roughly **six times** the true perimeter. It was measured that precisely
so it would never be mistaken for a cheap shortcut, and there is no code path to it here.

**`_simplify_ring` — Douglas-Peucker with the closed-ring repair.** A ring's first and last points
are the same point, so its base chord runs from a point to itself, every vertex measures zero
deviation, and the whole ring collapses to zero length. INV-01's prototype hit exactly this and
reported **every** perimeter as `0.0` while every area was correct — which reads as *"this room has
no walls"* rather than as a bug. The repair splits at the vertex farthest from the first point,
simplifies both halves as ordinary open polylines and rejoins. A test reproduces the collapse on the
naive form and pins that the shipped path survives it.

The simplification earns its place on exact ground truth: a face rising one pixel every four columns
is traced as a staircase and over-reads by **3.0%**, and the simplified ring lands on the exact
quadrilateral perimeter to floating point. On rectilinear ink it is *lossless* — a 200×120 rectangle's
637 traced points become 5, with the length unchanged — which is why adding it cannot perturb a guest
room's number.

**Perimeter and the blind shape ratio on the fill.** The linear scale factor `(1/zoom) × ft-per-point`
now sits directly beside the area factor `(1/zoom²) × ft-per-point²`, so neither can be derived from
the other; a perimeter accidentally taken from the area factor comes back ×4 in the scaling test.
`FilledRegion` gains `perimeter_lf` and `shape_ratio`; `RoomFillResult` gains `perimeter_lf`, plus
`region_perimeters` and `region_shape_ratios` **parallel to `regions`** — a perimeter that cannot say
which region it belongs to cannot be filtered by shape. All three are in `to_dict()`.
`RoomFillResult.to_dict` has **no call site in `src/` at all** (only tests), so nothing iterates it
positionally; that was checked before shipping, as INV-01 §9 requires.

**`MAX_HONEST_SHAPE_RATIO = 8.0`, with its rationale in the code.** Every observed value it was read
from is in the comment: 4.00 a square, 4.24 a 1:2 rectangle, 4.24–5.08 every honest room INV-01
measured, 8.54–9.04 the leaking architectural fills, 11.6–13.4 annotation cells. 8.0 is roughly a 2×
margin on the worst honest room and still below the best leak. It is **not applied to area** — doing
so moves a real Moxy suite by nearly sixty square feet, and whether those slivers are closets or a
cancelling error is a separate question (INV-01 §4). Nothing in this plan consumes it; 23-13 does.

**An oversize region is kept and flagged.** The hard drop it replaces emptied `enclosed` and returned
`None`, so a lobby, a ballroom or a retail floor plate produced **nothing at all** — and a drawing
that measured nothing is indistinguishable from an item that is genuinely zero. That is the silent
zero this phase exists to abolish (INV-02 §5). `MAX_REGION_SF` is unchanged at 900.0 and the bound
stays a parameter. The `dropped_regions` out-list still records the area, so the coverage ledger keeps
its `MEASURED_PARTIAL` record: the client sees the flag, the ledger sees the number, and neither
depends on the other (T-23-36).

**`flag_implausible_unit` stops erasing other flags.** It overwrote `review_reason` unconditionally,
so an oversize flag raised inside `measure_enclosed_area` was deleted by the very next call. A flag
that silently deletes another flag is the same defect as no flag at all.

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest -q` | **1637 passed, 2 deselected** (baseline 1601) |
| Four-set gate `tests/test_four_set_coverage.py` | green, unchanged (inside the full run) |
| `tests/test_room_fill.py` | **76 passed** (46 pre-existing kept, 3 rewritten, 30 added) |
| Moxy area probe diff, 19 RCP fills, `area_sf` + per-region lists | **EMPTY** |
| 16 pinned prototype areas, asserted as equality | pass |
| Dominant RCP shape ratio, 16 sheets | all in **[4.01, 5.28]** |
| AR leak signature, pages 23 / 27 / 29 | **8.62 / 9.04 / 8.54** — INV-01's values exactly |
| Regions failing to trace, whole prototype set | **0** (was 2 before the Task 3 fix) |
| Moxy p27 raw vs simplified perimeter | **< 1.5%**, anchored on the pinned 216.8 SF region |
| `MAX_REGION_SF == 900.0` | `constant value unchanged` |
| `'label_mask' in inspect.getsource(_label_regions)` | `projected` |
| `ast.parse(..., feature_version=(3,9))` | `py39 ok` on both files |
| `gitnexus impact` on `_label_regions` / `measure_enclosed_area` | **LOW** / **LOW**, run before editing |
| `gitnexus detect-changes` | run before each commit |
| `git diff --stat uploads/ human_inputs/ reports/` | **EMPTY** |

**No paid command was run.** `pytest -m golden`, `scripts/accuracy_gate.sh`,
`scripts/vision_only_benchmark.py` and `scripts/golden_convergence.py` were not executed; `.env` was
not read. Every number above came from a free offline probe or the offline suite.

### Impact analysis (CLAUDE.md), run before editing

| Symbol | Risk | Direct callers | Processes affected |
|---|---|---|---|
| `_label_regions` | LOW | 1 (`measure_enclosed_area`) | 2 |
| `measure_enclosed_area` | LOW | 1 (`_measure_room_fills`) | 2 |

Neither reported HIGH or CRITICAL, so no warning was owed.

## Deviations from Plan

### 1. [Rule 1 — bug] The trace's stopping criterion never fired on a real room

- **Found during:** Task 3, by the real-PDF assertion `test_every_prototype_sheet_reports_a_perimeter_at_all`.
- **Issue:** the criterion was the textbook phrasing — *stop when back at the seed with the seed's own
  initial backtrack (west)*. That assumes the ring passes through the seed the way the walk left it.
  On **Moxy page 35, `ACC KING TUB` RCP, the dominant 184.3 SF region**, the ring re-enters its seed
  heading **south**: the state *(seed, backtrack west)* lies on the walk's tail and never recurs. The
  walk ran to its 1.18-million-step cap and that room reported **no perimeter at all**. A second
  region on the same sheet's AR plan did the same. Instrumented directly: the walk's cycle is 2383
  steps and repeats the state reached at step 1, never the state at step 0.
- **Fix:** terminate on repetition of the **first transition** — the state a deterministic
  `(pixel, backtrack)` walk is guaranteed to return to. The iteration cap stays as the safety net it
  was always meant to be rather than as the thing that actually stops the walk.
- **Why this matters beyond the bug:** the cap did its job — the region was flagged
  `needs_review` with *"length is UNMEASURED, not zero"* rather than reporting a zero perimeter. The
  failure was visible instead of silent, which is the only reason a test caught it.
- **Commit:** `8133834`

### 2. [Rule 2 — missing critical functionality] A flag was deleting another flag

`flag_implausible_unit` assigned `review_reason` unconditionally, so the oversize flag raised one line
earlier in `measure_enclosed_area` was erased before any caller saw it. Reasons are now joined.
Pinned by `test_an_oversize_flag_is_not_erased_by_the_implausible_unit_flag`. Commit `8133834`.

### 3. [Decision] The plan's sixteenth pinned literal is wrong, and the measurement wins

The plan's acceptance criterion lists `451.0` for `ACC QQ RIS`. The shipped engine measures **451.1**,
and so did INV-01 §1 before this plan started. The test pins 451.1 — the value the **pre-change probe**
produced — because the invariance being asserted is *"the number did not move"*, and moving a
measurement to match a document would invert that. Every other one of the sixteen matches the plan
exactly.

### 4. [Decision] The P/A band is asserted over the sizes it was quoted for

The criterion asks for `perimeter / area` in `[0.20, 0.45]` per foot, described as *"the geometric
band for a rectilinear room of one hundred fifty to four hundred square feet"*. `P/A` is identically
`shape_ratio / sqrt(A)` — the same statement divided by a size — so the band is size-dependent by
construction. `KING A`'s dominant reflected-ceiling region is **121.8 SF**, below the band's own
stated premise, and an entirely honest ratio of 5.08 puts it at 0.461 by arithmetic alone. The band is
therefore asserted over `150 ≤ A ≤ 400` as quoted, and the identity `P/A == ratio/sqrt(A)` is pinned
unconditionally so the relationship cannot drift. **Widening the band to 0.47 would have been fitting
a threshold to an output**, which is exactly what D-07 forbids and what the rest of this plan is
built to avoid.

### 5. [Deviation from the plan's sequencing] The superseded tests were rewritten here, not left red

The plan says the currently-shipped tests asserting *"an oversize region is dropped"* are rewritten in
23-16 and expects them to fail meanwhile. Three tests encode that story
(`test_max_region_guard_rejects_sheet_scale_regions`,
`test_oversize_rejection_is_recorded_when_an_out_list_is_supplied`, and the oversize half of
`test_the_region_bound_is_threaded_and_defaults_to_the_module_constant`), not two. All three were
rewritten **in this plan**, in a file this plan already owns.

Leaving a red suite standing across seven plans would mean every plan from 23-10 to 23-15 executes
against a baseline that already fails, so any genuine regression they introduce arrives camouflaged.
The rewritten tests assert the new contract positively — kept, flagged, area preserved, reason names
the bound, out-list still populated — rather than merely deleting the old assertion. The offline gate
stayed green at every commit.

### 6. [Rule 3-adjacent, taken deliberately] `bytes.translate` for the ink classification

The per-pixel `for i in range(n_px)` loop that built the free mask is now a single
`samples.translate(table)`. Identical bits out (proved by the empty probe diff); the 19-page Moxy
probe went **83 s → 75 s**. Taken because the labeller is the acknowledged dominant cost (T-23-33)
and R11 explicitly forbids raising the render resolution to compensate — so the only permitted
direction is making the existing pass cheaper.

### 7. [Scope boundary — logged, NOT fixed] The ledger still says "rejected"

`_measure_room_fills` builds the coverage reason *"N region(s) … were rejected as larger than one
unit"*, and the out-parameter is named `dropped_regions`. Nothing is rejected or dropped any more.
Both live in `takeoff_pipeline.py`, which this plan is scoped out of. Logged as **DEF-23-10** for
23-11, which already owns that method. Purely cosmetic; the disposition
(`MEASURED_PARTIAL`) and the recorded area are both still correct.

### 8. [Scope boundary — logged, NOT fixed] The suite still rewrites three synthetic fixture PDFs

`tests/fixtures/synthetic/{dimensions,floorplan,symbols}_synthetic.pdf` come back modified after any
full-suite run. Pre-existing (23-08 deviation 6), unrelated, reverted rather than committed.

---

**Total deviations:** 2 auto-fixed (1× Rule 1, 1× Rule 2), 1 performance change taken deliberately,
3 decisions recorded, 2 logged and not fixed.

## Issues Encountered

**The real-PDF assertions are what found the bug.** The synthetic tests — rectangles, holes, ramps,
slivers, exact pixel ground truth — all passed against the broken stopping criterion, because a
rectangle's ring does re-enter its seed from the west. Only a real hotel room with a spur at its
topmost-leftmost pixel exposed it. The plan's insistence on blind real-PDF bands, rather than only
synthetic ones, is the reason this shipped correct.

**The module-scoped fixture costs ~70 s and is paid once.** `moxy_prototype_fills` measures Moxy pages
23–38 a single time and is shared by the area baseline, the perimeter existence check, the four
reflected-ceiling shape bands and the three architectural leak assertions. Measuring per test would
have cost about six minutes; the whole `test_room_fill.py` module runs in **83 s**. Total suite
movement: 25m31s → **26m35s**.

**The `to_dict` risk INV-01 §9 flagged turned out to be empty.** `RoomFillResult.to_dict` has no call
site in `src/` at all — the report and the learning store read the fill objects, not the dict. Adding
three keys is therefore additive with no consumer to break; a test pins that every pre-existing key
survives regardless.

## Known Stubs

None. Every function added is exercised against both synthetic exact-ground-truth fixtures and the
real Moxy PDF, and no threshold was moved.

**What is deliberately still absent:** `wall_perimeter_for_unit` and `wall_area_for_unit` (INV-01 §6
steps 5–6), the drawing-height resolver (step 7), and the `fusion._ROOM_FILL_BASES` gate (step 9).
Those are 23-13's, and this plan builds only the primitive they consume. **No wall area is produced
anywhere by this plan**, and `MAX_HONEST_SHAPE_RATIO` is published but has no consumer yet — that is
intentional, not an oversight: applying a shape gate is a measurement decision and it belongs with the
binder that bills the number.

## Threat Flags

None — no new network, auth, filesystem or schema surface. No new file is read or written; the same
pixmaps the engine already rendered are read once more.

Registered mitigations, all delivered:

- **T-23-33 (denial of service on a pathological many-component mask)** — the trace costs O(boundary),
  not O(area); the labeller runs once per clip; the min/max region filters bound the work; the render
  resolution constant is unchanged, and the ink classification got *cheaper*, not dearer.
- **T-23-34 (a Moore trace failing to terminate)** — a hard cap of `4 × px + 16`, an explicit
  isolated-pixel exit, and a component that hits the cap is flagged with *"length is UNMEASURED, not
  zero"* rather than looping. Pinned by `test_the_iteration_cap_flags_rather_than_looping` and
  `test_an_isolated_pixel_terminates_instead_of_spinning`. **This mitigation fired on real data during
  this plan** and is the reason deviation 1 was visible.
- **T-23-35 (perimeter work silently perturbing a shipped area)** — 16 pinned literals asserted as
  equality, an empty probe diff over 19 fills including every per-region list, and a labeller refactor
  that is a pure projection with the original return shape preserved.
- **T-23-36 (an oversize region disappearing with no trace)** — kept, counted, flagged with a reason
  naming the bound it exceeded, AND appended to the coverage out-list. Pinned by
  `test_an_oversize_region_is_kept_and_flagged_never_dropped` and
  `test_the_oversize_register_still_records_the_area_for_the_ledger`.

## Commits

| Task | Commit | Description |
|---|---|---|
| 1 | `c95c3ce` | One shared mask labeller that keeps its labels |
| 2 | `0842eee` | Outer-contour trace and a closed-ring-safe simplifier |
| 3 | `8133834` | Perimeter, a blind shape ratio, and kept-and-flagged oversize regions |

## Requirement status

`V4-MEAS-01` is **advanced, not completed** — left unticked, as 23-02 … 23-05 and 23-08 did with
theirs.

The requirement reads *"Room fills bind to takeoff line items for ceiling area (RCP basis) AND wall
area (perimeter × height, AR basis)"*. The perimeter half of the blocker is gone — the primitive
exists, is measured, and is on every fill — but **no binding was built here**:
`fusion._ROOM_FILL_BASES` still excludes `wall_area`, and no wall height is resolved. Ticking the box
would claim a line item no client can see. 23-13 owns the binding.

## What this unblocks

- **23-13 (wall-area binder)** inherits `region_perimeters`, `region_shape_ratios` and a published
  threshold, and it inherits the warning that comes with them: `wall_area` binds to the **AR** raster
  by discipline, and the AR raster leaks on `KING A`, `KING SUITE B` and `QQ A` — 8.62, 9.04, 8.54,
  measured again this run. Expect flagged zeros on the first pass. That is the correct outcome;
  switching those to the RCP raster to dodge the leak is the discipline violation §14.3 warns against.
- **23-14 (elevation facade)** inherits `label_mask` as its silhouette-complement labeller. It must
  call it, not fork it — D-03, and the reason the labeller was written blind to which polarity it was
  handed.
- **23-11 (geometric clip cell)** inherits **DEF-23-10** and a `_measure_room_fills` whose oversize
  path no longer deletes a drawing's whole measurement.

**The standing caution applies.** A perimeter is not a wall area. Summing every region's outer
perimeter counts a partition between bedroom and bath twice, once per face, which is right if the
estimator bills board faces and wrong if they bill wall length once. INV-01 §9 names this as an open
modelling question, and it is resolved by reading how the estimator's legend describes the item — **not
by trying ratios until a total matches**.

## Self-Check: PASSED

- `src/bobbytailor/deterministic/room_fill.py` — FOUND
- `tests/test_room_fill.py` — FOUND
- `.planning/phases/23-measurement-engine-completion/deferred-items.md` — FOUND
- commit `c95c3ce` (Task 1) — FOUND
- commit `0842eee` (Task 2) — FOUND
- commit `8133834` (Task 3) — FOUND
- `git diff --stat uploads/ human_inputs/ reports/ .env docs/PIPELINE-GROUND-TRUTH.md` — EMPTY

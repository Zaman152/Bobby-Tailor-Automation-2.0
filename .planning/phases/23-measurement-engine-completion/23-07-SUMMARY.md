---
phase: 23-measurement-engine-completion
plan: 07
subsystem: deterministic/geometry + pipeline/measurement
tags: [rotation, page-space, SP-1, coordinate-transform, room-fill, printed-scale, BUG-C, four-set-gate, INV-03, INV-04]
status: complete

requires:
  - phase: 23-02
    provides: "the anchored _paper_inches parse — Bob's callouts had to read 10.667 and 8.0 before binding them to the right viewport could mean anything"
  - phase: 23-03
    provides: "_measure_room_fills returning (fills, drops) and measure_enclosed_area(dropped_regions=...) — every recovery and every remaining skip in this plan lands as a named DrawingCoverage"
provides:
  - "room_fill.to_page_space(page, rect) — THE single drawing-space -> page-space transform for the engine (D-03)"
  - "room_fill.from_page_space(page, rect) — its exact inverse"
  - "measure_enclosed_area: one contract — the clip is drawing space, mapped internally before the pixmap call"
  - "takeoff_pipeline._page_space_point / _page_space_box — thin adapters over the one transform"
  - "_measure_room_fills(max_region_sf=MAX_REGION_SF) — the region bound is threaded, not a module constant"
  - "match_scales_to_viewports(printed_scales, viewports, page=None) — rotation-aware containment and 'above' fallback"
  - "printed_scale._title_above(..., page=None, y1=None) — rotation-aware stacked-title search"
  - "scripts/geom_probe.py: rotation, resolved fpp, room fills with plan name/kind, per-viewport own printed scale, --json"
affects:
  - "23-09 (region geometry), 23-11 (clip cell), 23-12, 23-14 — all consume to_page_space; none may write a second copy"
  - "23-11 / 23-14 — max_region_sf is now a parameter, so a facade needs no constant edit"
  - "every rotated sheet in every future plan: Bob's 7, Moxy 11, Chelsea 4 of 83 pages"

tech-stack:
  added: []
  patterns:
    - "one contract, no space flag: measure_enclosed_area always takes drawing space and maps forward itself, so a future caller cannot pick the wrong space — the page-space caller maps back instead"
    - "identity by object, not by value: to_page_space returns the caller's own rectangle at rotation zero, so the unrotated majority is byte-identical rather than merely equal"
    - "the oracle moves with the engine: page_measurable_signal binds a title to a callout by the same rule, so it had to move in the same commit or the ledger would contradict the measurement"
    - "measure the census, do not inherit it: the plan's '76 of 83 unrotated' was wrong; counting the real PDFs gives 61 of 83"
    - "a negative control per fixture: every new rotation test was run against the pre-change source tree and shown to fail there"
    - "falsify the acceptance criterion rather than satisfy it by retuning: two criteria were traced to a different subsystem and logged, not forced"

key-files:
  created:
    - .planning/phases/23-measurement-engine-completion/23-07-SUMMARY.md
  modified:
    - src/bobbytailor/deterministic/room_fill.py
    - src/bobbytailor/deterministic/printed_scale.py
    - src/bobbytailor/pipeline/takeoff_pipeline.py
    - scripts/geom_probe.py
    - scripts/scale_probe.py
    - scripts/room_probe.py
    - tests/test_room_fill.py
    - tests/test_printed_scale.py
    - .planning/phases/23-measurement-engine-completion/deferred-items.md
    - .gitignore

key-decisions:
  - "measure_enclosed_area keeps ONE contract — its clip is drawing space and it maps forward itself. The alternative, a clip_space flag, would have let 23-11/23-12/23-14 add a caller that forgets it and is silently wrong on 22 of 83 pages. _measure_room_fills reasons in page space and maps back through from_page_space; both maps are the identity on an unrotated page, so the round trip costs nothing where it is not needed."
  - "from_page_space was added in Task 1 although the plan's artifact list names only to_page_space. A transform whose inverse lives nowhere forces every page-space caller to re-derive the matrix, which is the duplication D-03 exists to forbid — and Task 2 needs the inverse by construction."
  - "A point is mapped through the rect transform via a degenerate rectangle rather than a second point-shaped copy of the rotation matrix. D-03 allows exactly one implementation; a rigid rotation sends the corners of a zero-area rect to the mapped point."
  - "The adjacency guard's -6.0 pt tolerance and the 260 pt side band are untouched and pinned by a test. Widening the tolerance would have 'fixed' Moxy by letting a callout ABOVE a title bind to it, moving unrotated sheets and binding wrong scales — the defect is the coordinate space."
  - "page_measurable_signal was fixed in the same commit as the engine (deviation 1). Moving only the engine made the skip veto's own oracle report ZERO measurable drawings on a page the engine measures at 743 SF — a silent zero wearing a coverage number, introduced by this plan."
  - "The plan's '76 of 83 pages are unrotated' is wrong and was not repeated. Counting the four PDFs gives 61 unrotated / 22 rotated: INV-03 counted Bob's 7 and Moxy's 11 but never counted Chelsea's 4. The invariance claim is unchanged and stronger for being measured — ZERO unrotated pages moved."
  - "Two of Task 3's acceptance criteria were NOT met and were logged as DEF-23-08 rather than forced. The page-level scale on Bob's p3 is decided by select_main_plan / _MAIN_PATTERNS, not by viewport binding, and `1 ROOF PLAN` sits ~1,900 pt to the LEFT of its callout on the same baseline — no rotation-correct _title_above can pair them. Satisfying the criterion would have required adding 'roof plan' to _MAIN_PATTERNS or widening _TITLE_X_TOL_PT 16x, both of which are the retune-a-constant trap 23-CONTEXT forbids."
  - "V4-MEAS-03 is ADVANCED, not completed — left unchecked, following 23-02/23-03/23-04/23-17. This plan removes the last coordinate blocker under it; the requirement's own subject (elevation wall-area SF and civil linework LF) is delivered by later plans in the phase."

requirements-completed: []
requirements-advanced: [V4-MEAS-03]

coverage:
  - id: D1
    description: "One page-space transform exists, is the identity when unrotated, and maps hand-computed corners at 90 and 270"
    requirement: V4-MEAS-03
    verification:
      - kind: unit
        ref: "tests/test_room_fill.py::test_to_page_space_is_the_identity_on_an_unrotated_page (4 rectangles, incl. two touching a page edge)"
        status: pass
      - kind: unit
        ref: "tests/test_room_fill.py::test_to_page_space_maps_the_hand_computed_corners_at_90_degrees / _at_270_degrees"
        status: pass
      - kind: unit
        ref: "tests/test_room_fill.py::test_a_rotation_preserves_area_and_lands_inside_the_displayed_page (T-23-25)"
        status: pass
      - kind: unit
        ref: "tests/test_room_fill.py::test_from_page_space_is_the_exact_inverse (rot 0/90/180/270)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The raster clip renders the region the caller named on a rotated page"
    requirement: V4-MEAS-03
    verification:
      - kind: unit
        ref: "tests/test_room_fill.py::test_the_raster_clip_renders_the_named_region_on_a_rotated_page"
        status: pass
      - kind: other
        ref: "Bob's page 4, real PDF: the raw rect renders Rect(0, 1152, 2058, 1616) in drawing space — 20.6% overlap with the named Rect(1152, 102, 1616, 2353); through the helper it renders the named rect exactly, carrying the drawing's own 83 words (INV-03 §3.4's count)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Unrotated measurement is byte-identical"
    requirement: V4-MEAS-03
    verification:
      - kind: integration
        ref: "Moxy pages 23-38 (16 sheets), pre- vs post-change room fills: byte-identical; the four INV-03 areas still read 229.4 / 341.7 / 272.6 / 274.6"
        status: pass
      - kind: integration
        ref: "all 83 pages of all four sets, room fills + geometry + per-viewport scale: ZERO of the 61 unrotated pages moved"
        status: pass
    human_judgment: false
  - id: D4
    description: "Rotated sheets bind their scales and measure"
    requirement: V4-MEAS-03
    verification:
      - kind: integration
        ref: "Moxy p9 LEVEL 1 LOBBY - AR PLAN 355.4 SF (> 300) + FF 387.7 SF, from empty; p10/p11/p13/p14 likewise; p12's FF 24.3 -> 220.4 SF"
        status: pass
      - kind: unit
        ref: "tests/test_room_fill.py::test_the_same_sheet_measures_the_same_whether_it_is_rotated"
        status: pass
    human_judgment: false
  - id: D5
    description: "A drawing binds the scale printed beneath IT, not a neighbour's"
    requirement: V4-MEAS-03
    verification:
      - kind: integration
        ref: "Bob's p3: the roof-plan viewport 1.0 -> 10.666667 ft/in and the VENT PIPE DETAIL's 1.0 goes to the detail viewport (INV-04 BUG-C); p4's three elevations get their own 8.0"
        status: pass
      - kind: unit
        ref: "tests/test_printed_scale.py::test_a_rotated_sheet_binds_the_drawing_the_label_sits_under_when_read"
        status: pass
      - kind: unit
        ref: "tests/test_printed_scale.py::test_a_stacked_title_is_found_above_the_ratio_as_the_sheet_reads"
        status: pass
    human_judgment: false
  - id: D6
    description: "The shared binding change does not move an unrelated drafting office (T-23-26)"
    requirement: V4-MEAS-03
    verification:
      - kind: integration
        ref: "four-fixture diff: crow 0/4 pages move, moxy 6/40 (all rot 90, all recoveries), chelsea 1/32 (p0, rot 270, no geometry effect), bobs 4/7 (all rot 270)"
        status: pass
      - kind: integration
        ref: "D-05 gate tests/test_four_set_coverage.py — moxy 2 (ceiling 2), crow 0 (==0), bobs 1 (==1), chelsea 0 (ceiling 2), silent loss 0"
        status: pass
      - kind: unit
        ref: "tests/test_printed_scale.py::test_the_page_argument_is_optional_and_none_defaulted / test_supplying_a_page_never_changes_an_unrotated_binding"
        status: pass
    human_judgment: false

metrics:
  duration: ~4h
  completed: 2026-08-03
  tasks: 3
  commits: 3
  tests_added: 26
  suite: "1557 passed, 2 deselected (baseline 1531)"
---

# Phase 23 Plan 07: Page-Space / Rotation-Correct Coordinate Transform Summary

**`page.get_text` and `page.get_drawings` answer in the unrotated mediabox; `page.get_pixmap`, and
every "which drawing sits above this label" judgement, live in `page.rect`. On the 22 rotated pages
of the four fixtures those are different spaces, and three live consumers were asking a question
about a space nobody looks at. Six Moxy sheets that returned NOTHING now measure, one that published
24.3 SF now measures 220.4, and Bob's roof plan binds its own 10.667 callout instead of a vent-pipe
detail's 1". Zero of the 61 unrotated pages moved.**

## Performance

- **Duration:** ~4h
- **Tasks:** 3 of 3
- **Files modified:** 10 (0 source files created) — 811 insertions, 24 deletions

## What shipped

**One transform, and its inverse (`room_fill.py`).** `to_page_space(page, rect)` maps a rectangle
from the space `get_text`/`get_drawings` report into `page.rect`, via `page.rotation_matrix`.
`from_page_space` is its exact inverse. Both **return the caller's own object** when the page
rotation is zero, so the unrotated majority is byte-identical rather than merely equal — that is the
whole safety argument for a transform applied at four consumer sites at once, and it is asserted with
`is`, not `==`. Neither ever raises: a page that cannot answer (a test stub, a defective file) yields
the input unchanged, which is exactly today's behaviour.

**`measure_enclosed_area` has ONE contract.** Its clip is in drawing space and it maps forward
itself, immediately before the pixmap call. The alternative — a `clip_space` flag — would have let a
future caller in 23-11/23-12/23-14 forget it and be silently wrong on 22 of 83 pages. The one caller
that *reasons* in page space maps back through `from_page_space` instead; both maps are the identity
where they are not needed, so the round trip is free.

**`_measure_room_fills` decides "beneath" as the sheet is READ.** The title box, the callout centre,
the adjacency gap and the clip are all computed in page space. The guard's `-6.0` pt tolerance and
the 260 pt side band are **untouched and pinned by a test**: widening the tolerance would have made
Moxy pass by letting a callout *above* a title bind to it, moving unrotated sheets. `max_region_sf`
is threaded through to `measure_enclosed_area`, defaulting to exactly `room_fill.MAX_REGION_SF`, so
23-11 and 23-14 can bound a facade without editing a constant every guest room shares — and a test
proves the argument reaches the measurement rather than being decorative.

**`match_scales_to_viewports` and `_title_above` take an optional, `None`-defaulted `page`.** Given
one, the containment test, the "region directly above the label" fallback and the stacked-title
search all run on page-space rectangles; given nothing, behaviour is exactly today's. The page is
passed from the four call sites that have one — `_deterministic_bundle`, `page_measurable_signal`,
`scale_probe.py` and `room_probe.py`. Viewport boxes are mapped **once per viewport**, not once per
(viewport, label) pair, so a page's label count cannot make the binding quadratic.

**`geom_probe.py`** now reports page rotation, the resolved feet-per-point, every room fill with its
plan name and kind, and each viewport's own printed scale, plus a `--json` mode so the four-fixture
diff is machine-checked rather than eyeballed. Fields are emitted from one flat per-page record, so
23-RESEARCH §5.1's later additions are cheap.

## Measured results (all free, zero API)

### The bug, on Bob's page 4

The clip for `FRONT ELEVATION NEW` is `Rect(1152, 102, 1616, 2353)` in drawing space. Handed straight
to the rasteriser it renders — expressed back in drawing space — `Rect(0, 1152, 2058, 1616)`: a
2058x464 band across the whole sheet instead of the 464x2251 drawing, **20.6% overlap** with the
region the caller named. Through the helper it renders the named rect exactly, carrying the drawing's
own **83 words** — the same count INV-03 §3.4 measured inside that viewport.

### Room fills: six Moxy sheets, all `/Rotate 90`

| Page | Before | After |
|---|---|---|
| 9 | (empty) | LEVEL 1 LOBBY - AR 355.4 SF, - FF 387.7 SF |
| 10 | (empty) | LEVEL 01 LOBBY - RCP 476.4 SF, LEVEL 1 LOBBY - FC 353.6 SF |
| 11 | (empty) | LEVEL 1 LOBBY - EM 358.9 SF |
| 12 | POP-UP HUB - FF **24.3 SF** | - AR 66.4, - FF **220.4**, - RCP 275.5 SF |
| 13 | (empty) | LEVEL 07 BAR - AR 78.7 SF |
| 14 | (empty) | LEVEL 07 ROOFTOP BAR - RCP 77.6 SF |

The 355.4 and 387.7 are INV-03 §4.2's page-space prototype figures to the decimal, reproduced by
production code. **Page 12 is the one that matters most:** it was not silent, it was *wrong* — the
sideways clip caught a 24.3 SF fragment of a 220.4 SF drawing and published it.

### Scale binding: Bob's, all `/Rotate 270`

| Page | Before | After |
|---|---|---|
| 1, 2 | no viewport had an own scale; page fpp 0.146850 (RANSAC) | R1 = 10.666667; page fpp **0.148148** (the PRINTED value) |
| 3 | main roof-plan viewport = **1.0** (a VENT PIPE DETAIL's callout) | roof plan = **10.666667**; the 1.0 goes to the detail viewport |
| 4 | one spurious 2.0 binding | the three elevations get their own **8.0** |

Pages 1-2 moving from 0.146850 to 0.148148 is the printed scale displacing a RANSAC estimate they
disagree by 0.88% — and INV-03 §4.1 independently corroborates 10.667 as the true value.

### The four-fixture diff — every page, against the pre-change source tree

| Set | Pages | Pages that moved | Unrotated pages that moved |
|---|---|---|---|
| Crow | 4 | **0** | 0 |
| Moxy | 40 | 6 (all `/Rotate 90`, all room-fill recoveries) | **0** |
| Chelsea | 32 | 1 (p0, `/Rotate 270` — one viewport gains an own scale; no geometry, fill, drop or disposition change) | **0** |
| Bob's | 7 | 4 (all `/Rotate 270`) | 0 |

**ZERO of the 61 unrotated pages moved.** That is T-23-26's mitigation, measured rather than
asserted.

### D-05 four-plan-set gate — run, not reasoned about

CONTEXT is explicit that a scale change must run this gate because a change to which callout binds to
which viewport can move a page's measurable signal and therefore its disposition.

| Set | Pre-veto skips | Skips now | Ceiling | Silent loss |
|---|---|---|---|---|
| Moxy | 18 | **2** (pages 0, 1) | ≤ 2 | 0 |
| Crow | 0 | **0** | == 0 | 0 |
| Bob's | 1 | **1** (page 0) | == 1 | 0 |
| Chelsea | 0 | **0** | ≤ 2 | 0 |

## A correction to the plan's own premise

The plan's must-have reads *"The seventy-six unrotated pages across the four fixtures take a
literally unchanged code path."* **That census is wrong.** Counted directly from the four PDFs:

| Set | Pages | Rotated |
|---|---|---|
| Crow | 4 | 0 |
| Bob's | 7 | 7 (all 270) |
| Moxy | 40 | 11 (pages 7-17, all 90) |
| Chelsea | 32 | **4** (pages 0, 19, 20, 21, all 270) |
| **Total** | **83** | **22** |

**61 unrotated, not 76.** INV-03 counted Bob's 7 and Moxy's 11 and never looked at Chelsea, so four
rotated Chelsea pages were invisible to the plan — and Chelsea page 0 is exactly the one non-Bob's
page the change moved. The invariance claim is unchanged and stronger for having been measured on all
83 rather than assumed for 76.

## Deviations from Plan

### 1. [Rule 1 — Bug] The skip-veto oracle drifted from the engine it is the oracle for

- **Found during:** Task 2, running `gitnexus detect-changes` before committing.
- **Issue:** `page_measurable_signal` binds a title to its callout with **the same rule** as
  `_measure_room_fills` — its comment says so in as many words: *"One definition, so the oracle cannot
  drift from the thing it is the oracle for."* Moving only the engine into page space broke exactly
  that. Measured on the real PDF: Moxy p9 `plan_titles = 0` from the oracle while the engine measured
  **two drawings totalling 743 SF**; p10 0 vs 2, p11 0 vs 1, p12 1 vs 3. The skip veto's first trigger
  reads that count, so the classifier could have discarded a lobby sheet the engine now measures — a
  silent zero wearing a coverage number, and one this plan would have introduced.
- **Fix:** the same page-space mapping in `page_measurable_signal`, via the shared
  `_page_space_box` / `_page_space_point` adapters. Oracle and engine now agree on **every** page of
  Moxy 7-17 and 23-38 (0 drifting pages).
- **Pinned by:** `test_the_skip_veto_oracle_cannot_drift_from_the_engine_it_measures` (rot 0 and 90).
- **Commit:** `1c97082`

### 2. [Decision] `from_page_space` was added although the artifact list names only `to_page_space`

A transform whose inverse lives nowhere forces every page-space caller to re-derive the rotation
matrix — which is the duplication D-03 exists to forbid — and Task 2 needs the inverse by
construction, because `_measure_room_fills` reasons in page space and `measure_enclosed_area` speaks
drawing space. Adding it in Task 1 kept both in `room_fill.py`, which is Task 1's file; Task 2's file
list does not include `room_fill.py`.

### 3. [Decision] `.gitignore` gained `scratch_*.json`

`geom_probe.py` writes `scratch_geom_probe.json` on every run and always has; running the extended
probe left it untracked. Per the commit protocol a generated runtime output is gitignored rather than
committed.

### 4. [Scope boundary — logged, NOT fixed] DEF-23-08 and DEF-23-09

Two of Task 3's acceptance criteria are not met. They are recorded in `deferred-items.md` with the
traces that falsify them, rather than forced:

- **DEF-23-08** — *"`geom_probe` reports page 3 feet-per-point of 0.148148"* and *"`scale_probe`
  reports page 3 with a resolved main scale"*. The **viewport** binding is fixed (1.0 → 10.667); the
  **page-level** scale is not decided by it. `select_main_plan` and `identify_main_plan_scale` both
  return `None` on that sheet, so `resolve_scale_v2` falls through to the text-scan tier, which
  answers 1 ft/in. Two independent blockers, both measured: `_MAIN_PATTERNS` has no `roof plan`, and —
  contrary to the plan's expectation that rotation-correctness would let the identifier "find the
  roof-plan title it currently cannot see" — the block `1 ROOF PLAN` sits at page-space
  `(120, 2096)-(314, 2121)` while its callout is at `(2178, 2100)-(2286, 2115)`: **the same baseline,
  ~1,900 pt apart**. `_title_above` requires ≤ 40 pt above and ≤ 120 pt of x-slack, so no
  rotation-correct version of it can pair them. Closing this needs either `roof plan` in
  `_MAIN_PATTERNS` (which moves main-plan identification on all four sets) or a new side-by-side
  binding rule — both are the retune-a-constant trap 23-CONTEXT forbids, and neither is a
  coordinate-space defect.
- **DEF-23-09** — the "region directly above the label" fallback has no distance bound. Chelsea p0's
  `R5` gained a scale from a callout **947 pt away**. The unbounded distance is pre-existing; this
  plan changed only which axis "above" is measured on. A distance cap is a new constant that would
  move unrotated sheets, which is what T-23-26's whole argument rests on not doing.

**Bob's p3 is not a regression.** Its roof-plan viewport now disagrees with the resolved page scale
by 10.7x, so the multi-scale guard excludes it and 23-03 records the exclusion with its reason.
Before, the viewport agreed with the wrong resolved scale and was measured 10.7x too small linearly.
Measured either way the quantities are identical (`n_walls` 1, `wall_lf_by_class {'TC1': 30.5}`,
`footprint None`) — the sheet yields almost no vector wall geometry. Net: one honest exclusion record
gained, no quantity lost, which is the direction 23-CONTEXT asks for.

---

**Total deviations:** 1 auto-fixed (Rule 1), 2 decisions recorded, 2 logged and not fixed.

## Issues Encountered

**Every new rotation test was run against the pre-change source tree first.** A `git archive` of
`7787941` into a scratch directory gave a clean pre-23-07 `src/`, and the Task 2 fixture measured
`295.6 SF` flat and **nothing** rotated there — so the assertion is known not to be vacuous. The same
tree produced every "before" column in this document; no baseline was regenerated by the code under
test.

**The synthetic PDF fixtures dirty the tree on every suite run.** `tests/fixtures/synthetic/*.pdf`
come back modified (same size, different bytes — PyMuPDF embeds a creation timestamp) after any
`pytest -q`. They were restored before each commit and never staged. This is DEF-23-06, pre-existing.

## Known Stubs

None. Every path is production code exercised against the real PDFs. Two things are deliberately
absent and named above: the page-level scale resolution on Bob's p3 (DEF-23-08) and a distance bound
on the viewport fallback (DEF-23-09).

## Threat Flags

None — no new security-relevant surface. The register's dispositions were carried out:

- **T-23-25 (a crafted rotation makes a clip render an unintended region)** — mitigated: a single
  helper with an identity path at rotation zero, unit-tested against hand-computed corners at 90 and
  270, plus an area-preservation and on-page containment assertion over four rectangles including two
  touching a page edge.
- **T-23-26 (the shared binding change silently moves an unrelated drafting office)** — mitigated and
  *measured*: every new parameter is optional and `None`-defaulted, and the four-fixture
  before-and-after diff over all 83 pages shows **zero** unrotated pages moving, Crow entirely
  unchanged, and Chelsea's single moved page carrying no geometry effect.
- **T-23-27 (a mapped rectangle covers the whole rotated page)** — mitigated: `get_pixmap` still
  intersects the mapped clip with the page rectangle, a rotation is area-preserving (asserted), and no
  render-resolution or clip constant was touched.
- **T-23-28 (a drawing skipped for want of a bound scale leaves no record)** — already delivered by
  23-03; this plan's remaining Moxy p13/p14 skips (`LEVEL 7 - AR/RCP PLAN`) come back as named
  `DrawingCoverage` drops, not as silence.

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest -q` | **1557 passed, 2 deselected** (baseline 1531; +26 tests) |
| Suite green before every commit | 1545 / 1550 / 1557 — Task 1, Task 2, Task 3 |
| D-05 gate `tests/test_four_set_coverage.py` | **14 passed** — Moxy 2, Crow 0, Bob's 1, Chelsea 0, silent loss 0 |
| Moxy 16-sheet RCP baseline (pages 23-38) | byte-identical; 229.4 / 341.7 / 272.6 / 274.6 unchanged |
| Moxy p9/p13 recovery | non-empty; `LEVEL 1 LOBBY - AR PLAN` **355.4 SF** (> 300) |
| Four-fixture room-fill + geometry diff, all 83 pages | 0 unrotated pages moved |
| Four-fixture `main` + per-viewport scale diff | Crow 0/4, Moxy 0/40, Chelsea 1/32, Bob's 4/7 |
| `max_region_sf` threaded, default `== MAX_REGION_SF` | `threaded, default unchanged` |
| `page` optional and `None`-defaulted | `optional, None-defaulted` |
| Negative controls against the pre-change tree | rotated fixture measured nothing; unrotated-space binding demonstrably wrong |
| `gitnexus detect-changes` | run before each of the three commits |

**Impact analysis was run before editing, per CLAUDE.md. Two targets came back CRITICAL and one HIGH;
they are reported here as required.**

| Symbol | Risk | Direct | Processes | Mitigation |
|---|---|---|---|---|
| `match_scales_to_viewports` | **CRITICAL** | 2 | 5 — `run_sheet`, `_run_sheet_vector`, `_deterministic_bundle`, `page_measurable_signal`, `run_pdf_analysis` | `page` is optional and `None`-defaulted; the two paths converge by construction at rotation zero. Four-fixture diff over all 83 pages: 0 unrotated pages move, Crow entirely unchanged. |
| `_title_above` | **CRITICAL** | 1 | 5 — same chain via `extract_printed_scales` | Both new parameters `None`-defaulted; the page is supplied only from `extract_printed_scales`, which always has one. Moxy — 40 sheets of bare ratios, the heaviest user of this path — is byte-identical on scale binding. |
| `_measure_room_fills` | **HIGH** | 1 | 3 | Every rectangle mapped by the one shared transform, identity when unrotated; `max_region_sf` defaults to the existing constant. Only rotated pages moved, and all 6 movements are recoveries or corrections. |
| `measure_enclosed_area` | LOW | 1 | 2 | One contract, mapped internally; the 16-sheet Moxy baseline is byte-identical. |

## Requirement status

`V4-MEAS-03` is **advanced, not completed** — left unchecked in `REQUIREMENTS.md`, following 23-02,
23-03, 23-04 and 23-17.

This plan removes the last coordinate-space blocker underneath it: an elevation clip on a `/Rotate
270` Bob's sheet now renders the facade rather than a band of unrelated sheet, and a drawing is
measured at the scale printed beneath *it*. But the requirement's own subject — elevation wall-area SF
and civil linework LF — is delivered by later plans in this phase. Checking the box here would claim
a client-visible quantity that no run yet emits.

## What this unblocks

23-09, 23-11, 23-12 and 23-14 all need a rotation-correct clip, and they now have exactly one to
consume — `room_fill.to_page_space`, with its inverse — instead of three copies of a rotation matrix
written independently, which is what four INV documents each proposed and what D-03 was written to
prevent. 23-11 and 23-14 can bound a facade through `max_region_sf` without touching a constant every
guest room shares.

More immediately: six Moxy sheets and four Bob's sheets that were invisible or mis-scaled are now
measurable inputs to every binder in Waves C and D. The standing caution applies — **743 SF of newly
measured Moxy lobby is not 743 SF of verified accuracy.** These are positions and scales validated
against each drawing's OWN printed callouts (INV-03's 355.4/387.7, INV-04's 10.667), never against a
golden quantity, and a paid validation run is the only thing that can confirm what a client receives.

## Commits

| Task | Commit | Description |
|---|---|---|
| 1 | `f958412` | The raster clip renders the region the caller named |
| 2 | `1c97082` | A callout is beneath a title as the SHEET IS READ |
| 3 | `85a70a1` | A drawing is measured at the scale printed beneath IT |

## Self-Check: PASSED

- `src/bobbytailor/deterministic/room_fill.py` — FOUND
- `src/bobbytailor/deterministic/printed_scale.py` — FOUND
- `src/bobbytailor/pipeline/takeoff_pipeline.py` — FOUND
- `scripts/geom_probe.py` — FOUND
- `scripts/scale_probe.py` — FOUND
- `scripts/room_probe.py` — FOUND
- `tests/test_room_fill.py` — FOUND
- `tests/test_printed_scale.py` — FOUND
- `.planning/phases/23-measurement-engine-completion/deferred-items.md` — FOUND
- `.gitignore` — FOUND
- commit `f958412` (Task 1) — FOUND
- commit `1c97082` (Task 2) — FOUND
- commit `85a70a1` (Task 3) — FOUND

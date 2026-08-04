# Phase 23 — deferred items

Out-of-scope discoveries logged during execution. NOT fixed in the plan that found them.

---

## DEF-23-13A — `king (t)` / `bunk (t)` / `ada (ris)` census tags do not match their full unit names

**Found during:** 23-13 Task 4 (room-mix probe on the real Moxy set).
**Where:** `room_tags.abbreviation_target` — the word-prefix rule (`every word of the census key is
a prefix of the corresponding word of the target`).

**Evidence (real, zero API):** the in-plan census reads `king (t)` = 3, `bunk (t)` = 1,
`ada (ris)` = 1 off the unit key plans, and the manifest declares `ACC KING TUB` = 3,
`ACC BUNK` = 2, `ADA KING RIS` = 1. None of the three tags match their full names under the
word-prefix rule (`king` is not a prefix of `acc`), so those counts fall back to the manifest
flagged as "NOT derived from the drawings" — even though the drawings appear to contain them
(`king (t)` = 3 agrees exactly with `ACC KING TUB` = 3). Consequence today: the 23-13
multiplier-review flag fires on ID-419 (ACC KING TUB, count 3, manifest-only) although the
drawings likely confirm the count. Honest but noisier than necessary.

**Why not fixed in 23-13:** matching `(t)`/`(ris)` suffix tags to full names is a NAMING rule
(abbreviation semantics), which is plan 23-15's scope; loosening the prefix rule ad hoc to quiet
one flag would risk false matches, the exact failure the unique-match rule exists to prevent.

## DEF-23-01 — `SCALE: 1-1/2" = 1'-0"` parses as 1/2, not 1 1/2

**Found during:** 23-02 Task 1 (printed-scale parser hardening).
**Where:** `src/bobbytailor/deterministic/printed_scale.py` — `_ANCH_MIXED_RE` requires
whitespace between the whole part and the fraction, so a HYPHENATED mixed number falls through
to the plain-fraction rule.

**Evidence (real, Bob's A8.3 page 6, two callouts):**

```
'SCALE: 1-1/2" = 1'-0"'   parses 1/2 -> 0.5 paper inches -> 2.0 ft/in
architecturally it is    1.5 paper inches            -> 0.6667 ft/in
```

**Why it was NOT fixed in 23-02:**

1. It is a **different defect** from BUG-A (split stacked fraction) and BUG-B (unanchored scan),
   which are 23-02's entire scope. It is wrong *before* the change too, so it is not a regression.
2. Correcting it moves 2 extra Bob's rows, making the four-fixture sweep `changed=9 unchanged=381`
   and breaking the `changed=7 unchanged=383` pin that 23-02 exists to establish (INV-03 §4.1).
   Verified by running exactly that experiment as a negative control.
3. D-07 forbids widening a parser rule without the before/after diff being re-derived and agreed.

**Pinned meanwhile:** `test_hyphenated_mixed_number_keeps_its_pre_change_value` asserts the
current 2.0, with the reason in the docstring, so the behaviour is documented rather than latent.

**To fix properly:** allow `[\s-]+` in `_ANCH_MIXED_RE`, re-derive the four-fixture sweep, and
update both the pinned totals and `tests/fixtures/printed_scale_pre_sp2.json`'s `_expected`.
Both affected callouts are on Bob's A8.3 STANDARD DETAILS (a detail sheet), so nothing measured
today depends on them — which is why this is safe to defer, not safe to ignore.

---

## DEF-23-02 — the offline suite rewrites tracked fixture PDFs

**Found during:** 23-02 Task 1, staging the first commit.
**Where:** `tests/fixtures/synthetic/dimensions_synthetic.pdf`,
`floorplan_synthetic.pdf`, `symbols_synthetic.pdf`.

Running `python3 -m pytest -q` leaves all three modified in the working tree — they are
regenerated on each run and the bytes differ (PyMuPDF writes a timestamp). This is pre-existing
(unrelated to the scale parser) and is the same class of problem commit `e2fa735`
("purge test-pollution") addressed for `output/`.

**Impact:** every `git status` after a test run shows spurious modifications, so a careless
`git add -A` commits churn — and it makes "is the tree clean?" useless as a check.

**To fix:** generate them into a tmp_path fixture, or add them to `.gitignore` and build them
in a session-scoped fixture. Not attempted in 23-02: it touches test infrastructure shared by
several suites and is unrelated to SP-2.

---

## DEF-23-03 — `main=None` on Bob's pages 3 and 4 after the scale fix

**Found during:** 23-02 Task 3, probe acceptance.

`scripts/scale_probe.py` now reports the correct per-callout values on Bob's
(`page 3 distinct_fpi=[1.0, 10.6667]`, `page 4 distinct_fpi=[2.0, 4.0, 8.0]`) but
`main=None` on both. This is **BUG-C**, the rotation-unaware callout↔viewport binding
(INV-04 §4 BUG-C): every Bob's page is `/Rotate 270`, and `match_scales_to_viewports`
implements "the label sits at the drawing's bottom" as `y1 <= cy` in *unrotated* space.

**Not a deferral — it is scheduled.** Plan 23-07 owns it, and 23-02's constraints explicitly
forbid starting it here. Logged only so the `main=None` reading in the probe output is not
mistaken for a defect introduced by SP-2. It is present identically before the change.

---

## DEF-23-04 — `test_max_region_guard_rejects_sheet_scale_regions` passes for the wrong reason

**Found during:** 23-03 Task 1, adding the `dropped_regions` out-list test.
**Where:** `tests/test_room_fill.py::test_max_region_guard_rejects_sheet_scale_regions`.

The fixture builds a 60' × 40' room at 1/4" = 1'-0", i.e. **1,080 × 720 pt**, on an **800 × 800 pt**
page starting at (100, 100). The room overflows the page, so its region **touches the clip edge**
and is discarded as "the outside" — the `max_region_sf` guard the test is named for is never
reached. Proven by instrumenting `measure_enclosed_area` with the new out-list: `dropped_regions`
comes back **empty**, which it could not be if the size filter had fired.

**Impact:** the assertion (`is None`) is correct, so nothing is broken today — but the test does not
in fact pin the behaviour it claims to, and would keep passing if `MAX_REGION_SF` were deleted.

**NOT fixed here** because rewriting an existing pin is out of this plan's scope (the change would
be indistinguishable from tuning a guard, which INV-08 risk 6 forbids without its own justification).
The new `test_oversize_rejection_is_recorded_when_an_out_list_is_supplied` draws its 1,200 SF region
at 1/8" so it genuinely fits on the page, and DOES exercise the size filter — so the behaviour is now
covered even though the older test remains vacuous.

**To fix:** redraw the fixture at a scale that fits the page (or enlarge the page) and assert
`dropped_regions` is non-empty, so the guard is what makes the test pass.

---

## DEF-23-05 — a non-HM door FRAME canonicalises into a DOOR bucket

**Found during:** 23-04 Task 3, checking the emitted item names against
`aggregator.ITEM_NAME_MAP`.
**Where:** `src/bobbytailor/pipeline/aggregator.py:119-126`.

`ITEM_NAME_MAP` has exactly ONE frame rule —
`hollow.?metal.*frame|frame.*hollow.?metal|frame.*\bhm\b|\bhm\b.*frame` → `Frame-HM` — and it fires
only for hollow metal. Every other frame material falls through to the DOOR rules below it:

| Emitted item | Canonicalises to | Correct? |
|---|---|---|
| `Door Frames-HM` | `Frame-HM` | yes |
| `Door Frames-AL` | `Doors-AL` (via `door.*alum`) | **no — a frame is billed as a door** |
| `Door Frames-STL` | `Doors` (generic catch-all) | **no** |

Measured: Bob's emits `Door Frames-AL 2`, Moxy emits `Door Frames-AL 5` and `Door Frames-STL 6`.
Those six-to-eleven units are currently added to a door line item.

**Impact is bounded and pre-existing.** `component_library` already emitted `Door Frames-AL` before
23-04 (`_MAT_CODE_ALIAS` mapped `ALUM → AL`), so this is not a regression — 23-04 only makes it
visible on two more plan sets. Neither Bob's nor Moxy's golden carries a non-HM frame row, so
nothing scores worse.

**NOT fixed here** because `aggregator.py` is not in 23-04's `files_modified`, and adding
`Frame-AL` / `Frame-STL` canonical names changes the item vocabulary every scored fixture matches
against — that is a naming decision with its own blast radius, not a door-schedule fix.

**To fix:** add generic frame rules (`frame.*\balum?\b` → `Frame-AL`, `frame.*\bstl\b|frame.*steel`
→ `Frame-STL`) ABOVE the door rules in `ITEM_NAME_MAP`, and re-score all four saved runs.

---

## DEF-23-06 — the synthetic fixture PDFs are rewritten by every test run

**Found during:** 23-04, staging each commit.
**Where:** `tests/fixtures/synthetic/{dimensions,floorplan,symbols}_synthetic.pdf`.

`git status` reports all three as modified after any full `pytest -q`, because the fixtures are
regenerated on use and PyMuPDF embeds a creation timestamp. The bytes differ, the content does not.

**Impact:** every run dirties the working tree, so a `git add -A` would sweep three unrelated binary
files into an unrelated commit. Pre-existing; not introduced by 23-04 (which staged files
individually, per the commit protocol).

**To fix:** generate them into `tmp_path` instead of the repo, or make the writer deterministic
(`doc.set_metadata({})` plus a fixed `creationDate`), then re-commit the fixtures once.

---

## DEF-23-07 — `door_schedule_coverage` has no production caller

**Found during:** 23-17, wiring the report-side surfacing.
**Where:** `src/bobbytailor/deterministic/schedule_extraction.py:1029`.

23-04 built `door_schedule_coverage(ds, absent_references)` and it returns exactly the right thing —
`ItemCoverage` dicts with `status=NOT MEASURED` / `NEEDS REVIEW`, `quantity=None`, and a reason that
says an input gap is an input gap. **Nothing in `src/` calls it.** `grep -rn door_schedule_coverage
src/bobbytailor/{pipeline,vision,web}` returns nothing; the only callers are its own warnings wrapper
and `tests/test_schedule_extraction.py`.

**Consequence:** Chelsea's "a door schedule is referenced on page(s) … but no parsable schedule table
exists in this PDF" record cannot reach `report["item_coverage"]`, the COVERAGE section, the CSV or
the workbook — because it is never produced during a run.

**Impact:** 23-04 named 23-17 as the plan that surfaces these records. 23-17 surfaces every
`ItemCoverage` (object OR dict) it finds on a sheet dict's `_item_coverage`, so the surfacing side is
done and waiting; the missing half is one call inside the pipeline's schedule path.

**NOT fixed here** because `takeoff_pipeline.py` and `schedule_extraction.py` are not in 23-17's
`files_modified`, and choosing the call site (which sheet's records, with which `absent_references`)
is a pipeline decision with its own blast radius rather than a report-rendering one.

**To fix:** where the pipeline builds a sheet's schedules, call `door_schedule_coverage(ds, …)` and
append the returned dicts to that sheet's `_item_coverage`. Nothing else is required — the report
already renders them.

---

## DEF-23-08 — Bob's page 3 binds its own scale but the SHEET still resolves 1.0 ft/in

**Found during:** 23-07 Task 3, verifying the plan's own acceptance criteria against the real PDF.
**Where:** `printed_scale.identify_main_plan_scale` (`_MAIN_PATTERNS`) and
`scale_solver.select_main_plan`.

23-07 fixed what it set out to fix: on Bob's page 3 the main roof-plan viewport now binds its **own**
`3/32" = 1'-0"` callout (10.667 ft/in) instead of a vent-pipe detail's `1"` callout, and the detail
callout binds to the detail viewport. That is INV-04 BUG-C, and it is closed.

The **page-level** resolved scale did **not** move: `geom_probe` still reports page 3
`fpp = 0.013889` (1.0 ft/in), not the 0.148148 the plan predicted. The viewport binding is not what
decides it. Traced on the real page:

```
main_id (select_main_plan)      -> None
identify_main_plan_scale(...)   -> None
resolve_scale_v2                -> 0.0138889  source: "printed notation only — unverified by
                                    dimensions"  (1 ft/in, share 100% of 1 scales)
```

With no main viewport and no main-plan printed scale, `resolve_scale_v2` falls through to the
text-scan tier (`scale_extraction.dominant_scale`), which is a different code path this plan never
touched.

**Two independent blockers, both measured, neither a rotation defect:**

1. `_MAIN_PATTERNS` is `('overall floor plan', 'floor plan', 'site plan', 'overall plan',
   'key plan')` — it has no `roof plan`, and page 3 is `A3.0 ROOF PLAN`.
2. Even with that word added, the title could not be found. The plan expected the rotation fix to let
   "the main-plan scale identification find the roof-plan title it currently cannot see". It cannot:
   the block `1 ROOF PLAN` sits at page-space `(120, 2096)-(314, 2121)` while its callout is at
   `(2178, 2100)-(2286, 2115)` — the **same baseline, ~1,900 pt apart horizontally**. `_title_above`
   requires a gap of ≤ 40 pt ABOVE and an x-overlap within 120 pt, so no rotation-correct version of
   it can pair them. The only block inside that window is `NORTH` (gap 23.8 pt), which is what the
   callout's title now reads.

**NOT fixed here.** Adding `roof plan` to `_MAIN_PATTERNS` changes main-plan identification on every
sheet of all four fixtures, and pairing a title to a callout on the same baseline is a NEW binding
rule (side-by-side, not stacked) with its own blast radius. Both are exactly the "retune a constant
and see if the number improves" move that 23-CONTEXT forbids, and neither is a coordinate-space
defect — which is all this plan is scoped to.

**Consequence today, and why it is not a regression.** Page 3's roof-plan viewport now carries an own
scale that disagrees with the resolved page scale by 10.7x, so the multi-scale guard **excludes** it
and 23-03 records the exclusion with its reason. Before this change the viewport agreed with the
resolved 1.0 and was measured at a 10.7x-too-small linear scale. Measured on the real page, the
quantities are unchanged either way (`n_walls` 1, `wall_lf_by_class {'TC1': 30.5}`, `footprint None`
before and after) — the sheet's roof plan yields almost no vector wall geometry. So the change is
one honest exclusion record gained and no quantity lost, which is the direction 23-CONTEXT asks for.

**To fix:** a plan that owns `scale_solver.select_main_plan` / `_MAIN_PATTERNS` should decide whether
a roof plan is a main plan, and whether a callout may claim a title beside it rather than above it —
gated, as always, on the four-set regression check.

---

## DEF-23-09 — the "region above the label" fallback has no distance bound

**Found during:** 23-07 Task 3, reading the four-fixture diff.
**Where:** `printed_scale.match_scales_to_viewports`, the non-containment branch.

Chelsea page 0 (`/Rotate 270`, the title sheet) is the ONE page outside Bob's that moved: viewport
`R5` gained an own printed scale of `0.333333` from a `DOOR DETAILS AT` callout **947 pt away** — 13
inches of paper. It binds only because `R5` is the sole non-mask viewport whose x-range overlaps the
label, and the "directly above" fallback ranks by nearest without ever asking *how far is too far*.

The unbounded distance is **pre-existing** — the same label could bind to a viewport 947 pt above it
in unrotated space too. This plan only changed which axis "above" is measured on, which is why the
page surfaced now rather than being caused now. Measured consequence on Chelsea page 0: no geometry,
no room fill, no drop and no coverage disposition changes; the four-set gate is green with Chelsea at
**0** skips against a ceiling of 2.

**NOT fixed here** because a distance cap is a new constant, and any value for it would move
unrotated sheets — which is precisely what this plan's whole safety argument (T-23-26) rests on not
doing. Choosing it needs its own four-set sweep.

**To fix:** cap the fallback distance at a justified multiple of the label height, or require the
label's x-span to overlap the viewport's rather than merely its centre, and re-run the four-set diff.

---

## DEF-23-10 — the coverage ledger still calls a KEPT oversize region "rejected"

**Found during:** 23-09 Task 3 (oversize regions kept and flagged).
**Where:** `TakeoffPipeline._measure_room_fills`, the `MEASURED_PARTIAL` branch — the reason string
reads *"N region(s) of X SF were rejected as larger than one unit"*.

As of this plan an oversize region is **not** rejected: it is kept, counted into `area_sf`, and the
result comes back flagged with a reason naming it. The out-list `dropped_regions` is still populated,
so the ledger still learns the fact and the disposition (`MEASURED_PARTIAL`) is still right — but the
verb is now wrong. The parameter name `dropped_regions` has the same problem at the API boundary.

**NOT fixed here** because 23-09's constraints scope it to `room_fill.py` and its tests; the string
and the call site both live in `takeoff_pipeline.py`, which is 23-11's file. Fixing it here would be
an untested edit to a module this plan does not exercise.

**To fix:** 23-11 (which already owns the clip cell in `_measure_room_fills`) should rename the
out-parameter to `oversize_regions` and reword the ledger reason to *"N region(s) of X SF exceed the
single-unit maximum and are included, flagged"*. Purely cosmetic; no measurement moves.

**Still open after 23-11.** That plan closed on its cross-check task alone (see DEF-23-SP4), so the
clip-cell work its nominated owner was attached to never happened and this rename went with it. It
carries forward to whichever plan next opens `_measure_room_fills`.

---

## DEF-23-11 — three Crow page-2 captions still bind to no viewport

**Found during:** 23-10 Task 3 (the schedule/drawing kind fix).
**Where:** `printed_scale.match_scales_to_viewports`.

Freeing the STAIR PLAN region took Crow page 2 from **4** unbound printed-scale labels to **3**.
Zero — which INV-06 §3.5 predicted — is not reachable from `viewports.py`, and two of the three have
nothing to do with viewport kinds:

1. **Pigeonhole.** `match_scales_to_viewports` keeps at most ONE label per region. Crow page 2 draws
   **13** captioned details into **11** non-title-block regions, so two labels cannot bind however
   the kinds are assigned. The segmenter merges some adjacent details into one region.
2. **The containment margin is symmetric.** A caption sits at its drawing's BOTTOM edge, but
   `_contains(..., margin=6.0)` also accepts a label just ABOVE a region's TOP edge. R4's top is
   `623` and `RAMP RAIL SECTION`'s caption is at `y=620`; R12's top is `1450` and `Z-GUARD DETAIL`'s
   is at `y=1445`. Both captions are therefore claimed by the drawing BELOW them, which already owns
   a nearer label, so they are dropped.

**NOT fixed here** because both live in `printed_scale.py`, which 23-10 does not touch, and because
either change is a shared-path edit that needs its own four-fixture before/after sweep. Neither
blocks 23-12: all five estimator rail marks already sit in an unmasked viewport bound to the scale
INV-06 measured them at.

**To fix:** make the containment margin asymmetric (slop below and sideways, none above the top
edge), and let a region own more than one caption when the labels are vertically separated — then
re-run the four-set scale diff.

---

## DEF-23-SP4 — what should a dimension-string corridor contribute to a room's measured area?

**Found during:** 23-11, prototyping the geometric clip cell (SP-4). It is the reason that plan
closed on its cross-check task alone.
**Where:** `room_fill.measure_enclosed_area` — the region filter at the `touches_edge` /
`MIN_REGION_SF` test — and every clip that feeds it.

**This is a DOMAIN question, not an engineering one, and it blocks SP-4 entirely.** No geometric clip
can be pinned against the current sixteen-sheet baseline until it is answered, because that baseline
is partly composed of the very thing in question.

### The evidence

`ID-407 KING A - RCP PLAN` measures **229.4 SF**, and that number is a sum of **eight** enclosed
regions. Three of them are not rooms — they are dimension-string corridors, the narrow channels
between a dimension line and the drawing it annotates (page-space bboxes, measured offline against
the real PDF):

```
   13.4 SF  bbox=(1049.5, 1397.8, 1060.7, 1767.7)   11 pt wide, 370 pt tall
    8.5 SF  bbox=(1245.2, 1399.1, 1254.2, 1690.7)    9 pt wide, 292 pt tall
   10.8 SF  bbox=(1617.4, 1399.1, 1626.4, 1768.6)    9 pt wide, 370 pt tall
  ---------
   32.7 SF  = 14% of the published 229.4 SF
```

They are the `11.6-13.4` shape-ratio band INV-01 §4 identified as "annotation and dimension cells",
and they clear `MIN_REGION_SF = 8.0` by a hair, which is why they survive the filter.

**Whether each one is counted depends entirely on where the fixed `±260 pt` clip's edge falls.** The
10.8 SF corridor sits at x 1617.4, and the nearest anchor-derived boundary lands at 1607.8 — so a
geometric clip cuts it, it touches the edge, and it is discarded. That single corridor is the whole
of the 229.4 → 218.6 SF movement observed in the 23-11 prototypes. INV-02 §3's own clip-width sweep
says the same from the other side: three sheets move 17-20% across a ±80 pt change of that constant.

**Consequence: a clip that no longer depends on a width constant cannot reproduce a number that
does.** The sixteen pinned RCP areas are a valid regression guard *for the current clip* and must be
left exactly as they are. They are NOT a specification a new clip can be measured against.

### The evidence that points to an answer

The estimator's own take-off appears to measure the ROOM and not the room plus its corridors.
`ID-411 KING SUITE B` golden reads **353.4 SF** against printed overall dimensions of
`17'-0" x 20'-7 1/8" = 350.1 SF` — a **0.9%** match. (The printed-dimension figure is measured;
the golden figure is quoted from the coordinator's reading of the take-off.)

**Answering this requires reading the TAKE-OFF DOCUMENTS, not the plans.** The plans state what is
drawn; only the take-off states what the estimator counted. One sheet is a coincidence — the pattern
needs confirming across several before anything is pinned.

### What comes after the answer

Once it is settled, SP-4 can be re-planned. 23-11 measured four clip-partition variants against all
sixteen prototype sheets and none reproduces the baseline; the three facts that falsify the
anchor-midpoint rule, and the two corrections to the plan's premises (INV-02 §5's strip collapse was
already fixed by 23-07; the ">900 SF largest region" criterion is likely unmeetable because an RCP is
subdivided by its own ceiling grid), are recorded in `23-11-SUMMARY.md` deviations 2 and 3. The
architecture that looked viable is per-drawing ink attribution in PAPER space — a wall is 2-8 pt of
paper and a layout gutter is tens of points, and that distinction is scale-free and
building-type-free — but it is a new plan, not a task.

**NOT fixed in 23-11** because the answer is not ours to choose. Fitting a clip until sixteen numbers
agreed would be the coincidence trap this phase exists to abolish, wearing a new costume.

## DEF-23-14A — a facade silhouette and a tilt-up perimeter x height row can double-represent one wall across SHEETS

**Found during:** 23-14 Task 4 (the elevation binder design).
**Where:** `fusion._fuse_wall_classes` (tilt-up: perimeter x height on the FLOOR-PLAN sheet, when a
vision label / vocabulary names a tilt-up wall_area class) vs `fusion._fuse_elevation_areas`
(facade silhouettes on the ELEVATION sheet).

**Evidence (real, zero API):** on Crow, the floor-plan sheet can bind `Tilt Up Wall` =
2,972 LF x height, while page 1 now emits four facade rows summing 133,478 SF. These are the SAME
exterior walls measured by two routes on two sheets. One-area-one-item arbitration is PER-SHEET
(`fuse_sheet`), so nothing arbitrates across the pair. Today the facade rows are flagged (no
text-anchored material on Crow) and the D-11 cross-check note names both figures, so the overlap is
visible, never silent — but an aggregator summing both under one item name would double-count.

**Why not fixed in 23-14:** cross-sheet arbitration is an AGGREGATION concern (the per-sheet
arbitration contract was deliberately scoped in 23-13), and suppressing the tilt-up binding would
break pinned 23-08/23-13 behaviour. The honest boundary shipped: the second route flags and
publishes no quantity on the elevation sheet; the cross-sheet dedupe belongs with the aggregator
(23-15/23-16 or Phase 24 scoring will surface it on the real Crow report).

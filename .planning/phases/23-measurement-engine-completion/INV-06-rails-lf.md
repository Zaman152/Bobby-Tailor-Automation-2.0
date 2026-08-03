# INV-06 — Rail LF is broken by ~100× (Crow blocker)

**Investigator deliverable: implementation map.** Read-only investigation; every behavioural claim
below is pasted probe output from a zero-API offline run against the real PDFs in `uploads/`.

---

## TL;DR

Rail LF is **two independent defects that happen to land in the same row**, not one:

1. **The nonzero number is a phantom.** The 3–7 LF the pipeline reports is *not* a measurement of
   anything. It is the rail's **pipe diameter in INCHES** (`1 1/2" O.D. STEEL PIPE GUARDRAIL`) read
   off the detail sheet as a dimension annotation and pushed through
   `calculator._apply_formula()`, whose LF branch (`calculator.py:1263-1266`) **ignores the `unit`
   argument entirely** and returns `value × waste_factor` stamped `"lf"`. `1.5 in → 1.54 LF`.
   Verified by direct call, below. Saved run totals: `guard_rail 5.78`, `hand_rail 4.74`, reported
   as `Guardrail 5.8 LF / Handrail 4.7 LF` with `needs_review=False`.
2. **The real measurement was never attempted.** There is no linear-run geometry candidate anywhere
   in the engine. `_deterministic_bundle()` returns
   `symbol_groups / walls / wall_lf_by_class / rooms / room_fills / viewports / schedules /
   footprint` (`takeoff_pipeline.py:1749-1760`) — no open-run candidate — and `fuse_sheet()` has
   seven binders (`fusion.py:1911-1927`), none of which consumes measure-basis `linear`. The
   component library **already names the item correctly and deterministically** (`Guard Rail`,
   basis `linear`, unit `LF`, `source: keynote` — proven below), so this is §12b's exact shape:
   *the name existed, the unit existed, the measurement step did not exist, so it reported ~0.*

**The rail linework does exist and IS measurable.** A prototype open-run extractor
(angle-constrained chaining + parallel-pair collapse), run on Crow **page 2** detail viewports at
**each viewport's own printed scale**, reproduces the estimator's own measurement marks **by
position**, e.g. `53.00 LF @ bbox (275,167)-(1229,167)` vs the estimator's `53.10 LF @
bbox (273,167)-(1229,167)` — 0.2% apart, same pixels.

**The honest ceiling.** Golden Guard Rail 420.35 LF / Hand Rail 438.80 LF are **per-instance detail
lengths × an instance multiplier the drawings do not print**. The estimator drew only **5**
measurement polylines totalling ~90.6 LF at printed scale; the golden totals are ~6× and ~21×
those. So the fix path is: measure the per-instance rail run deterministically (achievable now,
position-validated), and emit it with `unit_count=None` + `needs_review` — exactly the
`_fuse_room_fills` / `room_mix` contract (`fusion.py:1516-1600`). **Do not** tune a multiplier to
land on 420/438; that is §10's coincidence trap.

---

## 1. Evidence

All probes are zero-API. Scripts live in the session scratchpad (paths given); the code is
reproduced inline so any of it can be re-run without them.

| Probe | File |
|---|---|
| page-0 linework + rail text anchors | `…/scratchpad/rail_probe.py` |
| estimator markup → viewport → own scale | `…/scratchpad/rail_probe2.py` |
| naive open-run extraction per detail | `…/scratchpad/rail_probe3.py` |
| page-0 ramp regions | `…/scratchpad/rail_probe4.py` |
| **refined extractor (the recipe)** | `…/scratchpad/rail_probe5.py` |

(scratchpad root: `/private/tmp/claude-501/-Users-muhammadumer-…/scratchpad/`)

### 1.1 The phantom LF, reproduced from the production functions

```
$ python3 -c "... from bobbytailor.pipeline.calculator import ..."
_convert_units(1.5, in) -> (1.5, 'in')
_classify_item(...) -> guard_rail
_apply_formula(guard_rail,1.5,in) -> (1.545, 'lf', '2 lf × 1.03 = 2 lf')
ROW -> {'item_type': 'guard_rail', 'raw_value': '1.5', 'raw_unit': 'in',
        'quantity': 1.54, 'unit': 'lf', 'formula': '2 lf × 1.03 = 2 lf'}
ROW2-> {'item_type': 'hand_rail',  'raw_value': '1.5', 'raw_unit': 'in',
        'quantity': 1.58, 'unit': 'lf', 'formula': '2 lf × 1.05 = 2 lf'}
```

The rounded formula string (`"2 lf × 1.03 = 2 lf"`) actively hides the unit error in the audit
trail. Matching rows in the last saved Crow run
(`output/VisionOnly_Crow_F2_20260715_082130/calculations.csv`):

```
guard_rail,Steel pipe guardrail outer diameter,1.5,in,1.54,lf,1.03,...,"1 1/2"" O.D. STEEL PIPE GUARDRAIL"
guard_rail,Steel pipe guardrail outer diameter,1.125,in,1.16,lf,1.03,...,"1 1/8"" O.D. STEEL PIPE GUARDRAIL"
hand_rail, Handrail O.D. pipe diameter,        1.5,in,1.58,lf,1.05,...,"1 1/2"" O.D. HANDRAIL"
guard_rail,Guardrail O.D. pipe diameter,       1.5,in,1.54,lf,1.03,...,"1 1/2"" O.D. GUARDRAIL"
guard_rail,Guardrail O.D. pipe diameter,       1.5,in,1.54,lf,1.03,...,"1-1/2"" O.D. GUARDRAIL"
hand_rail, Handrail pipe diameter,             1.5,in,1.58,lf,1.05,...,"1 1/2"" O.D. PIPE GUARDRAIL"
hand_rail, Handrail pipe diameter,             1.5,in,1.58,lf,1.05,...,"1 1/2"" O.D. HANDRAIL @ CONC. SLAB"
sums: {'guard_rail': 5.78, 'hand_rail': 4.74}
```

and the report they produced:

```
Guardrail                             5.8 LF     src=library    review=False
Handrail                              4.7 LF     src=library    review=False
```

Every one of the seven source rows is a **pipe O.D.**, and every one came from `page_0003.png`
(the A-401 details sheet). `_calculate_from_measurement` has a detail-sheet guard at
`calculator.py:523` but it only covers `bollard/stairs/columns/ladder/lift` — rails fall straight
through.

### 1.2 The naming layer already works — this is purely a measurement gap

```
$ python3 -c "harvest_component_library(Crow pages)"
library entries: 25
   {'name': 'Guard Rail', 'basis': 'linear', 'unit': 'LF', 'aliases': [], 'source': 'keynote'}
   {'name': 'Hand Rail',  'basis': 'linear', 'unit': 'LF', 'aliases': [], 'source': 'keynote'}
classify_basis(Guard Rail) -> linear
classify_basis(Hand Rail)  -> linear
```

Source text it mined (Crow page 0, keynote 5, block bbox `1317,584,1584,594`):
`"RAMP GUARDRAIL - SEE DETAILS 4, 12 & 13 ON A-401"`, plus detail titles on page 2
(`RAMP RAIL SECTION`, `STAIR RAIL`, `Z-GUARD DETAIL`). `component_library.py:101-102` and
`:848-850` already map both to basis `linear`/unit `LF`. **Basis `linear` is then dropped on the
floor**: `fusion.py` mentions it only in a docstring (`:1859`); the only basis sets that are
consumed are `_ROOM_FILL_BASES` (`fusion.py:1601`, ceiling/roof/floor) and `_FLOOR_ROOF_BASES`.

### 1.3 The rail geometry exists — position-validated against the estimator's own marks

The take-off PDF (`uploads/Crow - Cass White Road-Take offs.pdf`, ground truth only) carries the
estimator's markup as extra coloured paths. Guard Rail = RGB `(0.79,0.02,0.05)`, Hand Rail =
`(0.37,0.22,0.95)`. **All five rail measurement polylines are on page 2 (A-401 MISC. DETAILS)**,
and the summary stamp on that page reads `Guard Rail 420.35 LF` / `Hand Rail 438.80 LF`:

```
== page 2 (estimator markup)
  color (0.79,0.02,0.05) bbox  273,167,1229,167   linelen 955.6 pt
  color (0.79,0.02,0.05) bbox 1771,869,1771,1168  linelen 299.5 pt
  color (0.79,0.02,0.05) bbox 1607,870,1607,1169  linelen 299.2 pt
  color (0.37,0.22,0.95) bbox 1783,937,1783,1315  linelen 378.0 pt
  color (0.37,0.22,0.95) bbox 1591,936,1591,1315  linelen 378.6 pt
```

Refined extractor output (`rail_probe5.py`) — production `walls._harvest` for linework, chained
with a 20° continuation constraint, parallel pairs (offset 0.02–1.0 ft) collapsed to one rail,
measured at **each detail's own printed scale**:

```
=== 13 ENLARGED RAMP PLAN (1/4"=1') fpp=0.05556 segs=239 -> 20 runs >= 4 ft
  ANSWER KEY (estimator markup):
     GUARD  53.10 LF  bbox=(273,167)-(1229,167)
        58.42 LF paired=False nseg=2   bbox=(208,270)-(1255,270)
        56.00 LF paired=False nseg=3   bbox=(268,116)-(1276,116)
        53.76 LF paired=False nseg=1   bbox=(268,86)-(1235,86)
        53.76 LF paired=False nseg=1   bbox=(268,188)-(1235,188)
        53.00 LF paired=True  nseg=1   bbox=(275,167)-(1229,167)   <-- the estimator's line
        52.75 LF paired=True  nseg=1   bbox=(279,163)-(1229,163)
        48.00 LF paired=True  nseg=1   bbox=(365,431)-(1229,431)   <-- rail on the ramp's far side

=== 6 STAIR PLAN (1/2"=1') fpp=0.02778 segs=861 -> 53 runs >= 4 ft
  ANSWER KEY (estimator markup):
     GUARD   8.32 LF  bbox=(1771,869)-(1771,1168)
     GUARD   8.31 LF  bbox=(1607,870)-(1607,1169)
     HAND   10.50 LF  bbox=(1783,937)-(1783,1315)
     HAND   10.52 LF  bbox=(1591,936)-(1591,1315)
        12.65 LF paired=True  nseg=4   bbox=(1607,868)-(1607,1169)  <-- right bbox, over-long
        12.63 LF paired=True  nseg=3   bbox=(1766,869)-(1767,1168)  <-- right bbox, over-long
        10.35 LF paired=True  nseg=1   bbox=(1591,937)-(1591,1315)  <-- 1.6% from golden mark
        10.21 LF paired=True  nseg=4   bbox=(1778,937)-(1778,1305)  <-- 2.8% from golden mark
```

**This is the decisive result.** Three of four rail marks are reproduced within 0.2–2.8% *at the
right coordinates*; the two guard-rail runs land on the exact bbox but over-chain past the rail
end (12.65 vs 8.32 LF) — a chain-termination detail, tunable against the bbox, never against a
count.

### 1.4 Why the current engine produces exactly zero of this

| Gate | Where | Effect on rails |
|---|---|---|
| Sheet-type gate | `takeoff_pipeline.py:232` `_PLAN_SHEET_TYPES = ("floor_plan","civil_site","roof_plan")`; used at `:1700` | Crow page 2 classifies `detail` → `extract_walls` / `extract_rooms` / `cluster_symbols` never run. Page 2 contributes **no geometry at all**. |
| Off-scale viewport mask | `takeoff_pipeline.py:1672-1700` | Correctly excludes off-scale details from plan-sheet measurement (anti-60×, anti-double-count) — but that is precisely where rails are drawn, so nothing measures them anywhere. |
| Only ungated measurement | `_measure_room_fills`, `takeoff_pipeline.py:1773` | Anchors on `room_fill.plan_titles()` → `PLAN_TITLE_RE` requires Moxy's `"<NAME> - <KIND> PLAN"`; Crow's `ENLARGED RAMP PLAN` / `STAIR PLAN` do not match → 0 fills on Crow (`room_fills=0` in probe 1). |
| Wall pairing window | `walls.py:52-53` `MIN_THICKNESS_FT=0.25` (3") | A 1½" pipe rail drawn as a double line can never pair as a wall; a single-line rail is not paired at all. Rails are structurally invisible to `extract_walls`. |
| No linear binder | `fusion.py:1911-1927` | Even with a candidate, basis `linear` has no consumer. |

### 1.5 A real, separate viewport bug found on the way (blocks 4 of the 5 rail marks)

The viewport that contains **4 of the 5 estimator rail marks** is classified as a *schedule*:

```
R7 schedule [1428, 755, 1921, 1374] fpi= None
   'BOLLARD COURT 7/A-401 SEE IN DETAIL TRUCK / SEE CONC. DOOR OPENING SCHEDULE'
```

`viewports.py:738-739` marks a region `schedule` when the word `SCHEDULE` appears anywhere in its
title-ish text and `PLAN` does not — here it fires on an in-drawing note
(`SEE CONC. DOOR OPENING SCHEDULE`) inside the **STAIR PLAN** drawing. Consequences:
`schedule` is in `_MASK_VIEWPORT_KINDS` (`takeoff_pipeline.py:239`) so its geometry is masked out,
**and** in `printed_scale._MASK_KINDS` (`:42`, used at `:394`) so it can never own a printed scale:

```
R7  kind=schedule  bbox=[1428, 755, 1921, 1374]  own_fpp=None  title=''
```

Page 2 has 13 printed scale labels and 12 viewports; **4 labels bind to no viewport at all** —
`SIDE SECTION @ LEVELER`, `RAMP RAIL SECTION`, `STAIR PLAN`, `Z-GUARD DETAIL` — i.e. three of the
four unbound labels are rail details.

### 1.6 The multiplier, stated honestly

Sum of what is actually drawn and measurable, at printed scale:

| Detail | own scale | measured (as drawn) |
|---|---|---|
| 13 ENLARGED RAMP PLAN | 1/4"=1'-0" | 53.0 LF guard (one side; a second run at 48.0 LF sits on the far side) |
| 6 STAIR PLAN | 1/2"=1'-0" | ~8.3 LF guard ×2, ~10.5 LF hand ×2 |
| **estimator's 5 marks** | | **90.6 LF total** |
| **golden** | | **859.15 LF total (420.35 + 438.80)** |

The golden is ~6× (guard) and ~21× (hand) the drawn lengths. Crow's overall floor plan (page 0)
draws the ramps and stairs, but at 1"=40' the rails are not separable — `rail_probe4.py` on the
left-ramp box returns chained hatch runs (`369.80 LF` inside a 19 ft × 53 ft box), not a rail. So
**the instance count is not recoverable from the linework**, and Crow's own stair count (golden 10
EA) is itself an open detection problem (§10). Therefore the target for this gap is *measure the
per-instance run, flag the count* — not a number that matches 420.35.

---

## 2. Implementation map

### Step 1 — kill the phantom: make `_apply_formula` unit-aware
**File/function:** `src/bobbytailor/pipeline/calculator.py:1212` `_apply_formula`, LF branch at
`:1263-1266` (and the SF branch at `:1275-1280`).

Today: `if item_type in ("storm_pipe","trench_drain","guard_rail","hand_rail","striping", …): return value * wf, "lf", …` — the `unit` parameter is never read.

Must do: guard both branches on the incoming unit.

```python
_LENGTH_UNITS = frozenset({"lf", "ft", "feet", "linear feet", "linear foot"})
_AREA_UNITS   = frozenset({"sq_ft", "sf", "square feet"})

if item_type in ("storm_pipe", "trench_drain", "guard_rail", "hand_rail", "striping",
                 "gas_pipe", "lintel", "duct_lf", "conduit_lf"):
    if unit not in _LENGTH_UNITS:
        # a diameter/height callout in inches is NOT a run length
        return value, unit, "no formula"
    ...
```

`_calculate_from_measurement` already drops any row whose formula is `"no formula"`
(`calculator.py:535`), so all seven phantom rows disappear with no other change. `_calculate_from_pipe_runs`
passes `"lf"` explicitly (`:869`) and is unaffected; `_calculate_from_lintel_runs` likewise (`:958`).

Also widen the detail-sheet callout guard at `calculator.py:523` to include `guard_rail`,
`hand_rail`, `striping`, `trench_drain` — a dimension annotation on a *detail* sheet is a spec, not
a run.

### Step 2 — new deterministic module `deterministic/linear_runs.py`
**New file.** Public API mirroring `room_fill.py`:

```python
@dataclass
class LinearRun:
    length_pt: float                  # POINT space (RawGeometry pattern, walls.py:23-27)
    points_pt: List[Tuple[float, float]]
    candidate_id: str = ""            # "LIN-1"
    scale_fpi: Optional[float] = None
    viewport_title: str = ""          # "ENLARGED RAMP PLAN"
    is_typical: bool = False          # measured in an off-main-scale detail
    paired: bool = False              # collapsed from a double-line rail
    needs_review: bool = False
    review_reason: str = ""
    def length_lf(self, feet_per_point): return self.length_pt * feet_per_point

def extract_linear_runs(page, doc, clip_pt, feet_per_point, *,
                        min_run_ft=4.0, exclude_rects=None) -> List[LinearRun]
```

`extract_linear_runs` must:
1. Harvest with the **existing** `walls._harvest(page, doc, exclude_rects)` (`walls.py:204`) — same
   stroked-path/OCG-layer/Bézier handling, and keep `walls.MAX_SEGMENTS` (`:84`) as the DoS guard.
2. Keep only segments whose midpoint is inside `clip_pt`.
3. Chain end-to-end with a **direction-continuity constraint** (join tol 0.75 pt, continuation
   within 20° of the current heading, choosing the straightest candidate). The constraint is what
   separates a rail from a hatch fan — the naive greedy version merges 33 k page-0 segments into
   6 112 junk runs (probe 1) while the constrained version isolates the rail exactly (probe 5).
4. Collapse **parallel pairs**: same heading ±5°, ≥70 % projection overlap, perpendicular offset in
   `[0.02 ft, 1.00 ft]` → one run of the mean length, `paired=True`. (A rail is drawn as two lines;
   without this every rail is reported at 2×. Deliberately *below* `walls.MIN_THICKNESS_FT = 0.25 ft`
   at the bottom and *below* `MAX_THICKNESS_FT` at the top so rails and walls cannot both claim a
   segment pair.)
5. Drop runs shorter than `min_run_ft`; return in point space.

Python 3.9: `from __future__ import annotations`, `typing.List/Tuple/Optional`, no `X | Y`.

### Step 3 — `TakeoffPipeline._measure_linear_runs` (new sibling of `_measure_room_fills`)
**File/function:** `src/bobbytailor/pipeline/takeoff_pipeline.py`, new method next to
`_measure_room_fills` (`:1773`).

Anchor on `printed_scale.extract_printed_scales(page)` (each `PrintedScale` already carries
`title`, `center_pt`, `bbox_pt`, `feet_per_point` — `printed_scale.py:67-77`) rather than
`room_fill.plan_titles()`, whose `PLAN_TITLE_RE` is Moxy-shaped and matches nothing on Crow. For
each label: clip the drawing area **above** it (reuse `_FILL_CLIP_UP_PT=620` / `_FILL_CLIP_SIDE_PT=260`,
`:1770-1771`), call `extract_linear_runs(page, doc, clip, ps.feet_per_point)`, stamp
`viewport_title = ps.title`, `scale_fpi = ps.feet_per_inch`, and
`is_typical = abs(ps.feet_per_point - resolved_fpp) > _SCALE_MATCH_TOL * resolved_fpp`
(`_SCALE_MATCH_TOL` at `:245`).

Wrap in `try/except` and default to `[]` — additive, exactly like the `room_fills` call site.

### Step 4 — expose the candidate in the bundle
**File/function:** `takeoff_pipeline._deterministic_bundle` (`:1587`), return dict at `:1749-1760`.

Call `_measure_linear_runs` beside the existing `room_fills` call (`:1741-1747`), **ungated by
sheet type** — same argument the room-fill comment already makes at `:1727-1735` ("a sheet is not
one thing"), and the decisive one here: Crow page 2 resolves to `detail`, so a plan-type gate skips
the only sheet the rails are on. Add `"linear_runs": linear_runs` to the returned dict, and add it
to `fusion.build_registry` so every run gets a `candidate_id` in the registry (rails must be
groundable IDs like every other candidate).

### Step 5 — `fusion._fuse_linear_runs` (new binder)
**File/function:** `src/bobbytailor/vision/fusion.py`, new function modelled on `_fuse_room_fills`
(`:1516`), called from `fuse_sheet` at `:1924` immediately after `_fuse_room_fills`.

```python
_LINEAR_BASES = frozenset({"linear"})

def _fuse_linear_runs(bundle, components, vocab_map, library=None, instance_counts=None):
```

Behaviour:
- For each vocabulary/library object whose basis ∈ `_LINEAR_BASES` (`Guard Rail`, `Hand Rail`,
  `Curb & Gutter`, `Lintels`, …), select runs whose **owning viewport title** resolves to that
  object via `component_library.resolve_library_name(run.viewport_title, library)`
  (`component_library.py:1194`) — the plan's own detail titles do the naming
  (`RAMP RAIL SECTION` / `STAIR RAIL` / `Z-GUARD DETAIL` → Guard Rail / Hand Rail). No vision input;
  no numeric input.
- Sum the selected runs per viewport → per-instance LF.
- `unit_count = instance_counts.get(...)` when known, else `None`; quantity = per-instance LF ×
  count, or per-instance LF when unknown, **with `needs_review=True`** and
  `review_reason = "measured ONE %r rail run (%.1f LF) on a TYPICAL detail; how many exist is not
  stated on this sheet"`. This is verbatim the `_fuse_room_fills` room-mix contract
  (`fusion.py:1566-1596`).
- Emit `provenance: "geometry"`, `unit: "LF"`, `candidate_id: run.candidate_id`,
  `name_source: "linear_run"`, and a `formula` string naming the viewport and its scale
  (`"53.0 LF (ENLARGED RAMP PLAN, open runs @ 4.00 ft/in)"`).
- **Never sum a `is_typical=True` run with a main-plan run of the same object** — same rail, two
  drawings; typical-detail runs are per-instance, main-plan runs are as-built (count 1).

### Step 6 — stop a drawing being classified as a table because it mentions one
**File/function:** `src/bobbytailor/deterministic/viewports.py:733-742` (the `kind` assignment in
the viewport constructor).

Must do: (a) do **not** assign `legend`/`schedule` when `printed_fpi is not None` — a region with
its own printed drawing scale is a drawing, not a table; (b) test only the region's title line
(bottom-edge title band), not every text block inside it. Evidence: R7 (`STAIR PLAN`, holder of 4 of
the 5 estimator rail marks) is `schedule` purely because the drawing contains the note
`SEE CONC. DOOR OPENING SCHEDULE`. Because `schedule` is in both `_MASK_VIEWPORT_KINDS`
(`takeoff_pipeline.py:239`) and `printed_scale._MASK_KINDS` (`:42`), that single misclassification
masks the geometry *and* denies it a scale. After the fix, `match_scales_to_viewports`
(`printed_scale.py:381`) should bind `STAIR PLAN` (and `RAMP RAIL SECTION`, `Z-GUARD DETAIL`) to a
viewport with no further change.

### Step 7 — name normalisation (small, and it is why the row reads "Guardrail")
**File/function:** the library-verbatim naming path that bypasses `aggregator.ITEM_NAME_MAP`
(§10.2). `aggregator.py:50-51` already canonicalises `guard.*rail → "Guard Rail"` /
`hand.*rail → "Hand Rail"`, yet the saved run emits `Guardrail` / `Handrail`. Route library names
through the same normalisation so `Guard Rail` converges with golden regardless of which path named
it.

---

## 3. Offline verification (free — zero API, no golden marker)

1. **Phantom is gone.**
   ```bash
   python3 -c "import sys;sys.path[:0]=['.','src'];\
   from bobbytailor.pipeline.calculator import _apply_formula,_calculate_from_measurement;\
   print(_apply_formula('guard_rail',1.5,'in','1.5'));\
   print(_calculate_from_measurement({'value':'1.5','unit':'in','description':'Steel pipe guardrail outer diameter','raw_text':'1 1/2\" O.D. STEEL PIPE GUARDRAIL'},'A-401','detail'))"
   ```
   Assert: `('...','in','no formula')` and `None`. (Today: `(1.545,'lf','2 lf × 1.03 = 2 lf')` and a
   1.54 LF row.)
2. **No rail row is ever built from an inch dimension.**
   ```bash
   awk -F, '$1 ~ /rail/ && $4 == "in"' output/*/calculations.csv   # must be empty after a re-run
   ```
3. **Candidate exists in the bundle.** Run `_deterministic_bundle` on Crow page 2 (`sheet_type="detail"`)
   and assert `"linear_runs" in bundle` and `len(bundle["linear_runs"]) > 0`.
4. **Position validation (the only legitimate acceptance test).** On Crow page 2 the extracted runs
   must include, within ±3 pt on every bbox edge and ±5 % on length:

   | expected bbox (pt) | expected LF | at fpp |
   |---|---|---|
   | `(275,167)-(1229,167)` | 53.1 ± 5 % | 0.05556 |
   | `(1591,937)-(1591,1315)` | 10.5 ± 5 % | 0.02778 |
   | `(1778,937)-(1778,1305)` | 10.5 ± 5 % | 0.02778 |
   | `(1607,868)-(1607,1169)` | 8.3 ± 5 % | 0.02778 |
   | `(1766,869)-(1767,1168)` | 8.3 ± 5 % | 0.02778 |

   These five bboxes are the estimator's own marks, read out of the take-off PDF's coloured paths
   (`(0.79,0.02,0.05)` guard, `(0.37,0.22,0.95)` hand). Pin them as literals in the test — **never**
   assert on 420.35 / 438.80.
5. **Viewport fix.**
   ```bash
   python3 -c "...segment_viewports(page2)..." | grep 1428
   ```
   Assert R7's `kind != 'schedule'` and that `match_scales_to_viewports` leaves **0** printed labels
   unbound on page 2 (today: 4 unbound, incl. `STAIR PLAN`, `RAMP RAIL SECTION`, `Z-GUARD DETAIL`).
6. **Fusion binder.** Unit test `fuse_sheet` with a synthetic bundle
   `{"linear_runs": [LinearRun(viewport_title="STAIR RAIL", …)], "fpp": 0.02778}` and vocabulary
   `[{"name":"Hand Rail","measure":"linear","unit":"LF"}]`; assert one component with
   `provenance == "geometry"`, `unit == "LF"`, `needs_review is True`, `unit_count is None`.
7. **No regression / no double-count.** `pytest -q` (1132 offline tests; the golden marker is
   excluded by default) plus an assertion that Crow's `takeoff_summary` contains **at most one**
   `Guard Rail` row and that its `formula` names exactly one viewport.
8. **Re-run the recipe end-to-end for free:** `python3 scripts/geom_probe.py "uploads/Crow - Cass
   White Road-Plans.pdf"` (page 2 must now report `linear_runs`), and the scratchpad
   `rail_probe5.py` for the position table.

---

## 4. Risks

1. **The §10 coincidence trap, restated for rails.** There is *no positional ground truth for the
   golden totals* — the take-off's 420.35/438.80 are a stamped summary, and the 5 marked polylines
   total only ~90.6 LF at printed scale. Any parameter tuned until the total reads 420 is tuned to a
   multiplier nobody has verified. Tune **only** against the five bboxes in §3.4.
2. **Under-report by ~6–21× is the expected, correct outcome of step 1–5 alone.** Rails will go
   from "5.8 LF, confidently wrong" to "~53 LF per ramp / ~10.5 LF per stair rail, flagged". That is
   a large *drop* on any naive total-based metric while being a large *gain* in correctness — the
   same trade §10 flagged as "a decision for the user, not a silent change". Get explicit sign-off
   before shipping, and land it together with the `needs_review` surfacing so the flag is visible.
3. **Double-counting across sheets.** The same rail is drawn on page 0 (plan) and page 2 (details).
   The `is_typical` flag plus the "never sum typical with main-plan" rule in step 5 is the whole
   defence; if that rule is dropped, Crow's rails inflate silently.
4. **Over-chaining.** Without the per-viewport clip *and* the 20° continuity constraint, chaining
   swallows hatch fields — probe 1 on page 0 produced a `369.80 LF` "run" inside a 19 ft × 53 ft box.
   Do not enable `extract_linear_runs` on an unclipped page.
5. **Loosening the viewport `schedule` test (step 6) is a shared-path change.** `schedule`-kind
   regions mask geometry for walls/symbols/dimensions too; a region wrongly promoted from
   `schedule` to `detail` would let table linework back into wall extraction. Gate the change on
   `printed_fpi is not None` (a real table has no drawing scale) and re-run the Crow/Bob's/Moxy
   `scale_probe` + `geom_probe` outputs for diffs before/after.
6. **Performance.** Crow page 0 harvests 33 018 straight segments; chaining must stay a hash-grid
   O(n) pass and must keep `walls.MAX_SEGMENTS` (`walls.py:84`). Page 2 (12 037 segments, 12
   viewports) ran in seconds in the probe, so the per-viewport clip is also the performance
   strategy.
7. **Python 3.9 only.** No `X | Y` unions, no `list[str]` builtins in annotations without
   `from __future__ import annotations`, no `match`.

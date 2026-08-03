# INV-01 — Room fills → wall-area line items (implementation map)

Investigator note: READ-ONLY investigation. The only file written inside the repo is this
document. Two throwaway probes were written to the session scratchpad (outside the repo) because
`scripts/room_probe.py` is broken (see §7) and exercises the wrong engine; every number below is
pasted from an actual zero-API run.

---

## TL;DR

1. **Room fills never reach a wall line item because of one frozenset.**
   `fusion._ROOM_FILL_BASES = frozenset({"ceiling_area", "roof_area", "floor_area"})`
   (`src/bobbytailor/vision/fusion.py:1601`) is the gate at
   `src/bobbytailor/vision/fusion.py:1550`. `human_inputs/moxy_knoxville.json` declares
   `Gyp Wall`, `Guestroom-Wall Covering` and `CMU Wall` with `"measure": "wall_area"`, so all three
   are `continue`d out of `_fuse_room_fills` before any fill is looked at. Ceiling binds only
   because `ceiling_area` happens to be in that set.
2. **Even with the gate opened there is nothing to bind.** A `RoomFillResult`
   (`src/bobbytailor/deterministic/room_fill.py:85-112`) carries `area_sf` and `regions` (a list of
   floats) — **no perimeter, no contour, no pixel geometry**. `_label_regions`
   (`room_fill.py:148-191`) throws the labelled bitmap away and returns only counts. Wall area
   needs `perimeter × height`; the perimeter primitive does not exist anywhere in the package
   (the only `perimeter_lf` in the codebase is `Footprint.perimeter_lf`, a whole-building
   `2×(w+d)` rectangle).
3. **The cheapest correct perimeter is an outer-contour trace on the mask room_fill already
   renders** — Moore-neighbour trace + Douglas–Peucker, pure stdlib, ~60 lines, Python 3.9-safe,
   zero new dependencies, zero extra renders. I prototyped it against the real Moxy PDF; it
   reproduces `room_fill`'s areas to the decimal and yields perimeters whose shape ratio
   `P/√A` lands at **4.24–5.08** on real guestrooms (4.00 = a perfect square). See §4.
4. **The wall height currently available would poison Moxy silently.**
   `_resolve_project_wall_height` (`src/bobbytailor/pipeline/takeoff_pipeline.py:860`) returns
   **15.00 ft, source `"plan"`** for Moxy — harvested from a single `15'-0" CLEAR REQ'D` callout on
   the **roof plan** (page 3). Because `source != "default"`, nothing is flagged
   (`fusion.py:1424 is_default = source == "default"`). The real guestroom height is printed inside
   every prototype RCP viewport: `9'-0"` (bedroom) and `8'-0"` (bath/entry) — I extracted both
   deterministically from the exact clip `_measure_room_fills` already computes (§5). The 30 ft
   industrial default is not the danger here; **the project-level `max()` clear-height rule is.**
5. **Double-count landmine.** `aggregator.aggregate_takeoff`
   (`src/bobbytailor/pipeline/aggregator.py:235`) *sums* buckets keyed by canonical name, and
   `fuse_sheet` (`fusion.py:1911-1927`) appends `_fuse_wall_classes` and `_fuse_room_fills` output
   into the *same* `components` list with no dedupe. `_fuse_wall_classes` already emits
   `Gyp Wall` SF (that is the current 2,745 SF). Turning on wall-area room fills without an
   explicit suppression rule produces `2,745 + room-fill` — a wrong number that looks better.

---

## 1. Evidence: what fills actually exist on Moxy today

`scripts/room_probe.py` could not answer this (§7), so the probe below calls
`TakeoffPipeline._measure_room_fills` **unbound** — that method reads only `page`, `sheet_name` and
three class constants, so it runs with a stub `self`, no pipeline construction, no API key.

```
$ python3 scratchpad/fill_probe.py "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf"
page 23: 5 fill(s)
   FILL-1   kind=AR   name='KING A'         area=    193.2 SF  scale_fpi=4.0     regions=[173.5, 11.5, 8.3]
       fields present: ['area_sf', 'candidate_id', 'needs_review', 'plan_kind', 'plan_name', 'regions', 'review_reason', 'scale_fpi', 'sheet_name', 'viewport_title']
   FILL-2   kind=FF   name='KING A'         area=    198.3 SF  scale_fpi=4.0     regions=[112.3, 24.0, 19.2, 14.5, 14.4, 13.9]
   FILL-3   kind=FF   name='KING A'         area=    185.1 SF  scale_fpi=4.0     regions=[113.6, 24.0, 14.7, 13.4, 10.9, 8.5]
   FILL-5   kind=EM   name='KING A'         area=    166.7 SF  scale_fpi=4.0     regions=[166.7]
   FILL-6   kind=RCP  name='KING A'         area=    229.4 SF  scale_fpi=4.0     regions=[121.8, 34.2, 19.9, 13.4, 11.9, 10.8]
page 27: 5 fill(s)
   FILL-1   kind=AR   name='KING SUITE B'   area=    369.9 SF  scale_fpi=4.0     regions=[249.4, 34.4, 26.2, 25.1, 17.3, 9.4]
   FILL-3   kind=RCP  name='KING SUITE B'   area=    341.7 SF  scale_fpi=4.0     regions=[216.8, 37.7, 33.4, 24.7, 18.8, 10.3]
page 29: 6 fill(s)
   FILL-1   kind=AR   name='QQ A'           area=    275.8 SF  scale_fpi=4.0     regions=[174.6, 41.8, 30.1, 16.0, 13.3]
   FILL-4   kind=RCP  name='QQ A'           area=    272.6 SF  scale_fpi=4.0     regions=[157.6, 40.6, 33.5, 14.2, 13.4, 13.3]
page 33: 5 fill(s)
   FILL-1   kind=AR   name='BUNK B'         area=    337.0 SF  scale_fpi=4.0     regions=[160.4, 65.7, 41.2, 28.3, 17.3, 15.3]
   FILL-3   kind=RCP  name='BUNK B'         area=    274.6 SF  scale_fpi=4.0     regions=[176.3, 40.4, 34.5, 11.7, 11.6]
...
== 87 fills total; sum area by discipline: {'AR': 4618.0, 'EM': 3064.4, 'FC': 2092.9, 'FF': 3747.2, 'RCP': 5682.0}
```

Facts established by this run:

* **87 fills exist across the project**, on pages 12, 21–38, covering every prototype unit type
  (`KING A`…`ACC BUNK`) plus `L7 CORRIDOR`, `L2-L6 CORRIDOR`, `LEVEL 1 POP-UP HUB`.
* The RCP numbers reproduce §14 of `docs/PIPELINE-GROUND-TRUTH.md` exactly (KING A 229.4,
  KING SUITE B 341.7, QQ A 272.6, BUNK B 274.6). The engine is working; only the binding is absent.
* **`plan_name` matches the `human_inputs/moxy_knoxville.json` room-mix keys verbatim**
  (`KING A`, `QQ A`, `BUNK B`, …), so `room_mix.get(_norm_name(pick.plan_name))` at
  `fusion.py:1561-1562` already resolves. The multiplier path is live.
* **The field list is the smoking gun**: `area_sf, candidate_id, needs_review, plan_kind,
  plan_name, regions, review_reason, scale_fpi, sheet_name, viewport_title`. No perimeter.
* **AR fills are materially less reliable than RCP fills** — `ACC QQ RIS` AR = 42.5 SF vs RCP
  451.1; `ACC BUNK` AR = 62.9 vs RCP 458.5; `KING A` AR = 193.2 vs RCP 229.4. The AR plan carries
  dimension strings, leaders and door swings that break the enclosure and let the fill leak.
  `BASIS_PLAN_KIND["wall_area"] = "AR"` (`room_fill.py:58`) therefore points wall area at the
  *worse* raster. This must be handled (§6, step 5) — not by silently switching to RCP.

---

## 2. Exactly why ceiling binds and wall does not — line by line

```
fusion.py:1547   for info in vocab_map.values():
fusion.py:1548       basis = str(info.get("basis") or "").strip().lower()
fusion.py:1550       if not name or basis not in _ROOM_FILL_BASES:   # <-- wall_area dies here
fusion.py:1551           continue
...
fusion.py:1601   _ROOM_FILL_BASES = frozenset({"ceiling_area", "roof_area", "floor_area"})
```

`_vocabulary_basis_map` (`fusion.py:365`) maps each human-input object to `{"basis": measure}`.
Moxy's inputs give `Gyp Ceiling → ceiling_area` (passes) and `Gyp Wall → wall_area` (rejected at
1550). `wanted` therefore never contains a wall object, `select_fill_for_basis` is never called for
it, and no component is appended. `Gyp Wall`'s only remaining producer is `_fuse_wall_classes`
(`fusion.py:1356`), which computes `round(lf_value * height, 1)` from **thickness-class centreline
linework** (`fusion.py:1464`) — the Crow-shaped measurement that yields 2,745 SF against a
129,521 SF golden.

Note `room_fill.BASIS_PLAN_KIND` (`room_fill.py:54-60`) **already contains** `"wall_area": "AR"`.
The deterministic layer anticipated this binding; the fusion gate was never widened, and the
perimeter primitive was never built.

---

## 3. What is missing in `room_fill.py`

| Needed | Present? | Where it would go |
|---|---|---|
| labelled pixel mask | built then discarded | `_label_regions` (`room_fill.py:148-191`) builds `seen`/`free` bytearrays and returns `List[FilledRegion]` of `(area_sf, px, touches_edge)` only |
| per-region contour | **no** | new `_trace_outer_contour` |
| per-region perimeter | **no** | new field on `FilledRegion` (`room_fill.py:76-82`) |
| unit perimeter | **no** | new field on `RoomFillResult` (`room_fill.py:85-112`) + `to_dict` (`100-112`) |
| wall height | **no** | new field on `RoomFillResult`; resolved per drawing (§5) |
| `perimeter × height` | **no** | new `wall_area_for_unit()` beside `total_for_units` (`room_fill.py:268`) |

`measure_enclosed_area` (`room_fill.py:194-247`) computes `px_area_sf = (1/zoom²)·fpp²` at line 229.
The linear analogue is one line: `px_len_ft = (1/zoom)·fpp`. Everything else already exists.

---

## 4. Prototype: the perimeter primitive, run against the real PDF

Method: re-render the *identical* clip `_measure_room_fills` computes, re-label with the identical
`INK_THRESHOLD`/`MIN_REGION_SF`/`MAX_REGION_SF` constants, then trace each surviving region's
**outer** contour (Moore-neighbour tracing from the region's topmost-leftmost pixel, which walks the
outer boundary only and ignores interior holes — furniture outlines and room-number text must not
inflate the perimeter), then Douglas–Peucker at ε = 2 px to remove the raster staircase.

```
$ python3 scratchpad/perim_probe.py "uploads/Moxy ...-Plans.pdf" --pages 23,27,29,33 --kinds AR,RCP
p23  KING A         AR    A_sum=  193.3 SF  P_sum=  174.2 LF   biggest: A=  173.5 P= 113.6 P/sqrtA=8.62   nreg=3
p23  KING A         RCP   A_sum=  229.4 SF  P_sum=  271.8 LF   biggest: A=  121.8 P=  56.1 P/sqrtA=5.08   nreg=8
        region A=  121.8 SF  P_raw=  56.5  P_simp=  56.1  P/sqrtA= 5.08  x9ft=   504.9 SF
        region A=   34.2 SF  P_raw=  30.5  P_simp=  30.4  P/sqrtA= 5.20  x9ft=   273.6 SF
        region A=   19.9 SF  P_raw=  26.8  P_simp=  26.6  P/sqrtA= 5.96  x9ft=   239.4 SF
        region A=   13.4 SF  P_raw=  42.3  P_simp=  42.3  P/sqrtA=11.56  x9ft=   380.7 SF
        region A=   11.9 SF  P_raw=  16.5  P_simp=  16.4  P/sqrtA= 4.75  x9ft=   147.6 SF
        region A=   10.8 SF  P_raw=  42.0  P_simp=  42.0  P/sqrtA=12.78  x9ft=   378.0 SF
p27  KING SUITE B   AR    A_sum=  369.9 SF  P_sum=  361.7 LF   biggest: A=  249.4 P= 142.8 P/sqrtA=9.04   nreg=7
p27  KING SUITE B   RCP   A_sum=  341.7 SF  P_sum=  263.3 LF   biggest: A=  216.8 P=  62.5 P/sqrtA=4.24   nreg=6
p29  QQ A           AR    A_sum=  275.8 SF  P_sum=  295.6 LF   biggest: A=  174.6 P= 112.8 P/sqrtA=8.54   nreg=5
p29  QQ A           RCP   A_sum=  272.6 SF  P_sum=  253.4 LF   biggest: A=  157.6 P=  58.2 P/sqrtA=4.64   nreg=6
p33  BUNK B         AR    A_sum=  337.1 SF  P_sum=  371.3 LF   biggest: A=  160.4 P=  55.4 P/sqrtA=4.37   nreg=7
p33  BUNK B         RCP   A_sum=  274.5 SF  P_sum=  208.0 LF   biggest: A=  176.3 P=  64.3 P/sqrtA=4.84   nreg=5
```

**Validated by shape and position, never by count** (rule 6):

* `A_sum` reproduces `room_fill`'s published areas to the decimal (193.3 vs 193.2, 229.4, 369.9,
  341.7, 275.8, 272.6, 337.1, 274.5) — proof the prototype is measuring the *same* regions and the
  perimeter is derived from the *same* mask, not a parallel re-implementation.
* The dominant RCP region's shape ratio `P/√A` is **4.24, 4.64, 4.84, 5.08** across four different
  unit types. A square is 4.00; a 1:2 rectangle is 4.24; an L-shaped hotel room with a bath alcove
  lands ~4.5–5.2. These are physically correct room outlines.
* The same ratio exposes junk: regions of 10–17 SF come back at **11.6–13.4** — long thin
  dimension/annotation cells, not rooms. Their perimeter is pure noise (a 13.4 SF cell contributes
  42 LF, more than a 121.8 SF bedroom's 56 LF).
* The same ratio exposes the AR leak: `KING A` AR = **8.62**, `KING SUITE B` AR = **9.04**,
  `QQ A` AR = **8.54** — the contour is wandering out through door swings and dimension strings.
  This is the §14.2 clip defect surfacing in a second measurable way, and it is a *blind* detector:
  no golden number is consulted.

**Raw vs simplified**: DP at ε = 2 px changes the perimeter by < 1.5% on every region
(114.9→113.6, 144.4→142.8, 66.5→64.3). The staircase penalty is small because guestrooms are
rectilinear; keep the simplification anyway so a diagonal wall does not get a √2 penalty.

**Do NOT apply the `P/√A` gate to AREA without a separate blind evaluation.** Stripping the
high-ratio regions from `KING SUITE B` RCP takes 341.7 SF → 283.6 SF, and §14 records 341.7 as
3.3% off. Those slivers may be real (closet/soffit slots) or may be cancelling another error. That
is a separate question; changing area here would be exactly the "136 columns was a coincidence"
trap run in reverse.

---

## 5. Where the wall height comes from — and the trap

`_resolve_project_wall_height` (`src/bobbytailor/pipeline/takeoff_pipeline.py:860-916`) is called
once per project at `takeoff_pipeline.py:2738`, stored on `self._project_wall_height`, and threaded
into `fuse_sheet` at `takeoff_pipeline.py:2113-2114`. Precedence is learned → Tier 1 CLEAR/CLR
(`_clear_height_values`, line 831) → Tier 2 wall keywords → Tier 3 material-adjacent → 30 ft default
(`_WALL_HEIGHT_DEFAULT_FT`, line 803).

Actual behaviour on the two real plan sets (zero API):

```
Moxy Knoxville - Addendum A City Comment Revision-Pl    -> 15.00 ft  source=plan
   clear-callouts: [15.0]
   primary-kw    : []
   material-kw   : [8.0, 8.083, 8.5, 9.0, 14.333, 15.5]
Crow - Cass White Road-Plans.pdf                        -> 36.00 ft  source=plan
   clear-callouts: [36.0]
DEFAULT = 30.0
```

The single Moxy CLEAR callout, located:

```
p3   ... | S3 | S8 | 15'-0" CLEAR REQ'D | 15'-0" | 4 | 1 | 3 | ...
```

Page 3 is the **roof plan**. `15'-0" CLEAR REQ'D` is a required clearance around rooftop equipment.
It becomes the project wall height for all 40 pages, with `source="plan"`, which means
`is_default` is False at `fusion.py:1424` and **the item is not flagged**. Multiplying a guestroom
partition perimeter by 15 ft would be a ~67% overstatement delivered at `confidence: high`.

**The correct height is printed inside the drawing that is already being clipped.** Extracting
feet-inch tokens in the 7–12 ft band from the exact `_measure_room_fills` clip, excluding `AFF`
mounting-height tags:

```
p23  KING A         RCP clip height-tags: [('9\'-0"', 9.0), ('8\'-0"', 8.0)]
p27  KING SUITE B   RCP clip height-tags: [('9\'-0"', 9.0), ('8\'-0"', 8.0)]
p29  QQ A           RCP clip height-tags: [('9\'-0"', 9.0), ('8\'-0"', 8.0)]
p33  BUNK B         RCP clip height-tags: [('9\'-0"', 9.0), ('8\'-0"', 8.0)]
```

Every guestroom RCP prints `9'-0"` (bedroom ceiling) and `8'-0"` (bath/entry). These are the ceiling
heights the RCP is *for*. The 30 ft warehouse default is not what poisons the hotel — **the
project-level `max(clear callouts)` rule is**, and it poisons it while looking authoritative.

Required precedence for the room-fill wall binding, most-specific first:
`per-drawing RCP ceiling tag` → `learned wall_height_ft` → `project _resolve_project_wall_height`
→ flag. Any height not read from that drawing's own clip must set `needs_review=True` with the
source named, exactly as `_fuse_wall_classes` does for `default`.

---

## 6. The binding path, function by function

```
page ──_measure_room_fills (takeoff_pipeline.py:1773)
       │  clip = title bbox ± _FILL_CLIP_SIDE_PT / _FILL_CLIP_UP_PT   (1824-1829)
       ├─ measure_enclosed_regions   [NEW, room_fill.py]  → FilledRegion(+perimeter_lf, +shape_ratio)
       ├─ resolve_drawing_height     [NEW, room_fill.py]  → (height_ft, source)
       └─ RoomFillResult(+perimeter_lf, +region_perimeters, +wall_height_ft, +wall_height_source)
              │
              └─ bundle["room_fills"]  (takeoff_pipeline.py:1751)
                     │
                     └─ fuse_sheet (fusion.py:1825) ── _fuse_room_fills (fusion.py:1516)
                            ├─ vocab basis gate           (fusion.py:1550, _ROOM_FILL_BASES:1601)
                            ├─ select_fill_for_basis      (room_fill.py:131)  wall_area → "AR"
                            ├─ wall_area_for_unit  [NEW]  = perimeter_lf × height_ft
                            ├─ total_for_units            (room_fill.py:268)  × room_mix count
                            └─ components.append({name, quantity, unit:"SF", provenance:"geometry",
                                                  formula, unit_count, needs_review, review_reason})
                                   │
                                   └─ merge_with_provenance (fusion.py:241)
                                          └─ calculator → aggregate_takeoff (aggregator.py:235) SUMS
```

### Step-by-step changes

**1. `room_fill._label_regions` (`room_fill.py:148-191`) — return geometry, not just counts.**
Keep the BFS, but write the component id into a `labels` array instead of the `seen` bytearray, and
record each region's first (topmost-leftmost) pixel index. Return `(labels, regions, width, height)`
or, to avoid churning the signature, add a sibling `_label_regions_with_contours`. `FilledRegion`
(`room_fill.py:76-82`) gains `perimeter_lf: float = 0.0` and `shape_ratio: float = 0.0`.

**2. New `room_fill._trace_outer_contour(labels, w, h, region_id, start_idx) -> List[Tuple[int,int]]`.**
Moore-neighbour (8-connected) tracing with Jacob's stopping criterion, seeded at the region's
topmost-leftmost pixel with an initial backtrack direction of west. Walks the **outer** ring only,
so interior holes (furniture blocks, room-number text) never enter the perimeter. Pure stdlib.

**3. New `room_fill._simplify_ring(points, eps_px=2.0)`.** Douglas–Peucker. **Closed-ring hazard:**
running plain DP on a ring whose first and last point coincide collapses the entire ring — the base
chord is degenerate and every deviation measures zero (I hit exactly this in the prototype: every
`P_simp` came back `0.0`). Split the ring at the vertex farthest from `points[0]`, simplify the two
halves independently, and rejoin.

**4. `room_fill.measure_enclosed_area` (`room_fill.py:194-247`) — add the linear scale factor.**
Beside `px_area_sf` at line 229, add `px_len_ft = (1.0 / zoom) * feet_per_point`. For each surviving
region (the filter at lines 233-236 is unchanged) compute
`perimeter_lf = polyline_length(_simplify_ring(_trace_outer_contour(...))) * px_len_ft` and
`shape_ratio = perimeter_lf / sqrt(area_sf)`. Populate the new `RoomFillResult` fields:
`perimeter_lf` (sum over surviving regions), `region_perimeters` (parallel to `regions`), and
`region_shape_ratios`. Extend `to_dict` (`room_fill.py:100-112`) with all three — the report and the
learning store both read `to_dict`.

**5. New `room_fill.wall_perimeter_for_unit(result, max_shape_ratio=8.0) -> Tuple[float, str]`.**
Returns the perimeter that should be billed plus a reason string. Sum `region_perimeters` for
regions whose `shape_ratio <= max_shape_ratio`; regions above it are annotation cells (measured
11.6–13.4 in §4) and their LF is dropped **and named in `review_reason`**, never silently.
If the *dominant* region itself exceeds the threshold — which is what the leaking AR fills do
(8.54–9.04) — return `(0.0, reason)` so the caller flags instead of emitting a fabricated LF.
Threshold rationale is geometric (`P/√A ≥ 4` for any simply-connected region; 8.0 is a 2× margin on
the worst honest room measured, 5.08), **not** fitted to any golden quantity.

**6. New `room_fill.wall_area_for_unit(perimeter_lf, height_ft) -> float`.** One line,
`round(perimeter_lf * height_ft, 1)`. Exists as a named function so the formula string and the
tests have a single anchor, mirroring `total_for_units` (`room_fill.py:268`).

**7. New `room_fill.drawing_ceiling_heights(page, clip) -> List[float]` and
`resolve_drawing_height(page, clip, project_height_ft, project_height_source)`.**
Scan text lines fully inside `clip`; accept feet-inch tokens in the 7.0–12.0 ft band; reject any
span containing `AFF` (those are fixture mounting heights — see the p23 text dump, `8'-1"AFF`,
`4'-6"AFF`, `2'-3"AFF`). Return `(max(found), "drawing")` when found, else
`(project_height_ft, project_height_source)`. Rationale for `max`: within one unit the RCP prints
the bedroom height and the lower bath/entry soffit; the wall that gets boarded full height is the
tall one. Height source is carried, and anything not `"drawing"` flags.

**8. `TakeoffPipeline._measure_room_fills` (`takeoff_pipeline.py:1773-1849`) — populate the new
fields.** After `flag_implausible_unit` at line 1837, call `resolve_drawing_height(page, clip, ...)`
and assign `result.wall_height_ft` / `result.wall_height_source`. The method must accept the project
height; today it takes `(page, viewports, printed_scales_by_region, sheet_name)` and **ignores
`viewports` and `printed_scales_by_region` entirely** — replace one of them rather than growing the
signature, and update the call site at `takeoff_pipeline.py:1740-1742`. Extend the existing
`logger.info` at 1843 with perimeter + height + height source so a run's log alone proves the
binding fired.

**9. `fusion._ROOM_FILL_BASES` (`fusion.py:1601`) — add `"wall_area"`.** One token. This is the
gate; everything above is what makes opening it honest.

**10. `fusion._fuse_room_fills` (`fusion.py:1516-1597`) — branch on basis.** Add
`wall_height_ft` / `wall_height_source` parameters (fall back to the fill's own
`wall_height_ft` first). Inside the loop after `select_fill_for_basis` at line 1558:

* if `info["basis"] == "wall_area"`: `perimeter_lf, why = wall_perimeter_for_unit(pick)`;
  if `perimeter_lf <= 0` → append a `quantity: 0.0`, `needs_review: True` component naming the
  reason (flag-don't-guess; never `continue` silently, or the item disappears from the report);
  else `base = wall_area_for_unit(perimeter_lf, height)`.
* else: `base = pick.area_sf` (today's behaviour, unchanged).
* `qty = total_for_units(base, count if known_count else None)` — the existing line 1564.
* `formula` becomes `"%.1f LF perimeter (%s, enclosed regions @ %.2f ft/in) × %.1f ft (%s) × %d units"`.
* `needs_review` gains the height-source condition: anything but `"drawing"`/`"learned"` flags,
  matching `_fuse_wall_classes`' treatment of a default height (`fusion.py:1449-1450`).

**11. `fusion.fuse_sheet` (`fusion.py:1825-1833`) — thread the height.** `wall_height_ft` and
`wall_height_source` are already parameters (lines 1830-1831) and already supplied by
`takeoff_pipeline.py:2113-2114`. Only the `_fuse_room_fills(...)` call at `fusion.py:1924` needs the
two extra arguments.

**12. `fusion.fuse_sheet` — suppress the double count.** `_fuse_wall_classes` (line 1914) runs
*before* `_fuse_room_fills` (line 1924) and both append to the same list; `aggregate_takeoff`
(`aggregator.py:235`) then **sums** same-named buckets. Add
`_suppress_superseded_wall_items(components, room_fill_names)`: a room-fill-derived wall item
measured from an actual enclosed region supersedes the same-named thickness-class estimate on that
sheet. The suppressed component must be appended to `fusion_rejected` with
`reason: "superseded_by_room_fill"` so the audit trail shows the substitution — the file already
has this pattern (`_reject_unknown_id`, `fusion.py:1945`). Do not rely on
`merge_with_provenance` (`fusion.py:241`) to resolve it: both carry `provenance: "geometry"`, so it
falls through to "higher confidence, then first-seen" and drops one silently.

**13. `select_fill_for_basis` (`room_fill.py:131-145`) — one guarded change.** It resolves
`wall_area → "AR"` today and returns `min(matches, key=area_sf)`. Two problems visible in §1:
`min()` picks the *smaller* of two same-discipline fills (correct for opposite-hand duplicates,
wrong when a sheet legitimately shows two unit types), and the AR raster leaks on several sheets.
**Do not switch wall_area to RCP to dodge the leak** — that is a discipline violation and §14.3
warns exactly against selection rules chosen for their output. Instead: keep AR, and let step 5's
shape gate return `0.0` + flag when the AR fill is degenerate. Fixing the AR clip is §14.2's open
defect and belongs to its own investigation.

---

## 7. `scripts/room_probe.py` is broken and probes the wrong engine

```
$ python3 scripts/room_probe.py "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf" --fpi 4.0
Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf: 40 pages, assumed scale 4.0 ft/in (fpp=0.0556)
  page  3 [roof_plan]: ERROR AttributeError: 'NoneType' object has no attribute 'fpp'
  page  7 [floor_plan]: ERROR AttributeError: 'NoneType' object has no attribute 'fpp'
  ... (29 pages, every one)
== TOTAL rooms=0  ceiling-area(sum of room polygons)=0 SF  perimeter-sum=0 LF
```

Cause: `scripts/room_probe.py:82` calls `select_main_plan([(v, None) for v in vps])`, but
`scale_solver.select_main_plan` (`src/bobbytailor/deterministic/scale_solver.py:261-278`) requires
`Sequence[Tuple[Viewport, ViewportScale]]` and dereferences `vs.fpp` at line 276. The probe has
been passing `None` as the scale since the signature changed.

Second, deeper problem: even repaired it exercises `deterministic.rooms.extract_rooms` (Recipe C,
the centreline polygonizer) — the engine §13.4 documents as returning 17 SF fragments on Moxy. It
**cannot** answer "what fills exist and what fields do they carry", which is what this gap needs.

Recommendation: repair line 82 (`select_main_plan(list(zip(vps, scales)))` from the same
`printed_scales_by_region` the pipeline builds) **and** add `--engine {vector,fill}`, where `fill`
runs the `_measure_room_fills` path and prints `area_sf / perimeter_lf / shape_ratio /
wall_height_ft / wall_height_source` per fill. The two scratchpad probes used here are the
reference implementation and should be folded in — the fill probe needs a stub `self` only because
`_measure_room_fills` is a method that uses no instance state; consider making it a module-level
function in `room_fill.py` taking `(page, sheet_name, clip_up_pt, clip_side_pt, max_unit_sf)`, which
removes the stub and makes it directly testable.

---

## 8. Offline verification — every step, zero API

All of the following are free. None touch `ANTHROPIC_API_KEY`, `pytest -m golden`,
`scripts/accuracy_gate.sh`, `scripts/vision_only_benchmark.py` or `scripts/golden_convergence.py`.

**Unit level** — extend `tests/test_room_fill.py`, which already builds synthetic pages with
`fitz` and a known scale (`FPP_QUARTER`, see `tests/test_room_fill.py:50`):

1. `test_perimeter_of_a_known_rectangle` — draw a 10 ft × 20 ft room; assert
   `perimeter_lf == pytest.approx(60.0, rel=0.02)` and `area_sf == approx(200.0, rel=0.02)`.
   Exact ground truth, no plan needed.
2. `test_perimeter_ignores_an_interior_hole` — same rectangle with a filled 2 ft × 2 ft block in
   the middle; perimeter must stay 60 LF (proves the trace walks the outer ring only).
3. `test_perimeter_scales_linearly_while_area_scales_quadratically` — same page measured at
   `FPP_QUARTER` and `8.0/72.0`; assert the perimeter ratio is 2 and the area ratio is 4. This is
   the §14 rule-2 guard expressed for the new primitive.
4. `test_shape_ratio_of_a_square_is_four` — assert `P/√A ≈ 4.0 ± 0.05`; and a 1 ft × 40 ft sliver
   asserts `> 8.0` (the annotation-cell detector).
5. `test_closed_ring_simplification_does_not_collapse` — regression for the DP hazard in step 3;
   assert `_simplify_ring` of a traced square returns ≥ 4 vertices and a non-zero length.
6. `test_wall_area_for_unit_multiplies_perimeter_by_height` and
   `test_wall_area_flags_when_height_source_is_not_the_drawing`.

**Fusion level** — extend the existing fusion tests (same style as `_fuse_room_fills`' current
coverage):

7. Bundle with one `RoomFillResult(plan_kind="AR", perimeter_lf=60.0, wall_height_ft=9.0,
   wall_height_source="drawing")` + vocabulary `{"Gyp Wall": {"basis": "wall_area", "unit": "SF"}}`
   + `room_mix={"king a": 26}` → exactly one component, `quantity == 14040.0`,
   `provenance == "geometry"`, `needs_review is False`.
8. Same, `wall_height_source="default"` → `needs_review is True` and the reason names the source.
9. Degenerate fill (all regions `shape_ratio > 8`) → a component with `quantity == 0.0` and
   `needs_review is True`. **It must still appear** — a missing row reads as "not required", a
   flagged zero reads as "we could not measure this".
10. `_fuse_wall_classes` and `_fuse_room_fills` both offered `Gyp Wall` on one sheet → exactly one
    survives in `components`, the other is in `fusion_rejected` with
    `reason == "superseded_by_room_fill"`. Guards the `aggregate_takeoff` summing landmine.

**Whole-suite regression**

```
python3 -m pytest -q            # 1132 tests, golden excluded by default (pytest.ini)
python3 -m pytest -q tests/test_room_fill.py tests/test_fusion.py -x
```

**Real-plan probes** (free, no API — this is the evidence that the binding actually fired):

```
python3 scripts/room_probe.py "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf" \
        --engine fill --pages 23,27,29,33
```

Blind acceptance criteria — **shape and position only, never a golden count**:

* `area_sf` per fill is byte-identical to the pre-change run (the perimeter work must not perturb
  the area path). Diff the two probe outputs.
* Every RCP prototype fill reports `wall_height_ft == 9.0`, `wall_height_source == "drawing"` —
  and specifically **not 15.0**, which is today's project answer.
* The dominant region's `shape_ratio` on every guestroom RCP is inside `[4.0, 6.0]`.
* `perimeter_lf / area_sf` for a guestroom lands in `[0.20, 0.45]` per foot — the geometric band for
  a 150–400 SF rectilinear room. A leaking fill breaks it immediately.
* Every AR fill whose `shape_ratio > 8` (KING A, KING SUITE B, QQ A today) emits a flagged row, not
  a number.
* Project-wide: `python3 scripts/score_report_dir.py` on a saved offline report directory, to
  confirm no previously-passing item regressed. (Read its `argparse` for the exact flags before
  running; it is offline, but it wants a report dir, not a PDF.)

---

## 9. Risks

* **Double counting.** `aggregate_takeoff` (`aggregator.py:235`) sums same-named buckets and
  `fuse_sheet` does not dedupe across `_fuse_*` helpers. Without step 12, Moxy's `Gyp Wall` becomes
  `2,745 + room-fill` and the number improves for the wrong reason. Highest-severity risk here.
* **A wrong height that does not flag.** 15 ft from a roof-plan `CLEAR REQ'D` arrives with
  `source="plan"`, so `is_default` is False and nothing flags. Until step 7 lands, any wall-area
  room-fill binding inherits it at `confidence: high`. Consider narrowing Tier 1 of
  `_resolve_project_wall_height` (`takeoff_pipeline.py:899-905`) to reject `CLEAR REQ'D` and
  callouts found on roof/site sheets — but that is a separate change with its own blast radius
  across Crow (which relies on `36' CLEAR`), so scope it deliberately.
* **The AR raster leaks on at least 5 of 16 prototype sheets** (`ACC QQ RIS` 42.5 SF,
  `ACC BUNK` 62.9 SF, `KING A` shape ratio 8.62, `KING SUITE B` 9.04, `QQ A` 8.54). Wall area binds
  to AR by discipline. Expect a meaningful share of flagged zeros on the first run. That is the
  correct outcome — the alternative is silently substituting the RCP raster, which is the exact
  peeking §14.3 warns about.
* **Shared-partition accounting is an open modelling question.** Summing every region's outer
  perimeter counts a partition between bedroom and bath twice (once per side), which is right if
  the estimator bills board faces and wrong if they bill wall length once. Resolve it by reading
  how the estimator's legend describes the item, or by asking the human — **not** by trying ratios
  until a total matches.
* **Performance.** `_label_regions` is a pure-Python BFS over ~1.2 M pixels per clip; the 40-page
  Moxy fill probe took several minutes. Contour tracing is O(boundary) and adds little, but the
  existing cost is already the dominant term and will be felt on larger sets. Do not raise
  `DEFAULT_DPI` (`room_fill.py:65`) as part of this work.
* **`room_fill.to_dict` is consumed downstream** (report + learning store). Adding fields is
  additive, but confirm no consumer iterates the dict positionally before shipping.

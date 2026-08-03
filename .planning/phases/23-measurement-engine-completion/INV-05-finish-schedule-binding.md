# INV-05 — Finish Schedule → Room Binding (Moxy WC-1..WC-10 = 0)

Investigator: subagent, read-only. Every number below came from a free offline probe
(zero API calls). Probe sources live in the session scratchpad, not the repo.

---

## TL;DR

**The gap's premise is wrong, and that is the finding.** There is no finish schedule in the
Moxy input to bind. Sheet **CS-03 "NOTES, REQUIREMENTS, FINISH SCHEDULES" is listed in the
drawing index on page 1 but is not in the 40-page PDF** (present CS sheets: CS-00, CS-01,
CS-02, CS-11, CS-31). `extract_schedules(..., kinds=["finish"])` returns **zero tables on all
four real plan sets** — the `finish` kind only ever fires on the synthetic fixture in
`tests/test_tables.py:85`.

WC-1..WC-10 were never measured from a schedule. Diffing the take-off PDF against the plans
PDF page-for-page shows the estimator's per-sheet Legend boxes, and **every WC quantity lives
on an interior-elevation sheet** (ID-200..ID-205 = pages 15,16,18,19,20). Those five legends
sum to **7,432.05 SF — the golden 7,432 SF exactly**. So the real join is
**finish tag → the elevation region it annotates**, not room-number → finish-code.

That join key **is** deterministically extractable. A direction-generic reader of the
two-token material tag (`WC` + `07`, adjacent along the text's own reading direction)
recovers the **exact set of WC codes on 6/6 elevation sheets, including a true negative on
p17** — validated by SET membership against the estimator's legends, never by quantity.

The area, however, is **not** obtainable: seeded flood fill at every WC tag leaks to the clip
edge (365–909 SF regions where the golden is 88–175 SF/tag) because an elevation's wall face
is not a closed ink region. **So the correct behaviour is to emit a named, flagged,
zero-quantity row per (finish code, sheet) and route it to the existing human measure
workspace — never to guess an area.** Today the pipeline emits *nothing*, and silence is
indistinguishable from zero.

**Bonus, and larger than the gap itself:** `_manifest_room_mix`
(`src/bobbytailor/pipeline/takeoff_pipeline.py:624`) documents in its docstring that the unit
multiplier is "routinely not in the drawing set at all … so no reading of the plan can recover
it", and `docs/PIPELINE-GROUND-TRUTH.md:352` calls this "BLOCKER A". **That is false.** Pages 7
and 8 (ID-001 / ID-002) are stacked unit key plans carrying 217 room tags with **217 distinct
room numbers, zero duplicates**. Counting them blind yields **QQ A 90, KING A 26, K SUITE B 2,
BUNK B 1 — a 4/4 exact match against the golden multipliers** in
`docs/PIPELINE-GROUND-TRUTH.md:346-351`. The room mix is in the input.

---

## 1. What I ran, and what it printed

### 1.1 Schedule extraction on all four real plan sets

`src/bobbytailor/deterministic/tables.py:439` ships a `__main__` harness. Free, no API.

```
$ python3 -m bobbytailor.deterministic.tables "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf"
=== Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf ===
  page 6: kind=door rows=60 bbox=(776.8, 44.9, 1883.0, 1288.2) conf=high

$ python3 -m bobbytailor.deterministic.tables "uploads/Crow - Cass White Road-Plans.pdf"
=== Crow - Cass White Road-Plans.pdf ===
  page 3: kind=door rows=5 bbox=(1422.4, 223.9, 2307.4, 340.3) conf=high

$ python3 -m bobbytailor.deterministic.tables "uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf"
=== Bob's Discount Furniture - Kennesaw, GA-plans.pdf ===
  page 3: kind=keynote rows=4 bbox=(99.0, 35.7, 2969.9, 2124.5) conf=high
  page 4: kind=keynote rows=8 bbox=(100.9, 35.7, 2969.9, 2124.4) conf=medium

$ python3 -m bobbytailor.deterministic.tables "uploads/Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf"
=== Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf ===
  (no tables)
```

**`kind="finish"` fires zero times across every real input.** The `finish` vocabulary
(`tables.py:108-114`) requires `page.find_tables()` to return a ruled grid whose header row
contains `FINISH`/`FINISHES` and whose tag column matches `_ROOM_TAG_RE = ^\d{2,4}[A-Z]?$`
(`tables.py:51`). Moxy has no such sheet at all.

### 1.2 The finish-schedule sheet is absent from the input

Front-matter sheet identity and the page-1 drawing index:

```
p0: [('CS-00', 1)]
p1: [('CS-01', 2), ('ID-01', 1), ('ID-001', 1), ('ID-002', 1)]
p2: [('CS-02', 1)]
p3: [('CS-11', 2), ('CS-31', 1)]
p4: [('CS-11', 1)]
p5: [('CS-31', 1)]

--- page 1 index rows mentioning FINISH / MATRIX / SCHEDULE ---
    ● | ● | A7-01 | DOOR SCHEDULES | ●
    ● | ● | CS-03 | NOTES, REQUIREMENTS, FINISH SCHEDULES | ●
    ● | ● | CS-04 | GUESTROOM MATRIX | ●
```

CS-03 and CS-04 are indexed; neither sheet is in the PDF. There is nothing to parse.

### 1.3 Where the WC quantities actually came from (take-off vs plans diff)

The take-off PDF is the same 40 sheets with a "Legend" box overlaid. Subtracting the plans'
text lines from the take-off's text lines isolates exactly what the estimator added:

```
================== takeoff page 15 extra lines: 7
    13'-6 ⅝" | 13'-10 ½" | Legend | WC-1 | 2,037.13 SF | WC-2 | 225.43 SF
================== takeoff page 16 extra lines: 10
    8'-10 ⅜" | Legend | WC-1 | 843.51 SF | WC-2 | 424.04 SF | WC-4 | 169.28 SF | WC-7 | 317.06 SF
================== takeoff page 17 extra lines: 5
    Legend | Guard Rail | 23.01 LF | Hand Rail | 23.50 LF
================== takeoff page 18 extra lines: 9
    8'-11 ¾" | 9'-4 ½" | 10'-9 ⅝" | 3'-7" | Legend | WC-6 | 1,136.62 SF | WC-7 | 1,253.94 SF
================== takeoff page 19 extra lines: 6
    10'-3 ⅞" | Legend | WC-9 | 523.84 SF | WC-10 | 148.77 SF
================== takeoff page 20 extra lines: 3
    Legend | WC-8 | 352.43 SF
================== takeoff page 27 extra lines: 11
     | Legend | Door Frame-HM | 2 EA | Doors-WD | 2 EA | Guestroom-Wall Coveri... 366.43 SF | Gyp Ceiling | 706.76 SF | Gyp Wall | 1,566.65 SF
```

2037.13 + 225.43 + 843.51 + 424.04 + 169.28 + 317.06 + 1136.62 + 1253.94 + 523.84 + 148.77 +
352.43 = **7,432.05 SF**, matching the golden `WC-1..WC-10 7,432 SF`
(`docs/PIPELINE-GROUND-TRUTH.md:321`) to the rounding.

Two independent observations follow:

1. **WC-1..WC-10 are elevation quantities, on ID-200..ID-205.** They are not room finishes
   keyed by room number. Pages 15–20 are interior elevations of the public spaces.
2. **The bare dimension strings the estimator added** (`13'-6 ⅝"`, `8'-11 ¾"`, `3'-7"`) are
   their own measurement markup. The estimator drew the rectangles by hand. The drawing does
   not delimit them.

`Guestroom-Wall Covering` is a different animal: it is a per-prototype-sheet quantity
(page 27 = ID-411, 366.43 SF beside Gyp Ceiling 706.76 and Gyp Wall 1,566.65), and **no WC
code appears anywhere on the guestroom sheets** — I checked pages 23, 26, 31 for two-token
material tags and got `[]` on all three.

---

## 2. The join keys that actually exist

### Key A — material/finish tag: `<PREFIX>` + `<NN>`, adjacent along the reading direction

Moxy draws finish callouts as a two-token tag inside a symbol: `WC` then `01`, then a
spelled-out `WALLCOVERING`. **The layout differs by text rotation and a naive rule fails.**
On p15 the tag is rotated (`dir=(0,-1)`) and the tokens stack in −y:

```
'WC'           (116.6, 2123.2, 128.3, 2138.5) dir=(0, -1)
'01'           (116.6, 2103.0, 128.3, 2112.5) dir=(0, -1)
'WALLCOVERING' (116.6, 2021.1, 128.3, 2090.3) dir=(0, -1)
```

On p18 the same tag is unrotated (`dir=(1,0)`) and the tokens run in +x:

```
'WC'           (908.4, 217.4, 923.7, 228.8) dir=(1, 0)
'07'           (934.2, 217.4, 943.6, 228.8) dir=(1, 0)
'WALLCOVERING' (956.4, 217.4, 1025.7, 228.8) dir=(1, 0)
```

The invariant is the same in both: **project each line's bbox onto its own `dir` axis; the
number token starts 0–16 pt after the prefix token ends, with perpendicular overlap.** A
first pass that only handled the rotated case found tags on p15/p16 and *nothing* on
p18/p19/p20. The direction-generic rule gets all six:

```
p15: WC={'WC-1': 9, 'WC-2': 1}                    golden=['WC-1', 'WC-2']            -> EXACT
      other tags: ['AT-2','PT-3','PT-4','PT-8','T-11A','T-11B','WD-1','WD-2']
p16: WC={'WC-1': 6, 'WC-2': 3, 'WC-4': 6, 'WC-7': 1} golden=['WC-1','WC-2','WC-4','WC-7'] -> EXACT
      other tags: ['PT-1','PT-4','WD-1']
p17: WC={}                                        golden=[]                          -> EXACT
      other tags: ['PT-4','PT-5','ST-1','WD-7']
p18: WC={'WC-6': 5, 'WC-7': 7}                    golden=['WC-6','WC-7']             -> EXACT
      other tags: ['PT-4','PT-5','PT-6','ST-2','WD-3','WD-4','WD-5','WD-6']
p19: WC={'WC-10': 2, 'WC-9': 3}                   golden=['WC-10','WC-9']            -> EXACT
      other tags: ['PT-4','PT-5','RB-1']
p20: WC={'WC-8': 4}                               golden=['WC-8']                    -> EXACT
      other tags: ['PT-5','WD-6']

WC finish-code SET recovered exactly on 6/6 elevation sheets
```

**This is validated by SET, not by count.** The tag counts (9, 6, 5, …) are deliberately *not*
compared to anything — they are callout instances, not regions, and tuning them toward a
quantity is the §10 "136 columns" trap. What is validated is *which finish codes appear on
which sheet*, plus a true negative on p17 where the estimator measured guard rail instead.
The extractor also recovers PT/WD/AT/T/ST/RB codes for free, which is the whole public-space
finish vocabulary.

### Key B — room tag: `<ROOM NAME>` + `<ROOM NUMBER>` on ID-001 / ID-002

Take-off page 2 (CS-02) prints the symbol legend for this set verbatim:
`ROOM TAG / ROOM NAME / ROOM NUMBER` and `UNIT TAG / UNIT NUMBER / UNIT TYPE`. Pages 7 and 8
are the stacked unit key plans. Applying the same direction-generic adjacency rule (rotated
text, name to the left of the number):

```
page 7 title-ish: ['ID-001', 'ID-001']
page 8 title-ish: ['ID-002', 'ID-002']
total pairs: 217 distinct room numbers: 217 duplicated numbers: {}
  QQ A         n= 90  nums=['206','207','208','209','210','213','215','217','219','225','227','229']...
  KING A       n= 26  nums=['204','221','245','247','249','304','321','345','347','349','404','421']...
  KING B       n= 15  nums=['230','232','234','330','332','334','430','432','434','530','532','534']...
  QQ C         n= 15  nums=['203','243','303','341','343','403','441','443','503','541','543','603']...
  K SUITE A    n=  5  nums=['223','323','423','523','623']
  K SUITE B    n=  2  nums=['602','702']
  QQ B         n=  6  nums=['205','305','405','505','605','705']
  KING C       n=  5  nums=['211','311','411','511','611']
  BUNK B       n=  1  nums=['241']
  BUNK A       n=  1  nums=['601']
  KING (T)     n=  3  nums=['302','402','502']
```

217 tags, 217 unique numbers, no double-count; the numbering is floor-prefixed (2xx…7xx), so
ID-001 + ID-002 together cover levels 2–7.

Golden multipliers from `docs/PIPELINE-GROUND-TRUTH.md:346-351`: ID-413 QQ A **90**,
ID-407 KING A **26**, ID-411 KING SUITE B **2**, ID-417 BUNK B **1**.
Extracted blind: QQ A **90**, KING A **26**, K SUITE B **2**, BUNK B **1**. **4/4 exact.**

Nothing was tuned: the pairing rule is the drawing set's own documented ROOM TAG convention,
and the comparison was made after the extraction.

### Key C — prototype name: `PLAN_TITLE_RE`

`room_fill.plan_titles` (`src/bobbytailor/deterministic/room_fill.py:115`) already yields the
name that Key B counts:

```
p23: plan_titles=[('KING A','AR'),('KING A','FF'),('KING A','FF'),('KING A','FC'),('KING A','EM'),('KING A','RCP')]
p26: plan_titles=[('KING SUITE A','AR'),('KING SUITE A','FF'),('KING SUITE A','RCP'),('KING SUITE A','FC'),('KING SUITE A','EM')]
p31: plan_titles=[('QQ C','AR'),('QQ C','FF'),('QQ C','FF'),('QQ C','RCP'),('QQ C','FC'),('QQ C','EM')]
```

So the binding chain that exists end-to-end today is:

```
RoomFillResult.plan_name ("KING SUITE B")   [Key C, room_fill.py:97]
        │  normalize
        ▼
unit-tag census from ID-001/ID-002          [Key B, pages 7-8]  → unit_count = 2
        │
        ▼
_fuse_room_fills room_mix lookup            [fusion.py:1561-1562]
```

and the chain that does **not** exist is:

```
finish tag "WC-7" on ID-203                 [Key A, extractable, 6/6]
        │
        ▼
      ???  no measured region, no component, no row     ← THE GAP
```

### Why the elevation sheets produce nothing today

```
p15: plan_titles=[]   printed_scales=[4.0 × 12]
p16: plan_titles=[]   printed_scales=[4.0 × 15]
p17: plan_titles=[]   printed_scales=[4.0 × 17]
p18: plan_titles=[]   printed_scales=[4.0 × 10]
p19: plan_titles=[]   printed_scales=[4.0 ×  9]
p20: plan_titles=[]   printed_scales=[4.0 ×  5]
```

`_measure_room_fills` (`src/bobbytailor/pipeline/takeoff_pipeline.py:1773`) iterates
`plan_titles(page)` and returns `[]` when it is empty. Every WC-bearing sheet has zero plan
titles and 5–17 printed scale callouts at 4.00 ft/in. **The measurement loop never executes on
the sheets that hold 7,432 SF of golden quantity.**

---

## 3. Why the area cannot be flood-filled (do not attempt it)

I seeded a flood fill at each WC tag centre, at that tag's nearest printed scale, in a 680 pt
box:

```
p20 WC-8: 4 tags, golden total 352.43 SF -> 88.1 SF/tag
    tag@(727, 276)  fpi=4.00 -> (770.7, True)
    tag@(1300, 289) fpi=4.00 -> (783.7, True)
    tag@(1946, 270) fpi=4.00 -> (804.0, True)
    tag@(497, 799)  fpi=4.00 -> (848.2, True)
    sum of non-edge seeded regions = 0.0 SF (golden 352.43)

p19 WC-9: 3 tags, golden total 523.84 SF -> 174.6 SF/tag
    tag@(662, 722)  fpi=4.00 -> (365.4, True)
    tag@(1692, 726) fpi=4.00 -> (909.4, True)
    tag@(2491, 754) fpi=4.00 -> (681.0, True)
    sum of non-edge seeded regions = 0.0 SF (golden 523.84)
```

(`True` = the region reached the clip edge.) Every fill leaks and every area is 4–10× the
golden. An elevation's wall face is bounded by a floor line and a ceiling line but is open
laterally into the adjacent surface — it is **not** an enclosed ink region, which is the one
precondition `room_fill` states in its module docstring
(`src/bobbytailor/deterministic/room_fill.py:12-16`). Recipe E does not transfer to elevations.

**Related open problem — region perimeter is also not solved.** The obvious route to
`Guestroom-Wall Covering` and `Gyp Wall` is perimeter × height × units, but
`FilledRegion` (`room_fill.py:77`) carries only `area_sf`, `px`, `touches_edge` — there is no
perimeter, and naive raster boundary counting is unusable:

```
========== ID-411 KING SUITE B (page 27, 2 units, golden Gyp Wall 1,566.65 SF)
   region area=  249.4 SF  raster_perim=  245.6 LF  bbox_perim=  70.8 LF
   region area=   34.4 SF  raster_perim=   43.6 LF  bbox_perim=  37.7 LF
   region area=   26.2 SF  raster_perim=   63.3 LF  bbox_perim=  49.5 LF
   region area=   25.1 SF  raster_perim=   63.0 LF  bbox_perim=  44.1 LF
   region area=   17.3 SF  raster_perim=   40.2 LF  bbox_perim=  28.7 LF
   region area=    9.4 SF  raster_perim=   29.9 LF  bbox_perim=  16.8 LF
   region area=    8.1 SF  raster_perim=   30.8 LF  bbox_perim=  28.0 LF
   AR perim x 9ft x 2 units = 9,297.0 SF   (golden Gyp Wall 1,566.65)
```

Raster boundary over-counts ~5.9× (staircasing plus every interior fixture outline). The
largest region's bbox perimeter (70.8 LF, area 249.4 SF → a 25.7 ft × 9.7 ft room, textbook
for a King Suite) is the only plausible figure, and back-solving a height from the golden
gives 11.06 ft. **Do not pick a height that makes 1,566.65 come out.** That is the coincidence
trap. Perimeter needs a real contour trace + rectilinear simplification, validated against the
sheet's own printed dimension strings, and it is a separate work item.

---

## 4. Code-level root cause, by function

| # | Location | What it does today | Why the quantity is absent |
|---|---|---|---|
| 1 | `deterministic/tables.py:108-114` (`SCHEDULE_KIND_VOCABULARIES["finish"]`) | Requires a ruled `find_tables()` grid with a `FINISH` header and numeric room tags | Fires on zero real plan sets; Moxy's CS-03 is not in the PDF. Dead capability. |
| 2 | `deterministic/room_fill.py:115` (`plan_titles`) | Anchors measurement on `<NAME> - <KIND> PLAN` | Returns `[]` on pages 15–20, so `_measure_room_fills` (`takeoff_pipeline.py:1773`) never runs on any WC-bearing sheet |
| 3 | `vision/fusion.py:1601` (`_ROOM_FILL_BASES`) | `{"ceiling_area","roof_area","floor_area"}` | Excludes `wall_area`, so `_fuse_room_fills` cannot emit any wall/finish area even when a fill exists. `room_fill.BASIS_PLAN_KIND` maps `"wall_area": "AR"` at `room_fill.py:58` — **a dead mapping with no consumer.** |
| 4 | `deterministic/room_fill.py:77` (`FilledRegion`) | Carries `area_sf`, `px`, `touches_edge` | No perimeter ⇒ no wall/finish area is derivable from a fill at all |
| 5 | `vision/fusion.py:1741` (`_fuse_schedules`) | Every schedule row → `quantity = 1.0`, `unit = "EA"` (`fusion.py:1757-1763`) | Even if a finish schedule parsed, `WC-1` would emit as `1 EA`, never SF |
| 6 | *(nothing)* | — | **No function reads a finish/material tag from the plan body.** There is no `finish` symbol reader, no code path from a finish code to any region, and no "unmeasured finish" row. The absence is silent. |
| 7 | `pipeline/takeoff_pipeline.py:624` (`_manifest_room_mix`) | Reads `unit_count` only from manifest entries | Docstring asserts the mix is unrecoverable from the plans; pages 7–8 disprove it (4/4 exact) |

Blocker 6 is the one that matters most: `scripts/export_takeoff_excel.py:39-41` already
renders a zero-quantity row as `NOT MEASURED` with the About-sheet caption *"Do NOT read a
blank as zero."* The machinery to communicate "we found this finish and did not measure it"
exists. Nothing feeds it, so WC-1..WC-10 are simply **absent** from the summary — the worst of
the three states.

---

## 5. Implementation map

Ordered. Each step names the function, what it must do, and how it is checked for free.
All Python 3.9-compatible (`typing.List/Dict/Optional`, no `X | Y`, no `match`).

### Step 1 — new `deterministic/finish_tags.py::extract_material_tags(page) -> List[MaterialTag]`

The join-key reader. `MaterialTag` is a dataclass: `code` (`"WC-7"`), `prefix` (`"WC"`),
`number` (`"07"`), `bbox_pt`, `page_index`, `text_dir`.

Algorithm (proven 6/6 above):
1. Walk `page.get_text("dict")` lines; keep `(text, bbox, dir)` with `dir` rounded to ints.
2. A tag is a `prefix` line matching a registry of finish prefixes
   (`WC|WD|PT|AT|T|CPT|LVT|SC|CT|RB|ST|MTL|GL`) followed by a `^\d{2}[A-Z]?$` line.
3. **Adjacency is measured along the line's own `dir`**, not in page x/y. Project both bboxes:
   `dir=(1,0) -> (x0,x1,y0,y1)`; `dir=(-1,0) -> (-x1,-x0,y0,y1)`;
   `dir=(0,-1) -> (-y1,-y0,x0,x1)`; `dir=(0,1) -> (y0,y1,x0,x1)`. Require
   `0 <= next.start - prefix.end < 16.0` pt and perpendicular-range overlap (±3 pt).
   Both `dir`s must be equal. **This is the step a naive implementation gets wrong** — the
   y-stacked-only version silently returns `{}` on p18/19/20.
4. Normalize `code = "%s-%s" % (prefix, number.lstrip("0") or "0")`.
5. Skip tags whose bbox falls inside a `ScheduleTable.bbox_pt` or a `title_block`/`legend`
   viewport, reusing the masks `_deterministic_bundle` already computes.

Add `MaterialTag` list to the bundle in `TakeoffPipeline._deterministic_bundle`
(`takeoff_pipeline.py:1745-1760`) as `"material_tags"`, next to `"schedules"`. Additive: a
failure leaves the list empty.

### Step 2 — `vision/fusion.py::_fuse_material_tags(bundle, components)` (new)

Called from `fuse_sheet` at `fusion.py:1926`, immediately after `_fuse_schedules`.

For each distinct `code` on the sheet, emit **one** component:

```python
{
    "name": code,                      # "WC-7" — a text-layer label, not a vision guess
    "quantity": 0,
    "unit": "SF",
    "provenance": "text_layer",
    "confidence": "low",
    "candidate_id": "FINISH-%s" % code,
    "name_source": "material_tag",
    "needs_review": True,
    "review_reason": (
        "finish %s is called out %d time(s) on %s but its extent is not a closed "
        "region on this drawing — area not measured; measure it in the workspace"
        % (code, n_tags, sheet_name)
    ),
    "tag_positions_pt": [t.bbox_pt for t in tags],   # seeds the measure UI
}
```

`quantity=0` + `needs_review` renders as `NEEDS REVIEW` in
`scripts/export_takeoff_excel.py:38-45`; drop `needs_review` and it renders `NOT MEASURED`.
Either is correct and both beat absence. **Do not synthesize an area.**

`tag_positions_pt` lets the reports workspace pre-place the shapes: `finishMeasureShape` /
`measureQty` in `src/bobbytailor/web/static/js/reports-workspace.js` already POST to
`/measurements`, which accepts `measure_type` in `takeoff_measurements.VALID_TYPES`
(`deterministic/takeoff_measurements.py:32`) and converts `area` via
`polygon_area_pt2(pts) * fpp**2` (`takeoff_measurements.py:114`). The human draws each WC
rectangle once; `verify.py`'s `POST /measurements` handler captures it into the learning store
(`web/blueprints/verify.py:18-21`). **This is the whole point: a flagged named row is a task a
human can close in seconds; an absent row is invisible.**

### Step 3 — `deterministic/room_tags.py::extract_room_tags(page) -> List[RoomTag]` (new)

Same direction-generic adjacency primitive as Step 1, different vocabulary: a `RoomTag` is a
name line (alphabetic, not a number) adjacent to a `^(?:\d{3}|[A-Z]\d{1,2})$` line. Fields:
`name`, `number`, `bbox_pt`, `page_index`.

Factor the projection helper (`_project_bbox(bbox, text_dir)`) into a shared module —
`deterministic/tag_pairing.py` — so Steps 1 and 3 use one implementation. That single helper
is the load-bearing piece of both keys.

### Step 4 — `pipeline/takeoff_pipeline.py::_derive_room_mix(doc) -> Dict[str, int]` (new)

Census the whole document's room tags, key by `" ".join(name.split()).strip().lower()`, and
**require room-number uniqueness**: if the same number appears twice, the sheets overlap —
return `{}` for that name and flag, rather than double-count. (On Moxy: 217 tags, 217 unique
numbers, so it passes cleanly.)

Then change `_manifest_room_mix` (`takeoff_pipeline.py:624`) to
`_resolve_room_mix(manifest, doc)`: manifest entries win where present, derived counts fill
the rest, and every derived count is tagged `"source": "unit_tag_census"` so
`_fuse_room_fills` can put it in the formula string. Correct the docstring at
`takeoff_pipeline.py:626-632` and the "BLOCKER A" claim at
`docs/PIPELINE-GROUND-TRUTH.md:352` — the multiplier **is** in the input.

This is the single highest-value change in this map: it unblocks the `× units` factor for
Gyp Ceiling, Gyp Wall, Guestroom-Wall Covering, and Doors simultaneously, with zero human
input.

### Step 5 — `deterministic/room_fill.py::FilledRegion` gains `perimeter_lf`, computed by a contour trace

`_label_regions` (`room_fill.py:148`) already visits every boundary pixel. Add a
**Moore-neighbour contour trace of the outer boundary only** (holes excluded — a fixture
outline inside the room must not add wall), then **rectilinear simplification**: collapse
runs whose direction is constant to within one pixel, then drop segments shorter than
`0.5 ft` at the current scale. Surface `perimeter_lf` on `RoomFillResult` as the sum over
kept regions.

**Do not ship this on the raw boundary count.** Section 3 shows it over-reads ~5.9×.

### Step 6 — validate Step 5 against the drawing's own printed dimensions, not against golden

`deterministic/dimensions.py` already reads printed dimension strings. For each measured
region, compare its bbox width/height in feet to the nearest parallel printed dimension on
the same viewport. Accept the perimeter only when the measured extents agree with the printed
extents within 3%. This is a **non-circular, in-document** check and it is free. If it does
not agree, `needs_review=True` and no perimeter is published.

### Step 7 — add `"wall_area"` to `_ROOM_FILL_BASES` (`fusion.py:1601`), gated on Step 6

Only after Steps 5–6 land. In `_fuse_room_fills` (`fusion.py:1516`), when
`basis == "wall_area"`, use `pick.perimeter_lf * wall_height_ft * unit_count` and require
**both** a verified perimeter and a non-default `wall_height_source`; otherwise emit
`quantity=0, needs_review=True`. This retires the dead `BASIS_PLAN_KIND["wall_area"]` mapping
at `room_fill.py:58`.

`Guestroom-Wall Covering` is **not** derivable even then: golden is 183.2 SF/unit against
783.3 SF/unit of Gyp Wall (23%), i.e. an accent wall the drawing does not designate on the
guestroom sheets (verified: zero material tags on pages 23/26/31). Emit it via Step 2's
flagged path, named from the vocabulary, quantity 0.

### Step 8 — make the dead `finish` schedule kind honest

Leave `SCHEDULE_KIND_VOCABULARIES["finish"]` in place (a ruled finish schedule is real on
other drawing sets), but **fix `_fuse_schedules` (`fusion.py:1741`) so a `finish`-kind row
never emits `1 EA`.** A finish schedule row is a *type declaration*, not an installed
quantity. For `kind == "finish"`, emit `quantity=0, unit="SF", needs_review=True` with the
room tag in the reason — the same shape as Step 2, so the two paths converge. Note in the
module docstring that the kind has never fired on a real input as of this investigation.

---

## 6. Offline verification (all free, zero API)

```bash
# 1. Finish schedules: still zero on every real set (regression guard for Step 8).
for f in "Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf" \
         "Crow - Cass White Road-Plans.pdf" \
         "Bob's Discount Furniture - Kennesaw, GA-plans.pdf" \
         "Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf"; do
  python3 -m bobbytailor.deterministic.tables "uploads/$f"
done
# assert: no line contains "kind=finish"

# 2. Step 1 acceptance — WC code SET per sheet, compared to the estimator's legends.
python3 -m bobbytailor.deterministic.finish_tags \
  "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf"
# assert exactly:
#   p15 {WC-1, WC-2}    p16 {WC-1, WC-2, WC-4, WC-7}   p17 {}
#   p18 {WC-6, WC-7}    p19 {WC-9, WC-10}              p20 {WC-8}
# Assert the SET only. Never assert tag counts against a golden SF figure.

# 3. Step 1 rotation regression — the bug a naive implementation ships.
#    p15 tags are dir=(0,-1); p18 tags are dir=(1,0). Both must resolve.
# assert: p18 set is non-empty (a y-stacked-only reader returns {} here)

# 4. Steps 3-4 acceptance — room-mix census, uniqueness first.
python3 -m bobbytailor.deterministic.room_tags \
  "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf"
# assert: 217 tags, 217 distinct numbers, 0 duplicates
# assert: QQ A=90, KING A=26, K SUITE B=2, BUNK B=1
#         (matches docs/PIPELINE-GROUND-TRUTH.md:346-351, derived independently)

# 5. Step 2 acceptance — the flagged rows exist and carry no invented area.
python3 scripts/score_report_dir.py <run_dir>      # read its --help first
# assert: rows named WC-1..WC-10 are PRESENT with quantity 0 and needs_review=True
# assert: no WC row has quantity > 0 unless a human /measurements POST created it

# 6. Step 5-6 acceptance — perimeter must NOT regress area.
python3 scripts/room_probe.py \
  "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf" --fpi 4.0 --pages 27,29
# assert: ID-411 RCP area stays 341.7 SF (the 3.3% blind result, PIPELINE-GROUND-TRUTH.md:408)
# assert: every published perimeter passed the printed-dimension cross-check (Step 6)

# 7. Whole offline suite (paid golden marker excluded by default).
python3 -m pytest -q
```

Forbidden throughout, and not used anywhere in this investigation: `pytest -m golden`,
`scripts/accuracy_gate.sh`, `scripts/vision_only_benchmark.py`, `scripts/golden_convergence.py`.

---

## 7. Risks

1. **Tuning the perimeter height to hit 1,566.65 SF.** Section 3 back-solves to 11.06 ft,
   which is not a guestroom ceiling. Any height chosen to make Gyp Wall land is the §10
   coincidence trap. Step 6's printed-dimension cross-check is the only admissible validation.
2. **Widening the tag-adjacency gap past 16 pt.** The prefix registry contains one-letter
   codes (`T`, `SC`) and drawings are dense with stray two-digit numbers. A looser gap will
   manufacture codes that do not exist and break the 6/6 set match. Tighten before loosening.
3. **`extract_material_tags` firing inside schedules and title blocks.** Door-schedule tag
   columns and legend keys look exactly like plan-body callouts — the same false-positive
   class `_is_door_table` (`schedule_extraction.py:170`) was built to reject. The bbox masks
   in Step 1.5 are mandatory, not optional.
4. **Deriving the room mix from a partial sheet set.** Moxy's ID-001/ID-002 happen to cover
   levels 2–7 with unique numbers. A set with per-floor key plans would double-count. The
   number-uniqueness gate in Step 4 must **fail closed** (return `{}` and flag), never fall
   back to a partial census.
5. **Flag fatigue.** Steps 2 and 8 add roughly 10 WC rows plus PT/WD/AT/T/ST/RB rows per
   elevation sheet. Group by code across sheets and cap the emitted set, or the review queue
   becomes noise and gets ignored — which returns us to silent zeros by another route.
6. **Correcting `docs/PIPELINE-GROUND-TRUTH.md` "BLOCKER A".** The doc is the project's
   honesty anchor; the correction must cite the ID-001/ID-002 census and the 4/4 match, not
   just delete the claim.

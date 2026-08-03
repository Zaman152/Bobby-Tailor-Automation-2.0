# INV-02 — The "~2× clip defect" (GAP 2): implementation map

Investigator: read-only pass, 2026-08-03. Every number below came from a **free offline probe** against
the real `uploads/` PDFs (zero API calls). No golden number was used to select or tune anything; golden
is quoted only at the end, to score.

---

## TL;DR

**The clip is not the defect. The multiplier is.** ID-412 and ID-416 do **not** leak into a neighbouring
plan — three independent geometric probes exonerate the clip:

1. Widening the clip by ±80 pt per side (a 160 pt-wider window) changes ID-412 by **0.0 SF** and ID-416
   by **0.5 SF**, while it changes ID-407 by **+38.8 SF**, ID-413 by **+30.2 SF** and ID-415 by
   **+57.5 SF**. The two "defective" sheets are the *least* clip-sensitive of all 16.
2. Every enclosed region the fill counts on ID-412 lies inside a **339 × 502 pt** column — 47 % of the
   715 × 612 pt clip. Nothing from a neighbour is inside it.
3. The drawing's **own printed overall dimensions** — `17'-0 1/8"` × `26'-9 1/8"` = **455.2 SF** — match
   the fill (**458.3 SF**, ratio 1.007). A clip that had swallowed a second unit would read ≈ 2.0.

The `458.3 SF` measurement of ID-412 is **correct to 0.7 %** of the estimator's own sheet total
(461.49 SF). The ~2× appears one layer later: `total_for_units()`
(`src/bobbytailor/deterministic/room_fill.py:268`) multiplies that correct single-unit area by a
`unit_count` of **2** that comes from `human_inputs/moxy_knoxville.json` — a human input derived from the
golden `Doors-WD 2 EA`, which on these sheets is *entry door + connecting door in one suite*, not two
units. Four sheets share the signature: **ID-412, ID-416, ID-420, ID-422**.

Consequences for the plan:

* **Root cause** (`§4`): an unverifiable human multiplier is applied silently and reported at
  `confidence: "high"`. Fix = a geometric *self-consistency* cross-check (printed overall dims vs fill)
  and honest provenance on the multiplied row.
* **Still fix the clip** (`§6`, steps 1–3): the fixed `±260 / 620 pt` box is genuinely fragile — adjacent
  clips overlap **8–48 %** on every prototype sheet, correctness survives only because leaked neighbours
  happen to touch the clip edge and get discarded, and the box **collapses to a 33 pt-high strip** on
  ID-109 `LEVEL 7 - RCP PLAN` (title near the page top → zero output). Replace it with a
  midpoint-partition + own-ink-extent clip. This is a robustness fix, **not** the fix for GAP 2.
* **`docs/PIPELINE-GROUND-TRUTH.md` §14.2 must be corrected**, and so must the two tests and the docstring
  that encode the wrong story (`§8`).

---

## 1. What the code actually does

| Concern | Location |
|---|---|
| Anchor titles `"<NAME> - <KIND> PLAN"` | `src/bobbytailor/deterministic/room_fill.py:49-51` (`PLAN_TITLE_RE`), `:115-128` (`plan_titles`) |
| Clip construction | `src/bobbytailor/pipeline/takeoff_pipeline.py:1824-1829` |
| Clip constants | `src/bobbytailor/pipeline/takeoff_pipeline.py:1770-1771` |
| Scale binding (callout under the title) | `src/bobbytailor/pipeline/takeoff_pipeline.py:1811-1818` |
| Raster flood fill + region filter | `src/bobbytailor/deterministic/room_fill.py:194-247`, filter at `:233-236` |
| Region size caps | `src/bobbytailor/deterministic/room_fill.py:72-73` (`MIN_REGION_SF=8`, `MAX_REGION_SF=900`) |
| Plausibility guard (the 900 SF threshold) | `src/bobbytailor/deterministic/room_fill.py:250-265`, called at `takeoff_pipeline.py:1837` with `_MAX_UNIT_SF` (`:1764`) |
| Discipline pick (AR vs RCP) | `src/bobbytailor/deterministic/room_fill.py:131-145` |
| Multiplication by the room mix | `src/bobbytailor/deterministic/room_fill.py:268-277`, called from `src/bobbytailor/vision/fusion.py:1562-1564` |
| Room mix source | `src/bobbytailor/pipeline/takeoff_pipeline.py:624-651` (`_manifest_room_mix`), data in `human_inputs/moxy_knoxville.json` |

The clip is a **fixed-size rectangle hung off the title bbox** (`takeoff_pipeline.py:1824-1829`):

```python
clip = fitz.Rect(
    tx0 - self._FILL_CLIP_SIDE_PT,          # 260 pt
    max(0.0, ty0 - self._FILL_CLIP_UP_PT),  # 620 pt
    tx1 + self._FILL_CLIP_SIDE_PT,
    max(0.0, ty0 - 8.0),
)
```

It contains **no information about the drawing's own extent**. Its only protection against a neighbour is
`touches_edge` (`room_fill.py:168`, applied at `:233-235`): a region that reaches the clip border is
treated as "outside" and dropped. That works when a neighbour is *sliced* by the clip, and fails silently
if a neighbour ever falls *wholly inside* it.

---

## 2. Probe A — real behaviour on ID-411 (good) vs ID-412 (defective)

Replica of `TakeoffPipeline._measure_room_fills` run against
`uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf`.
**Page indices: ID-411 = p27, ID-412 = p28, ID-415 = p31, ID-416 = p32** (searching page text for `ID-411`
finds the drawing index on p8 first — INV-00 §1b's warning is correct).

```
page 27  sheet='ID-411'
  plan titles: 5
     [0] KING SUITE B  AR   title_bbox=(348.4, 1479.5, 526.6, 1500.6)
     [2] KING SUITE B  RCP  title_bbox=(1054.0, 1463.1, 1247.3, 1484.3)
  --- fills ---
     [0] KING SUITE B  AR   clip=(88.4,859.5,786.6,1471.5)   w=698 h=612 fpi=4.00
           -> area=369.9 SF  n_regions=7  top=[249.4, 34.4, 26.2, 25.1, 17.3, 9.4, 8.1]
     [2] KING SUITE B  RCP  clip=(794.0,843.1,1507.3,1455.1) w=713 h=612 fpi=4.00
           -> area=341.7 SF  n_regions=6  top=[216.8, 37.7, 33.4, 24.7, 18.8, 10.3]

page 28  sheet='ID-412'
  plan titles: 5
     [0] KING SUITE C  AR   title_bbox=(316.6, 884.7, 499.9, 905.9)
     [2] KING SUITE C  RCP  title_bbox=(940.4, 1832.7, 1134.8, 1853.9)
  --- fills ---
     [0] KING SUITE C  AR   clip=(56.6,264.7,759.9,876.7)    w=703 h=612 fpi=4.00
           -> area=517.9 SF  n_regions=8  top=[175.5, 151.6, 100.3, 30.9, 25.4, 15.0, 10.8, 8.3]
     [2] KING SUITE C  RCP  clip=(680.4,1212.7,1394.8,1824.7) w=714 h=612 fpi=4.00
           -> area=458.3 SF  n_regions=5  top=[291.9, 63.5, 62.6, 29.9, 10.4]

page 32  sheet='ID-416'
     [2] BUNK A        RCP  clip=(650.9,1212.7,1316.2,1824.7) w=665 h=612 fpi=4.00
           -> area=454.7 SF  n_regions=6  top=[287.2, 63.1, 51.1, 30.4, 12.3, 10.6]

page 31  sheet='ID-415'
     [3] QQ C          RCP  clip=(963.8,1212.7,1611.7,1824.7) w=648 h=612 fpi=4.00
           -> area=284.3 SF  n_regions=6  top=[170.9, 40.2, 34.5, 15.3, 13.6, 9.9]
```

The clip geometry is essentially the same on all four sheets (≈ 650–715 × 612 pt). Nothing distinguishes
the two "defective" ones.

### Where the counted area physically sits (region bounding boxes, page points)

```
page 27  KING SUITE B - RCP   clip=(794,843,1507,1455)
    216.8 SF  bbox=(1032, 1028, 1336, 1261)     <- all regions inside x 1010-1336 (326 pt)
     37.7 SF  bbox=(1238, 1270, 1336, 1397)
     33.4 SF  bbox=(1032, 1270, 1176, 1357)
     24.7 SF  bbox=(1010, 1006, 1181, 1282)
     18.8 SF  bbox=(1186, 1271, 1237, 1397)
     10.3 SF  bbox=(1059, 1358, 1146, 1397)
    TOTAL 341.7 SF over 6 regions

page 28  KING SUITE C - RCP   clip=(680,1213,1395,1825)
    291.9 SF  bbox=( 928, 1464, 1232, 1782)     <- all regions inside x 906-1245 (339 pt)
     63.5 SF  bbox=( 928, 1301, 1096, 1454)        and y 1301-1803 (502 pt)
     62.6 SF  bbox=(1105, 1301, 1232, 1462)
     29.9 SF  bbox=( 906, 1447, 1076, 1803)
     10.4 SF  bbox=(1235, 1448, 1245, 1782)
    TOTAL 458.3 SF over 5 regions

page 32  BUNK A - RCP         clip=(651,1213,1316,1825)
    287.2 SF  bbox=( 902, 1463, 1205, 1782)     <- all regions inside x 880-1219 (339 pt)
     63.1 / 51.1 / 30.4 / 12.3 / 10.6 SF        and y 1301-1803
    TOTAL 454.7 SF over 6 regions
```

**Reading:** on ID-412 the counted ink occupies a 339 × 502 pt column — 47 % of the 714 × 612 pt clip. A
clip that had reached into a horizontally adjacent plan would show two separated x-clusters. It shows one.
Rendering the clip confirms it visually: a single guestroom (bedroom + bathroom + entry), no second plan.

---

## 3. Probe B — clip-width sensitivity across all 16 prototype sheets

Same code, `_FILL_CLIP_SIDE_PT` varied. RCP fill (the one that feeds `ceiling_area`):

```
page  plan            RCP@220  RCP@260  RCP@300  RCP@340   AR@260
 23   KING A            218.6    229.4    229.4    268.2    193.2
 24   KING B            235.8    235.5    249.7    281.9    211.6
 25   KING C            217.6    217.6    217.6    217.6    225.0
 26   KING SUITE A      362.6    362.5    373.9    373.9     85.4
 27   KING SUITE B      341.7    341.7    341.7    341.7    369.9
 28   KING SUITE C      458.3    458.3    458.3    458.3    517.9   <- "defective"
 29   QQ A              272.6    272.6    302.8    302.8    275.8
 30   QQ B              309.5    309.5    309.5    309.5    360.6
 31   QQ C              274.4    284.3    299.8    341.8    260.4
 32   BUNK A            454.2    454.7    485.6    485.1    515.5   <- "defective"
 33   BUNK B            274.6    274.6    274.6    290.0    337.0
 34   ADA KING RIS      347.2    347.2    355.2    355.2    382.4
 35   ACC KING TUB      347.7    347.7    356.3    365.0    384.4
 36   ACC QQ RIS        451.1    451.0    451.0    451.0     42.5
 37   ACC QQ TUB        463.0    463.0    463.0    463.0    336.8
 38   ACC BUNK          458.5    458.5    458.5    458.0     62.9
```

**ID-412 is bit-identical across a 240-pt range of clip widths.** ID-416 moves 0.5 SF between 220 and 260.
Meanwhile ID-415 moves +57.5 SF (+20 %) and ID-407 +38.8 SF (+17 %). If the 2× came from the clip, the two
defective sheets would be the *most* sensitive; they are the *least*. **The clip hypothesis is falsified.**

### Adjacent-clip overlap (pure geometry, no rasterizing)

```
page sheet   n_clips  worst_pair_overlap  whole neighbour inside a clip?
 23  ID-407     5          45%            -
 24  ID-408     6          48%            -
 25  ID-409     5          35%            -
 26  ID-410     5          35%            -
 27  ID-411     5           8%            -
 28  ID-412     5          35%            -      <- "defective", NOT the worst
 29  ID-413     6          45%            -
 30  ID-414     5          21%            -
 31  ID-415     6          42%            -
 32  ID-416     5          24%            -      <- "defective", 4th LOWEST
 33  ID-417     5          29%            -
 34  ID-418     5          33%            -
 35  ID-419     5          33%            -
 36  ID-420     5          27%            -
 37  ID-421     5          28%            -
 38  ID-422     5          36%            -
```

Two facts at once: (a) the defective sheets are not the ones with the worst overlap — again falsifying the
clip story; (b) **every** sheet's clips overlap their neighbours by 8–48 %, and no sheet currently contains
a whole neighbour. Today's correctness is therefore an accident of `touches_edge`, which is why the clip
should still be fixed (`§6` steps 1–3) — just not as the fix for GAP 2.

---

## 4. Probe C — the drawing's own printed dimensions, and the real root cause

Largest horizontal × largest vertical printed dimension found inside each sheet's **AR** viewport
(`dimensions.parse_feet_inches`, `line["dir"]` for orientation) — this is the drawing's own statement of
its extent, independent of golden:

```
page sheet   plan            maxH_ft  maxV_ft  bound_SF   RCP fill   fill/bound
 23  ID-407  KING A            10.86    20.59     223.7      229.4      1.03
 24  ID-408  KING B            10.29    21.34     219.7      235.5      1.07
 25  ID-409  KING C            10.29    20.84     214.5      217.6      1.01
 26  ID-410  KING SUITE A      11.93    12.26     146.2      362.5      2.48   (partial dims only)
 27  ID-411  KING SUITE B      17.00    20.59     350.1      341.7      0.98
 28  ID-412  KING SUITE C      17.01    26.76     455.2      458.3      1.007
 29  ID-413  QQ A              10.29    24.68     254.0      272.6      1.07
 30  ID-414  QQ B              12.62    24.68     311.5      309.5      0.99
 31  ID-415  QQ C               —        —          —        284.3      (no dims in AR viewport)
 32  ID-416  BUNK A            17.01    26.76     455.2      454.7      0.999
 33  ID-417  BUNK B            10.29    26.76     275.4      274.6      0.997
 34  ID-418  ADA KING RIS      17.01    20.59     350.3      347.2      0.99
 35  ID-419  ACC KING TUB      17.01    20.59     350.3      347.7      0.99
 36  ID-420  ACC QQ RIS         —        —          —        451.1      (no dims in AR viewport)
 37  ID-421  ACC QQ TUB        17.01    26.76     455.2      463.0      1.017
 38  ID-422  ACC BUNK          17.01    26.76     455.2      458.6      1.007
```

**13 of 16 sheets land in `fill/bound` 0.98–1.07.** ID-412 and ID-416 are among the *tightest* fits in the
whole set. The drawn `KING SUITE C` really is a 17'-0 1/8" × 26'-9 1/8" unit; the flood fill measured it
correctly. (ID-410's 2.48 is a *bound* failure — only partial interior dims were paired inside that
viewport — not a fill failure; see `§7` risks.)

### The multiplier is the defect

`human_inputs/moxy_knoxville.json` room mix:

```
KING A 26 | KING B 15 | KING C 5 | KING SUITE A 5 | KING SUITE B 2 | KING SUITE C 2
QQ A 90 | QQ B 6 | QQ C 15 | BUNK A 2 | BUNK B 1 | ADA KING RIS 1
ACC KING TUB 3 | ACC QQ RIS 2 | ACC BUNK 2
```

`_fuse_room_fills` (`src/bobbytailor/vision/fusion.py:1562-1564`) does:

```python
count = room_mix.get(plan_key)
known_count = count is not None and int(count) > 0
qty = total_for_units(pick.area_sf, count if known_count else None)
```

so ID-412 emits `458.3 × 2 = 916.6 SF` against an estimator sheet total of `461.49 SF` — the observed
"~2×". Scoring the whole family (golden read **after** the measurement, purely to size the prize):

| sheet | plan | fill (SF) | mix count | emitted | estimator sheet total | with count = 1 |
|---|---|---|---|---|---|---|
| ID-412 | KING SUITE C | 458.3 | 2 | 916.6 | 461.49 | **0.7 %** |
| ID-416 | BUNK A | 454.7 | 2 | 909.4 | 461.00 | **1.4 %** |
| ID-420 | ACC QQ RIS | 451.1 | 2 | 902.2 | 470.21 | **4.1 %** |
| ID-422 | ACC BUNK | 458.6 | 2 | 917.2 | 456.73 | **0.4 %** |
| | **family** | | | **3 645.4** | **1 849.4** | **1 822.7 → 1.4 %** |

For contrast, ID-411 `KING SUITE B` genuinely *is* ×2: fill 341.7, printed dims 350.1, estimator sheet
total 706.76 = 2 × 353.4. So the mix is right on 12 sheets and wrong on 4 — because whoever built the
manifest read `Doors-WD` as the unit count (§13.2's model). On ID-412 that is wrong: key note 3 on the
sheet itself is *"WHEN CONNECTING DOOR IS USED…"* — the second wood door is a connecting door inside one
suite. Corroborated by two more golden columns that are unmistakably single-unit on these sheets:
`Guestroom-Wall Covering` 239.76 (ID-412) / 240.44 (ID-416) vs the known **1-unit** ID-417's 241.14; and
`Gyp Wall` 632.00 / 650.83 vs ID-411's 1 566.65 for two units.

**This is an INPUT error the code silently amplifies and reports at `confidence: "high"`
(`fusion.py:1581`).** The fix is not to hardcode "these four are 1" — that is exactly the §10 coincidence
trap. The fix is to make the code *unable* to present an unverifiable multiplier as a confident quantity,
and to add the geometric self-check that already discriminates perfectly (Probe C).

---

## 5. The 900 SF threshold — why it must go regardless

* `flag_implausible_unit` is applied to the **per-unit** fill at `takeoff_pipeline.py:1837`, *before*
  `total_for_units` runs in fusion. 458.3 < 900 → passes; the flag never sees the 916.6 that is actually
  wrong. The guard is on the wrong side of the multiplication.
* `MAX_REGION_SF = 900.0` (`room_fill.py:73`) **discards any single region above 900 SF** at
  `room_fill.py:235`. A lobby, ballroom or retail floor plate is one region far above 900 SF, so the
  engine returns `None` on exactly the sheets Bob's and Moxy Level 1/7 need. `tests/test_room_fill.py`
  (`test_max_region_guard_rejects_sheet_scale_regions`) currently *asserts* this behaviour with a 2 400 SF
  room.
* Both numbers are guestroom-shaped constants. Probe C's `fill / (maxH × maxV)` ratio is the scale-free,
  building-type-free replacement: it is ~1.0 for a guestroom, ~1.0 for a lobby, and ~2.0 for a genuine
  two-plan clip leak.

Independent evidence that the fixed clip breaks on non-guestroom sheets: `ID-109 LEVEL 7 - RCP PLAN`
(page 14) has its title near the page top, so `max(0.0, ty0 - 620)` collapses the clip to
`Rect(1691.2, 0.0, 2232.3, 32.9)` — a 33 pt strip. One region, 98.9 SF, `touches_edge=True` → discarded →
`measure_enclosed_area` returns `None`. Enlarging the constants to `side=700, up=1400` does not help.
The room-fill engine currently produces **nothing** for Moxy's Lobby / Pop-Up Hub / Level 7 / corridor
sheets.

---

## 6. Implementation map

Ordered. Steps 1–3 are the geometric clip fix (robustness, and the prerequisite for lobbies); steps 4–7
are the actual GAP 2 fix; step 8 is the doc/test correction.

### Step 1 — `TakeoffPipeline._measure_room_fills` (`takeoff_pipeline.py:1773-1849`): replace the fixed box with a midpoint partition

Delete `_FILL_CLIP_UP_PT` / `_FILL_CLIP_SIDE_PT` (`:1770-1771`). Extract a new module-level helper in
`room_fill.py`:

```python
def clip_cells(titles, page_rect, mask_rects=()):
    """One clip per '<NAME> - <KIND> PLAN' title, partitioned by its NEIGHBOURS."""
```

Rules (all geometric, no size constants):

* **Bottom** = `title.y0 - 8` (unchanged: a drawing sits above its title).
* **Left / right** = the midpoint in x between this title's centre and the centre of the nearest title
  *in the same title row* (titles whose `y0` is within one title height), else the page edge / nearest
  masked `title_block`/`legend`/`schedule` rect from `viewports.segment_viewports`.
* **Top** = the bottom (`y1`) of the nearest title *above* this one whose x-span overlaps, else the page
  top / masked rect. On a sheet with one drawing this yields the whole sheet minus the title block — which
  is what a lobby needs.

This alone converts ID-412's clip from `(680,1213,1395,1825)` to roughly `(810,905,1305,1825)` (midpoints
to the FF title at x≈430 and the FC title at x≈1563; top bounded by the AR title row at y≈906), i.e. it
*narrows* to the actual drawing — measurement unchanged (Probe B shows ID-412 is flat from 220 to 340 pt).

### Step 2 — `room_fill.measure_enclosed_area` (`:194-247`): tighten the clip to the drawing's own ink

Inside the cell from step 1, compute the **ink bounding box** from `page.get_drawings()` segments whose
midpoint falls in the cell (reuse `viewports._segments_from_paths`, `viewports._trimmed_bbox`), drop the
outermost 1 % as leader-line outliers, and intersect the cell with `ink_bbox + 6 pt`. Accept a new
optional parameter `clip_source: str` recorded on `RoomFillResult` (`"midpoint_cell"` /
`"ink_extent"`) so a run can be audited. This is the "stop the flood at the drawing's own border
linework" requirement; `touches_edge` then means *"reaches the drawing's own extent"*, which is a real
signal rather than an artefact of a 260 pt constant.

### Step 3 — `room_fill`: delete `MAX_REGION_SF` (`:73`) as a hard filter

Change `:233-236` so an over-large region is **kept and flagged**, never dropped:

```python
enclosed = [r for r in regions if not r.touches_edge and r.area_sf >= min_region_sf]
```

Move the "too big to be a room" decision entirely to step 4's dimension cross-check. Keep
`MIN_REGION_SF` (fixture/annotation cells are genuinely tiny and scale-invariant in *drawing* terms).

### Step 4 — new `room_fill.printed_extent_bound(page, clip, feet_per_point)` and `cross_check_extent(result, bound_sf)` — replaces `flag_implausible_unit` (`:250-265`)

```python
def printed_extent_bound(page, clip, plan_name=None):
    """(max horizontal dim ft) x (max vertical dim ft) printed for this drawing."""
```

* Harvest dimension texts with `dimensions.extract_dimension_samples(page, exclude_rects=mask)` (already
  used by `scale_solver`), keep samples whose `text_bbox` centre lies in the clip **or in any other
  viewport carrying the same `plan_name`** (Moxy prints the overall dims on the AR plan, not the RCP —
  Probe C relied on exactly this), split by `rotation` into horizontal/vertical, take the max of each.
* `cross_check_extent` sets `needs_review=True` when `area_sf > TOL * bound_sf`. Choose `TOL` from the
  *distribution in Probe C* (13 sheets ≤ 1.07, a leak would be ≈ 2.0) — e.g. `TOL = 1.25`, which is
  4 σ-ish clear of both populations and is **not** a size in SF, so it does not overfit to guestrooms.
* When no dimension pair is found (ID-415, ID-420), return `None` and set
  `review_reason="no printed overall dimension to cross-check the measured extent"` — flag, never guess.
* Record `bound_sf` and `extent_ratio` on `RoomFillResult` so the Excel export can show them.

Delete `_MAX_UNIT_SF` (`takeoff_pipeline.py:1764`) and its call at `:1837`; call
`cross_check_extent` there instead.

### Step 5 — `room_fill.select_fill_for_basis` (`:131-145`): stop using `min(area)` as the "single unit" rule

`:143-145` currently picks the smallest same-discipline fill because *"if a sheet repeats it (opposite
hand), the smaller is the single unit — the larger spans both"*. That rationale is the same misdiagnosis.
Replace with: prefer the fill whose `extent_ratio` is closest to 1.0; break ties by `candidate_id`. If two
same-discipline fills both validate, return `None` and flag `"two <KIND> drawings of <NAME> on one sheet —
which one is the unit is ambiguous"`. Never silently take the smaller.

### Step 6 — `vision/fusion._fuse_room_fills` (`:1516-1596`): the multiplier must be visible and cross-checked

* Emit `unit_count_source: "manifest"` alongside `unit_count` (`:1592`) and downgrade
  `confidence` (`:1581`) from `"high"` to `"medium"` whenever `known_count and count > 1`. A number the drawing set
  does not contain (§13.3) must not be reported as high-confidence.
* When `pick.extent_ratio` is available and `count > 1`, append a review reason:
  `"measured ONE <NAME> unit of <area> SF (printed extent <bound> SF, ratio <r>); multiplied by <count>
  from the manifest room mix — verify the count is UNITS, not doors"`. On ID-412 this is precisely the
  sentence that would have caught the error.
* Add the reciprocal check: if a sheet's fill validates as one unit (`ratio ≈ 1`) **and** the manifest
  count for that plan came from a door count, that is exactly the ambiguity to surface — see step 7.

### Step 7 — `_manifest_room_mix` (`takeoff_pipeline.py:624-651`): carry provenance for the count

Accept and propagate an optional `assumptions.unit_count_source` (`"estimator"`, `"door_schedule"`,
`"assumed"`). Default to `"assumed"` when absent. `_fuse_room_fills` then flags every row whose count is
not `"estimator"`. Update `human_inputs/moxy_knoxville.json` to record where each count came from — do
**not** edit the four counts to 1 in the same change; let the flag fire first, so the fix is validated by
the flag firing on exactly ID-412/416/420/422 and on nothing else.

### Step 8 — correct the record

* `docs/PIPELINE-GROUND-TRUTH.md` §14.2: replace the "the clip reaches the adjacent opposite-hand plan"
  claim with the evidence above. Keep the (correct) instruction not to move a threshold to make it pass.
* `src/bobbytailor/deterministic/room_fill.py:250-256` docstring — same correction.
* `tests/test_room_fill.py:114-122` — `test_oversize_unit_is_flagged_never_silently_halved` uses the real
  ID-412 numbers with a fabricated 420 SF cap and a docstring asserting the clip story. Rewrite as a
  cross-check test: `area_sf=458.3, bound_sf=455.2 → not flagged`; `area_sf=916.6, bound_sf=455.2 →
  flagged`.
* `tests/test_room_fill.py` `test_max_region_guard_rejects_sheet_scale_regions` — invert: a 2 400 SF room
  must now be **measured and returned**, not `None` (step 3).

### Step 9 (small, separate) — `scripts/room_probe.py:82` is broken

```python
main_id = select_main_plan([(v, None) for v in vps])
```

`select_main_plan` (`scale_solver.py:261-278`) dereferences `vs.fpp`, so this raises
`AttributeError: 'NoneType' object has no attribute 'fpp'` on every Moxy page:

```
$ python3 scripts/room_probe.py "uploads/Moxy ...-Plans.pdf" --fpi 4.0 --pages 27,28,31,32
  page 27 [floor_plan]: ERROR AttributeError: 'NoneType' object has no attribute 'fpp'
  page 28 [floor_plan]: ERROR AttributeError: 'NoneType' object has no attribute 'fpp'
  page 31 [floor_plan]: ERROR AttributeError: 'NoneType' object has no attribute 'fpp'
  page 32 [floor_plan]: ERROR AttributeError: 'NoneType' object has no attribute 'fpp'
== TOTAL rooms=0
```

Pass real `ViewportScale`s (or `main_bbox=None`) and add a `--engine {vector,fill}` switch so the probe
exercises `room_fill` — today no committed script exercises the engine that produces Moxy's numbers,
which is why §14.2's diagnosis went unchallenged.

---

## 7. Offline verification (free, zero API)

1. **The clip fix must not move the 9 correct sheets.** Regenerate the Probe B table after steps 1–2 and
   assert, per sheet, `|new - old| / old <= 0.02` for pages 23, 24, 25, 26, 27, 29, 30, 31, 33 (ID-407,
   408, 409, 410, 411, 413, 414, 415, 417):
   ```
   python3 - <<'PY'  # ~90 s, pure PyMuPDF + stdlib
   # for pg in 23..38: fills = TakeoffPipeline()._measure_room_fills(page, vps, scales, sid)
   # print RCP area per sheet; diff against the baseline table in §3
   PY
   ```
   Baseline to diff against (RCP @ current code): `229.4, 235.5, 217.6, 362.5, 341.7, 458.3, 272.6,
   309.5, 284.3, 454.7, 274.6, 347.2, 347.7, 451.0, 463.0, 458.5`.
2. **Clip-invariance regression.** Re-run the ±80 pt sweep after the fix. Post-fix, *every* sheet should be
   invariant (the clip is now derived from the drawing, not a constant), i.e. the ID-407/413/415 columns
   collapse to a single value. This is the positive proof the clip is now geometric.
3. **Cross-check discriminates without a size threshold.** Assert `extent_ratio` ∈ [0.9, 1.15] for the 13
   sheets that have printed dims, and that injecting a synthetic double-width clip (concatenate two copies
   of the ID-412 RCP raster) yields `extent_ratio ≈ 2.0` and `needs_review=True`.
4. **Lobby generality.** `measure_enclosed_area` on `ID-109 LEVEL 7 - RCP PLAN` (page 14) must return a
   result instead of `None` after steps 1–3. Assert `result is not None` and
   `result.regions[0] > 900` (the region the current `MAX_REGION_SF` deletes).
5. **The multiplier flag fires on exactly four sheets.** After steps 6–7, run fusion on the saved bundle
   and assert `needs_review` is set on the `Gyp Ceiling` rows sourced from ID-412/416/420/422 and clear on
   ID-407/408/409/410/411/413/414/415/417.
6. **Suite**: `python3 -m pytest tests/test_room_fill.py tests/test_pipeline_deterministic.py -q`
   (offline; the golden marker is excluded by default since commit `10cd7be`).
7. **End-to-end score, free**: `python3 scripts/score_report_dir.py --golden
   tests/fixtures/moxy/moxy_golden.csv --dir output/VisionOnly_Moxy_Knoxville_20260717_045741` — re-score
   a *saved* run after re-running fusion offline against its saved bundle. Never re-run the live pipeline
   to check this.

---

## 8. Risks

1. **The four manifest counts are a human input, and I have only proved they contradict the drawing.**
   Steps 6–7 flag rather than correct, deliberately. If someone "fixes" the four counts to 1 without the
   flag, the next project with a genuine 2-unit suite sheet regresses silently — the §10 coincidence trap
   in a new costume.
2. **The printed-extent bound fails where dimensions are absent or partial** — ID-415 and ID-420 have no
   dimension pair inside the AR viewport, and ID-410 produced a bound 2.5× too small from partial interior
   dims. The cross-check must therefore be a *flag*, never a filter: no bound → `needs_review`, not a
   dropped measurement. A bound-derived rejection of a good fill would be worse than the current bug.
3. **Widening the clip to a midpoint cell can newly admit a whole neighbour** on a sheet whose drawings
   are unevenly spaced (the midpoint may land inside the smaller drawing's neighbour). Step 2's ink-extent
   tightening is what contains this; verification item 2 is the guard.
4. **Removing `MAX_REGION_SF` admits sheet-scale background regions** on sheets where the border linework
   is broken and the "outside" does not reach the clip edge. Mitigation: keep `touches_edge`, and treat a
   region larger than the printed-extent bound as `needs_review` rather than as a room.
5. **`select_fill_for_basis` currently returns the smaller of two same-discipline fills**; step 5 turns
   that into an explicit ambiguity flag, which will surface new `needs_review` rows on sheets that were
   quietly resolved before. That is an accuracy *improvement* but a visible increase in review load.
6. **`docs/PIPELINE-GROUND-TRUTH.md` §14's blind table excluded ID-412/416/420/422**, so the published
   7.0 % Gyp Ceiling figure never included them. Correcting the multiplier adds ~1 823 SF of correctly
   measured area; do not report that as an improvement to the 7.0 % number without recomputing the whole
   table on the same basis.

---

## 9. Files touched by the proposed change

```
src/bobbytailor/pipeline/takeoff_pipeline.py   :624-651, :1764, :1770-1771, :1773-1849
src/bobbytailor/deterministic/room_fill.py     :72-73, :131-145, :194-247, :250-265
src/bobbytailor/vision/fusion.py               :1516-1596
scripts/room_probe.py                          :82  (+ --engine switch)
tests/test_room_fill.py                        :114-131, :146-152
docs/PIPELINE-GROUND-TRUTH.md                  §14.2
human_inputs/moxy_knoxville.json               unit_count_source provenance only
```

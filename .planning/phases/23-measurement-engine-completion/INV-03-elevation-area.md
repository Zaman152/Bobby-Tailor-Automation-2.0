# INV-03 — Elevation wall-area SF is never measured (Bob's blocker)

**Status:** investigation complete, read-only. Every number below came from a ZERO-API offline probe
run against the real PDFs in `uploads/`. No paid path was touched.

---

## TL;DR

1. **Elevations are structurally unreachable.** `takeoff_pipeline.py:236`
   `_DETERMINISTIC_SHEET_TYPES = ("floor_plan","civil_site","roof_plan","schedule")` — `"elevation"`
   is absent, so `run_sheet` (`takeoff_pipeline.py:1239`) never calls `_route_deterministic` for an
   elevation sheet. Classification is *not* the bug: Bob's page 4 and Crow page 1 both classify
   `elevation` correctly from the title block.
2. **Even if it were reached, it would measure nothing.** The only area engine,
   `_measure_room_fills` (`takeoff_pipeline.py:1773`), is anchored on
   `room_fill.plan_titles()` → `PLAN_TITLE_RE` (`room_fill.py:49`) which requires
   `"<NAME> - AR|RCP|FF|EM|FC PLAN"`. An elevation is titled `FRONT ELEVATION NEW`. Probe: forcing
   Bob's page 4 through `_deterministic_bundle` yields `room_fills: 0` **even when the sheet type is
   forced to `floor_plan`**. This is §12b verbatim: "no per-room measurement step, so it computed 0".
3. **The recipe that works is NOT the room flood fill.** An elevation facade is a *filled silhouette*
   subdivided by joint/reveal lines, not a void enclosed by walls. The naive room fill fragments the
   Bob's front elevation into 63 voids summing 4,561 SF. **Complement labeling** — flood the
   clip *border* to get the background, take the largest connected component of the complement — returns
   one clean blob per elevation on all three fixtures.
4. **Position/shape validation, never count-tuning (§10 trap avoided).** On Crow the four facade blobs
   measure 1,150/1,160 ft wide against the page-0 footprint's independently measured
   `width_ft=1136`, and their summed area is **135,528 SF vs perimeter 2,972 LF × the elevation's own
   printed datum T/PANEL 45'-2" = 134,246 SF → 1.0% agreement** between two fully independent
   measurements. On Bob's the blob is 249–250 ft wide against the page-1 footprint's independently
   measured `depth_ft=250.0`.
5. **A blocking scale bug sits underneath all of it (new, undiagnosed).** `_paper_inches`
   (`printed_scale.py:141`) takes the *first* digit run left of `=`, so a **leading drawing number is
   parsed as the paper-inch value**. Real Bob's block `'2 SCALE: 18" = 1\'-0" FRONT ELEVATION NEW'`
   → **0.5 ft/in instead of 8.0** (16× linear, 256× area). Same class of bug: `'SCALE: 3 32" = 1\'-0"'`
   (space-separated stacked fraction) → **0.333 instead of 10.667** on Bob's floor plan. A prototype
   fix corrects **7 scales, all on Bob's, and changes 0 of 383 on Crow / Moxy / Chelsea**.
6. **Two latent rotation bugs break the existing shipped room-fill too.** Bob's pages are
   `rotation=270`, 11 Moxy pages are `rotation=90`. `measure_enclosed_area` passes an *unrotated*
   clip to `page.get_pixmap` (`room_fill.py:221`), and `_measure_room_fills` pairs title↔scale by
   unrotated "below" (`takeoff_pipeline.py:1815-1819`). **Moxy pages 9 and 13 return zero room_fills
   today**; the page-space prototype returns 355.4 SF for `LEVEL 1 LOBBY - AR PLAN`.
7. **Material split (CMU vs EIFS) comes from keynote tags, not hatch.** Every fill path inside Bob's
   front elevation is white (`fill=(1,1,1)` ×932, `(0,0,0)` ×2) — there is no hatch signal. But the
   drawing carries positioned keynote tags `01…15` and the sheet carries a `KEYED NOTES` legend
   (`14 → PREPARE EXISTING CMU FOR NEW PAINT COLOR`, `03 → NEW EIFS SCRATCH COAT AT SIGN BAND`).
   That is the realistically available material signal.
8. **21-13's concern is fully preserved by construction.** Keep `_PLAN_SHEET_TYPES` unchanged.
   `extract_walls`/`extract_rooms`/`cluster_symbols`/`footprint_from_page` are gated on
   `_PLAN_SHEET_TYPES` at `takeoff_pipeline.py:1707` and `:1716`, so adding `"elevation"` to
   `_DETERMINISTIC_SHEET_TYPES` alone produces **zero** wall pairing on elevations. Probe proof: forcing
   Bob's page 4 to `floor_plan` emits **22 bogus walls / 4 bogus thickness classes**; leaving it
   `elevation` emits `walls: 0, wall_lf_by_class: 0` — exactly what 21-13 wanted.

---

## 1. How elevation sheets are classified and routed today

### 1.1 Classification is correct — this is not a classifier bug

`classify_sheet_type_from_text` (`sheet_pass_matrix.py:191`) checks `_KW_ELEV = {"ELEVATION",
"ELEVATIONS"}` at line 241, after `_KW_SCHEDULE` (line 222) and after `_PLAN_VIEWPORT_RE` (line 237).
Run against the real title blocks (`pdf_analyzer.get_title_block_text`, `pdf_analyzer.py:165`):

```
### uploads/Crow - Cass White Road-Plans.pdf
 page 0 type_from_tb= floor_plan | tb= MATCHLINE B 48' - 4" OFFICE POD 54' - 0" ...
 page 1 type_from_tb= elevation  | tb= FINISH FLOOR 0' - 0" T/ PANEL 45' - 2" TRUCK COURT -4' - 0" ...
 page 2 type_from_tb= detail
 page 3 type_from_tb= detail
### uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf
 page 0 type_from_tb= title_sheet
 page 1 type_from_tb= floor_plan
 page 2 type_from_tb= schedule
 page 3 type_from_tb= floor_plan
 page 4 type_from_tb= elevation  | tb= 3. ALL DENS-GLASS GOLD GYPSUM SHEETING ... SPLIT FACE CMU WALLS ...
 page 5 type_from_tb= schedule
 page 6 type_from_tb= floor_plan
```

Both elevation sheets are found. (Note: with `title_block_text=""` and only full-page text, Crow p1
mis-classifies as `schedule` because the word "SCHEDULE" appears in a note — a real ordering weakness
at `sheet_pass_matrix.py:222` vs `:241`, but not the blocker here since production always passes the
title block, `pdf_analyzer.py:319`.)

### 1.2 The routing gate is the blocker

```python
# src/bobbytailor/pipeline/takeoff_pipeline.py:232-236
_PLAN_SHEET_TYPES = ("floor_plan", "civil_site", "roof_plan")
...
_DETERMINISTIC_SHEET_TYPES = _PLAN_SHEET_TYPES + ("schedule",)
```
```python
# src/bobbytailor/pipeline/takeoff_pipeline.py:1235-1247
if (
    self._settings.deterministic_enabled
    and pdf_path is not None
    and page_index is not None
    and resolved_type in _DETERMINISTIC_SHEET_TYPES
):
    routed = self._route_deterministic(...)
```

`PASS_MATRIX["elevation"] = ["count", "measure"]` (`sheet_pass_matrix.py:47`) with
`("elevation","measure") → CLAUDE_MODEL_SCHEDULES` (`sheet_pass_matrix.py:76`) — i.e. elevations run
**vision-estimated numbers only**. Those are exactly the model-supplied quantities the architecture
forbids, and they are why Bob's scores 8%.

Probe (zero API):

```
_DETERMINISTIC_SHEET_TYPES = ('floor_plan', 'civil_site', 'roof_plan', 'schedule')
'elevation' routed deterministically? False
bundle keys -> {'symbol_groups': 0, 'walls': 0, 'wall_lf_by_class': 0, 'rooms': 0,
                'room_fills': 0, 'viewports': 8, 'schedules': 1, 'footprint': None, 'fpp': 0.1111}
forced floor_plan -> {'walls': 22, 'wall_lf_by_class': 4, 'rooms': 4, 'room_fills': 0,
                      'footprint': None, 'fpp': 0.1111}
```

Two conclusions in one run: (a) `room_fills: 0` regardless of sheet type — the area engine cannot see
an elevation; (b) forcing `floor_plan` is exactly the 21-13 failure mode (22 fabricated walls). **The
fix must open routing without opening `_PLAN_SHEET_TYPES`.**

### 1.3 Elevations are not confined to `elevation` sheets

Chelsea (32 pages) — `extract_printed_scales` titles, per sheet type:

```
 p9  elevation   scales=4  [(8.0,'FRONT ELEVATION TYPE A BLDG 8'), (8.0,'BACK ELEVATION TYPE A BLDG 8'), (8.0,'SIDE ELEVATION TYPE A BLDG 8'), (8.0,'SIDE ELEVATION TYPE A BLDG 8')]
 p10 elevation   scales=4  [... TYPE B BLDG 2 ...]
 p11 elevation   scales=4  [... TYPE C BLDG 3 ...]
 p12 elevation   scales=4  [... TYPE C BLDG 9 ...]
 p13 floor_plan  scales=2  [(4.0,'SIDE ELEVATION CLUBHOUSE'), (4.0,'FRONT ELEVATION CLUBHOUSE')]
 p14 floor_plan  scales=2  [(4.0,'LEASING ELEVATION FRONT'), (4.0,'LEASING ELEVATION SIDE')]
 p15 floor_plan  scales=2  [(4.0,'FITNESS ELEVATION FRONT'), (4.0,'FITNESS ELEVATION SIDE')]
 p16 floor_plan  scales=3  [(4.0,'8-BAY SINGLE GARAGE ELEVATION ...') ×3]
 p18 elevation   scales=4  [(4.0,'16-BAY GARAGE ELEVATION FRONT') ...]
```

21 elevation drawings; **9 of them live on sheets typed `floor_plan`.** So the measurement must be
**viewport-level**, keyed on the scale callout's own title — the identical argument already written
into `takeoff_pipeline.py:1729-1737` ("A sheet is not one thing — it is a COLLECTION of drawings").

---

## 2. What geometry an elevation sheet actually contains

### 2.1 Bob's page 4 (`A4.0 ELEVATIONS`), `rotation=270`, 15,473 drawing paths, 1,323 words

`scale_probe.py` output for the whole file:

```
### Bob's Discount Furniture - Kennesaw, GA-plans.pdf — 7 pages
page 4: viewports=7 printed_scales=6 distinct_fpi=[0.2, 0.3333, 0.5, 2.0, 8.0] main=None  <-- MULTI-SCALE PAGE
    R1   kind=title_block  own_printed_fpi=None
    R2   kind=unknown      own_printed_fpi=None
    R3   kind=unknown      own_printed_fpi=None
    R4   kind=unknown      own_printed_fpi=None
    R5   kind=unknown      own_printed_fpi=None
    R6   kind=unknown      own_printed_fpi=None
    R7   kind=unknown      own_printed_fpi=8.0
== multi-scale pages: 4/7
```

Viewports and printed scales (unrotated coordinates; `page.rect` is `3024×2160`, `mediabox` is
`2160×3024`, `rotation=270`):

```
  printed scales:
    fpi=8.0      bbox=[1646, 2228, 1662, 2329]   text='SCALE: 18" = 1\'-0"'
    fpi=0.5      bbox=[1104,  119, 1129, 2329]   text='2 SCALE: 18" = 1\'-0" FRONT ELEVATION NEW'
    fpi=0.3333   bbox=[ 621,  119,  647, 2329]   text='3 REAR ELEVATION NEW SCALE: 18" = 1\'-0"'
    fpi=0.2      bbox=[  39,  120,   65, 1367]   text='5 ENLARGED GLAZING AND ENTRY DOORS SCALE: 14" = 1\'-0" 4 TRUCK DOCK ELEVATION NEW'
    fpi=8.0      bbox=[  79,  458,   99, 1762]
    fpi=2.0      bbox=[  81, 2240,   96, 2341]   text='SCALE: 12" = 1\'-0"'
  viewports:
    R1   kind=title_block  bbox=[   0, 2356, 2160, 3024]
    R2   kind=unknown      bbox=[1152,  102, 1616, 2353]   <- FRONT ELEVATION NEW
    R3   kind=unknown      bbox=[1687,  102, 2108, 2353]   <- FRONT ELEVATION DEMOLITION
    R5   kind=unknown      bbox=[ 122,  163,  546, 2248]   <- TRUCK DOCK ELEVATION NEW
    R6   kind=unknown      bbox=[ 700,   99, 1053, 2353]   <- REAR ELEVATION NEW
    R7   kind=unknown      bbox=[  85,  582,  511, 1378]   own_fpi=8.0
```

So the sheet **does** contain per-drawing viewports and per-drawing printed scales with usable titles.
The linework: 15,473 drawing paths, all strokes; the only fills are white.

### 2.2 Crow page 1 (`EXTERIOR ELEVATIONS`), `rotation=0`, 68,376 drawing paths

```
  printed scales:
    fpi=40.0  bbox=[2184,1970,2579,2013]  num='1' title='OVERALL NORTH ELEVATION'
    fpi=20.0  bbox=[2184,1581,2556,1624]  num='2' title='OVERALL EAST ELEVATION'
    fpi=40.0  bbox=[2184,1073,2578,1116]  num='3' title='OVERALL SOUTH ELEVATION'
    fpi=20.0  bbox=[2184, 691,2563, 734]  num='4' title='OVERALL WEST ELEVATION'
  viewports:
    R1   kind=legend       bbox=[ 202,  27, 2666,  921]
    R2   kind=unknown      bbox=[ 380,1374, 2610, 2106]
    R3   kind=unknown      bbox=[ 246, 848, 2691, 1450]
    R4   kind=title_block  bbox=[2718,   0, 3024, 2160]
```

Crow's printed scales are perfect (drawing number *follows* the ratio, so the parse bug never fires),
but **`segment_viewports` merges four elevations into two regions and mis-labels a 2,464×894 pt band
`legend`**. → viewport segmentation is not a reliable anchor for elevations; the **scale callout is**.
This matches the reasoning already in `takeoff_pipeline.py:1766-1771` (`_FILL_CLIP_UP_PT`).

Crow page 1 also carries the datum ladder in its title block:

```
--- datum labels ---  TRUCK COURT / FINISH FLOOR / T/ PANEL / T/ PANEL AT GUTTER / T/ PANEL AT ENTRY
"0'"   n=4  e.g. [(2560, 1873), (1077, 1461), (272, 966)]
"45'"  n=4  e.g. [(2554, 1792), (1077, 1311), (272, 897)]
"37'"  n=1  e.g. [(2554, 1820)]
"-4'"  n=3
```

FINISH FLOOR 0'-0", T/ PANEL 45'-2", T/ PANEL AT GUTTER 37'-9", TRUCK COURT -4'-0". **Every elevation
prints its own real-world vertical ruler.** That is the missing wall-height primitive (today
`_resolve_project_wall_height`, `takeoff_pipeline.py:860`, keyword-scrapes plan text and falls back to
`_WALL_HEIGHT_DEFAULT_FT`).

---

## 3. The measurement recipe (validated offline)

### 3.1 Why the room flood fill is the wrong primitive here

`measure_enclosed_area` (`room_fill.py:194`) keeps regions that do **not** touch the clip edge, i.e.
*voids*. On Bob's front elevation, at the correct 8.0 ft/in:

```
R2 FRONT ELEV NEW    clip_px=3752x774 regions=1628 enclosed=63  sum=4561 SF
    top12= [1094, 734, 212, 207, 138, 137, 125, 124, 123, 112, 102, 102]
R3 FRONT ELEV DEMO   clip_px=3752x703 regions=4083 enclosed=40  sum=2977 SF
R6 REAR ELEV NEW     clip_px=3759x589 regions=578  enclosed=204 sum=4057 SF
R5 TRUCK DOCK        clip_px=3476x707 regions=2302 enclosed=53  sum=2589 SF
```

63 fragments for one facade: control joints, CMU coursing, reveals and mullions cut the facade into
pieces. This is not a measurement.

### 3.2 The right primitive: complement labeling (facade silhouette)

```
mask   = render(clip, dpi) < INK_THRESHOLD
bg     = flood fill of the FREE pixels seeded from the clip BORDER
solid  = NOT bg                       # ink + everything the outline encloses
facade = largest connected component of `solid`
```

Bob's page 4, clips mapped through `page.rotation_matrix`, 80 dpi, fpi = 8.0 (corrected):

```
FRONT ELEV NEW   px=2502x516 comps=2
     area=    6245 SF  bbox_ft=249 x 44  fill=0.57
     area=     142 SF  bbox_ft= 32 x  4  fill=1.00
REAR ELEV NEW    px=2506x393 comps=3
     area=    5100 SF  bbox_ft=250 x 27  fill=0.75
TRUCK DOCK       px=2317x472 comps=23
     area=    1910 SF  bbox_ft= 86 x 27  fill=0.83
FRONT ELEV DEMO  px=2502x469 comps=1
     area=    6134 SF  bbox_ft=250 x 43  fill=0.57
```

Crow page 1, bands between consecutive callouts, 80 dpi, each at **its own** printed scale:

```
OVERALL WEST ELEVATION   fpi=20.0  comps=629  area= 16194 SF  bbox_ft= 414 x 57  fill=0.69
OVERALL SOUTH ELEVATION  fpi=40.0  comps=335  area= 52732 SF  bbox_ft=1160 x 64  fill=0.70
OVERALL EAST ELEVATION   fpi=20.0  comps=288  area= 16150 SF  bbox_ft= 396 x 58  fill=0.71
OVERALL NORTH ELEVATION  fpi=40.0  comps=380  area= 50452 SF  bbox_ft=1150 x 56  fill=0.79
```

Chelsea page 9 (a completely different drafting office, 3-storey apartment blocks), same code, no
tuning:

```
FRONT ELEVATION TYPE A BLDG 8    comps=1   area= 5648 SF  bbox_ft=106 x 62  fill=0.86
BACK ELEVATION TYPE A BLDG 8     comps=2   area= 5569 SF  bbox_ft=105 x 66  fill=0.80
SIDE ELEVATION TYPE A BLDG 8     comps=14  area= 3449 SF  bbox_ft= 89 x 64  fill=0.60
SIDE ELEVATION TYPE A BLDG 8     comps=9   area= 3423 SF  bbox_ft=102 x 63  fill=0.53
```

One dominant component per drawing on all three plan sets.

### 3.3 Validation by POSITION / SHAPE — not by count (§10 discipline)

**Crow.** Page 0 footprint, measured independently by `footprint_from_page`:

```
Footprint(width_ft=1136.0, depth_ft=350.0, area_sf=397600.0, perimeter_lf=2972.0, confidence='high')
```

* Blob **width**: south 1160 ft / north 1150 ft vs footprint `width_ft=1136` → +1.2% / +2.1%.
* Blob **height**: 56–64 ft bbox against the sheet's own printed `T/ PANEL 45'-2"` datum, the excess
  being connected grid bubbles / dimension strings above the parapet — i.e. the known reason to add
  the datum trim in step D below.
* **Area identity**: `perimeter_lf 2,972 × 45.167 ft = 134,246 SF` vs
  `50,452 + 52,732 + 16,150 + 16,194 = 135,528 SF` → **+1.0%**.
  Two measurements that share no code path, no sheet and no scale agree to 1%.

**Bob's.** Page 1 footprint, measured independently:

```
Footprint(width_ft=200.17, depth_ft=250.0, area_sf=50041.7, perimeter_lf=900.3, confidence='high')
```

* Front and rear blob widths are **249 ft and 250 ft** against `depth_ft=250.0`. Exact.
* This is also the definitive refutation of the mis-parsed 0.5 ft/in: at 0.5 the same facade would be
  **15.6 ft wide**.

Neither check ever looks at a golden quantity. Golden (`Bob's ... -Take offds.pdf`, ground truth only)
is `Exterior Painting - CMU Wall 16,218.94 SF` + `Exterior Painting-EIFS - ALT 3,053.04 SF` = 19,272 SF;
the three NEW elevations sum to 13,255 SF gross. **Do not tune to close that gap** — the residual is
structural (only 3 of 4 facades are drawn; the EIFS row is an ALT), and it is exactly the kind of gap
that must be closed by the perimeter×datum-height cross-check in §3.5, not by a fudge factor.

### 3.4 Material attribution: keynote tags, not hatch

Fill/stroke colours of all paths inside Bob's `FRONT ELEVATION NEW`:

```
paths in FRONT ELEV NEW: fills= 934
 fill colors:   [((1.0,1.0,1.0), 932), ((0.0,0.0,0.0), 2)]
 stroke colors: [((0.0,0.0,0.0), 4313), ((1.0,1.0,1.0), 2027), ((0.502,0.502,0.502), 20)]
```

**There is no hatch pattern and no fill colour to classify.** Hatch-based material detection is not
available on this fixture and should not be built.

What *is* available: positioned keynote tags inside the drawing, and a keynote legend on the sheet.

```
words inside FRONT ELEV NEW viewport (x 1152..1616): 83
   '01' ×7   '02' ×2   '03' ×2   '04' ×8   '05' ×6   '06' ×2   '07' ×6   '14' ×12   '15' ×2
legend blocks:
   [1248,2483]-[1273,2662]  KEYED NOTES
   [1562,2442]-[1588,2703]  DEMO KEYED NOTES
   [ 900,2372]-[ 909,2630]  14 PREPARE EXISTING CMU FOR NEW PAINT COLOR
   [1188,2398]-[1197,2598]  NEW EIFS SCRATCH COAT AT SIGN BAND.      (number block '03' at [1187,2371])
   [ 881,2372]-[ 890,2621]  15 INFILL REVEALS ON PILASTERS ON ALL SIDES.
```

And the sheet notes confirm the two golden materials verbatim:
`AT BASE OF ALL EX. MASONRY & SPLIT FACE CMU WALLS…`, `11. EIFS FINISH SHOWN ON ELEVATIONS SHALL BE
SAND TEXTURE AND 'DRYVIT' OR …`.

**Recipe:** keynote number → legend text → material keyword, then attribute by tag position. Tag `14`
(CMU paint prep) occurs 12× spread across the facade; tag `03` (EIFS sign band) occurs 2× clustered.
There are **two keynote legends on the sheet** (`KEYED NOTES` and `DEMO KEYED NOTES`) and the correct
one is chosen by which drawing the tag sits in — a `03` inside `FRONT ELEVATION DEMOLITION` (viewport
x 1687–2108) means a demo note, a `03` inside `FRONT ELEVATION NEW` (x 1152–1616) means EIFS.

**Honesty boundary — this is where flag-don't-guess applies.** The tag tells you *which materials are
present and roughly where*; it does not draw the boundary between them. Emit:
* the **gross facade SF per elevation** at `provenance="geometry"`, `confidence="high"` (fully
  deterministic, position-validated); and
* the **per-material split** only where a tag sits inside a closed sub-region whose boundary the fill
  actually found; the unclaimed remainder goes to the dominant material with
  `needs_review=True` and a reason naming the tags seen. Never split by a ratio, never divide the
  total by the number of distinct materials.

### 3.5 Second, independent elevation quantity: perimeter × datum height

The datum ladder gives a real wall height per elevation. Combined with the floor plan's measured
`perimeter_lf` this produces the *whole-building* exterior wall area even for facades that are not
drawn (Bob's has no side elevations; Crow has all four). On Crow the two routes agree to 1.0% (§3.3).
Emit it as a **cross-check that flags disagreement**, not as a second quantity — if silhouette-sum and
perimeter×height disagree by more than ~15%, flag both rather than pick one.

The datum pair is also a **free scale verifier**: two datum texts at `y_a, y_b` with feet values
`f_a, f_b` give `ft/pt = |f_a - f_b| / |y_a - y_b|`. On Crow's north elevation this returns 40.1 ft/in
against the printed 40.0. It is noisy (the label baseline is offset from its leader — other Crow pairs
land 21.7 and 47.1 against printed 20 and 40), so use it as a **±30% plausibility band only**. That
band is still tight enough to reject the Bob's 0.5-vs-8.0 misparse (16×).

---

## 4. Blocking defects that must be fixed first

### 4.1 `_paper_inches` reads the drawing number as the paper-inch value — CRITICAL

```python
# src/bobbytailor/deterministic/printed_scale.py:186-196 (parse_scale_ratio)
left, right = t.split("=", 1)
paper_in = _paper_inches(left)
```
```python
# src/bobbytailor/deterministic/printed_scale.py:166-172 (_paper_inches)
m = re.search(r"(\d+(?:\.\d+)?)", s)      # <-- FIRST digit run anywhere left of '='
if m:
    token = m.group(1)
    if token in _DROPPED_SLASH_FRACTIONS:
        return _DROPPED_SLASH_FRACTIONS[token]
```

For `'2 SCALE: 18" = 1\'-0" FRONT ELEVATION NEW'` the left side is `'2 SCALE: 18" '`; the first digit
run is `2`, so the function returns 2.0 paper inches and never reaches the §11.2 stacked-fraction
repair. Result **0.5 ft/in instead of 8.0**. Crow escapes only because it prints the drawing number
*after* the ratio.

Second, related hole: `_DROPPED_SLASH_FRACTIONS` (`printed_scale.py:127`) only handles the
**concatenated** form (`"332"`); Bob's floor plan prints the **space-separated** form
`'SCALE: 3 32" = 1\'-0"'`, which falls through to `float("3")` → 0.333 instead of 10.667.

Prototype fix, run over every printed scale in all four real PDFs:

```
### Crow - Cass White Road-Plans.pdf                       (no changes)
### Bob's Discount Furniture - Kennesaw, GA-plans.pdf
  p1  OLD=0.3333    NEW=10.6667    'SCALE: 3 32" = 1\'-0"'
  p2  OLD=0.3333    NEW=10.6667    'SCALE: 3 32" = 1\'-0"'
  p3  OLD=0.3333    NEW=10.6667    'SCALE: 3 32" = 1\'-0"'
  p4  OLD=0.5       NEW=8.0        '2 SCALE: 18" = 1\'-0" FRONT ELEVATION NEW'
  p4  OLD=0.3333    NEW=8.0        '3 REAR ELEVATION NEW SCALE: 18" = 1\'-0"'
  p4  OLD=0.2       NEW=4.0        '5 ENLARGED GLAZING AND ENTRY DOORS SCALE: 14" = 1\'-0" 4 TRUCK DOCK…'
  p5  OLD=1.0       NEW=0.5        '1 SCALE: 2" = 1\'-0"'
### Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf   (no changes)
### Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf (no changes)

changed=7 unchanged=383
```

All 7 changes are corrections; **zero** movement on the other three fixtures. The `10.667` value is
independently corroborated: Bob's page-1 footprint solver already lands at `fpp=0.14685` (= 10.57
ft/in) via RANSAC/dimensions, and the corrected elevation scale makes the facade 250 ft wide, matching
`depth_ft=250.0`.

### 4.2 Rotated pages: the clip is built and rendered in the wrong coordinate space — HIGH

`page.get_text(...)` and `page.get_drawings()` return **unrotated** coordinates, but
`page.get_pixmap(clip=…)` expects **`page.rect`** (rotated) coordinates. Bob's page 4:
`rotation=270`, `page.rect=(0,0,3024,2160)`, `mediabox=(0,0,2160,3024)`; drawings span
`x 34..2126, y 99..2972` — i.e. y exceeds `page.rect.height`.

```
raw    Rect(1104.0, 119.0, 1129.0, 2329.0)
rotmat Matrix(0.0, -1.0, 1.0, 0.0, 0.0, 2160.0)
mapped Rect(119.0, 1031.0, 2329.0, 1056.0)
```

`room_fill.measure_enclosed_area` passes the raw rect straight to `get_pixmap`
(`room_fill.py:221`), and `_measure_room_fills` computes the title↔scale gap as `cy - ty1`
(`takeoff_pipeline.py:1817-1819`) which encodes "below" in unrotated y.

**This is already breaking production, not just the new path.** Moxy has 11 pages at `rotation=90`
(pages 7–17). On page 9:

```
rot 90 rect Rect(0.0, 0.0, 3024.0, 2160.0)
title LEVEL 1 LOBBY AR [1004, 2293, 1025, 2486]
title LEVEL 1 LOBBY FF [2047, 2296, 2068, 2486]
scale fpi= 5.333 center [1021, 2406] title 'ID-100 LEVEL 1 LOBBY AR PLAN'
scale fpi= 5.333 center [2064, 2407] title 'ID-100 LEVEL 1 LOBBY FF PLAN'
```

`gap = 2406 - 2486 = -80`, the guard is `-6.0 <= gap`, so no scale binds and the drawing is skipped:

```
page 9  rot 90 room_fills:      (empty)
page 13 rot 90 room_fills:      (empty)
```

With all pairing and clipping done in **page space** (`rect * page.rotation_matrix`), the same sheet
measures:

```
LEVEL 1 LOBBY    AR   fpi=5.33 clip=[278, 384, 991, 996]  px=1584x1361  enclosed=7   SUM=355.4 SF
LEVEL 1 LOBBY    FF   fpi=5.33 clip=[278,1427, 988,2039]  px=1578x1361  enclosed=12  SUM=387.7 SF
```

(Both are truncated by `MAX_REGION_SF = 900.0`, `room_fill.py:73` — a lobby is not a guest room. That
cap must become a parameter, not a module constant, before it is reused for elevations.)

---

## 5. Implementation map

Ordered. Each step names the function, what it must do, and how it is proved offline for free.

### Step 1 — `printed_scale._paper_inches` (`printed_scale.py:141`)
Anchor the paper-inch parse on the **last** `SCALE` keyword occurrence in the left-of-`=` text before
any digit search; when no `SCALE` keyword exists (Moxy's bare ratios) keep today's behaviour. Then, in
order: mixed number `\d+\s+\d+/\d+`; plain fraction `\d+/\d+`; **new** space-separated stacked fraction
(two bare integers whose concatenation is a key of `_DROPPED_SLASH_FRACTIONS` → `A/B`); concatenated
stacked fraction; literal. Python 3.9-safe, pure `re`.

### Step 2 — `printed_scale._number_and_title` (`printed_scale.py:220`)
The left-side digit-strip (`printed_scale.py:243`) removes *all* digit runs, so a **leading** drawing
number is lost. Recover it: if `number is None` after the current scan, take a leading lone integer
from the original normalized text. Titles already survive (`'FRONT ELEVATION NEW'` was extracted
correctly in every probe above); this only restores `drawing_number`.

### Step 3 — new `room_fill.to_page_space(page, rect)` + rotation-correct clipping
Add a module-level helper `to_page_space(page, rect) -> fitz.Rect` = `Rect(rect) * page.rotation_matrix`
normalized (identity when `rotation == 0`). Apply it in `measure_enclosed_area` (`room_fill.py:221`)
before `get_pixmap`, and in `_measure_room_fills` (`takeoff_pipeline.py:1804-1830`) so title bbox,
scale centre, the `cy - ty1` adjacency test and the clip rect are **all** computed in page space.
Parameterise `MAX_REGION_SF` through `_measure_room_fills` instead of relying on the module constant.

### Step 4 — new `room_fill.measure_facade_area(page, clip, feet_per_point, …) -> FacadeResult`
Sibling of `measure_enclosed_area`, same contract (returns `None` on any failure; never raises).
Reuse the render + `INK_THRESHOLD` path, then:
(a) flood the **free** pixels seeded from all four clip borders → background;
(b) `solid = NOT background`; connected-component label `solid`;
(c) return the **largest** component: `area_sf`, `bbox_ft = (w, h)`, `fill_ratio`, `component_count`,
    plus the list of enclosed void areas (openings) so a net area can be reported alongside gross.
Refactor the BFS in `_label_regions` (`room_fill.py:148`) into one shared labeller taking a mask, so
there is one flood-fill implementation, not two.

### Step 5 — new `room_fill.elevation_datums(page, clip) -> List[Tuple[float, float]]`
Parse `(y_pt, feet)` from datum texts inside the clip: a feet-inches token adjacent to
`FINISH FLOOR | T/ | T.O. | TOP OF | PARAPET | GUTTER | TRUCK COURT | GRADE | B.O.`. Return sorted by
y. Two outputs: `wall_band = (y_top, y_finish_floor)` used to crop the facade blob to the wall (drops
roof/gable and the annotation tail — the 56-vs-45 ft excess seen on Crow), and
`datum_ft_per_pt` used **only** as a ±30% plausibility band on the printed scale. Reuse
`_feet_inches_to_ft` / `_WALL_HEIGHT_TOKEN` (`takeoff_pipeline.py:778`) rather than a new parser.

### Step 6 — new `room_fill.elevation_titles(page)` + `ELEVATION_TITLE_RE`
Mirror `plan_titles` (`room_fill.py:115`) but drive it off `extract_printed_scales(page)` — the probes
show the callout title is reliable on Crow, Bob's and Chelsea while `segment_viewports` is not. Match
`\bELEVATION S?\b` in `PrintedScale.title`, and classify orientation (`NORTH|SOUTH|EAST|WEST|FRONT|
REAR|BACK|SIDE|TRUCK DOCK`) and intent (`DEMOLITION|DEMO|EXISTING` → excluded from new-work
quantities; `INTERIOR` → interior finish, not exterior painting). Return
`(title, orientation, is_demo, is_interior, printed_scale)`.

### Step 7 — new `TakeoffPipeline._measure_elevation_areas(page, sheet_name)` (beside `_measure_room_fills`, `takeoff_pipeline.py:1773`)
For each `elevation_titles` entry: build the clip in page space as the band from the previous callout
(or drawing-area edge) up to this callout, `± _ELEV_CLIP_SIDE_PT` horizontally; call
`measure_facade_area` at **that callout's own** `feet_per_point`; crop by `elevation_datums`; check the
scale against the datum band; attach `needs_review` when there is no datum pair, when
`fill_ratio < 0.4` (blob is annotation, not facade), or when the blob bbox width disagrees with the
floor-plan footprint's `width_ft`/`depth_ft` by more than 20%. Return `List[FacadeResult]` on the
bundle key `"elevation_areas"`.

### Step 8 — call it from `_deterministic_bundle` (`takeoff_pipeline.py:1738-1744`)
Add next to the existing `room_fills` block, in the same additive try/except, and **not** gated on
`_PLAN_SHEET_TYPES` — for the same reason `room_fills` is not (`takeoff_pipeline.py:1729-1737`), and
because Chelsea puts 9 elevations on `floor_plan` sheets. Add `"elevation_areas"` to the returned dict
at `takeoff_pipeline.py:1745-1760`.

### Step 9 — routing: `_DETERMINISTIC_SHEET_TYPES` (`takeoff_pipeline.py:236`)
Change to `_PLAN_SHEET_TYPES + ("schedule", "elevation")`. **Leave `_PLAN_SHEET_TYPES` alone** — that
single line is what keeps `extract_walls` / `extract_rooms` / `cluster_symbols`
(`takeoff_pipeline.py:1707`) and `footprint_from_page` (`takeoff_pipeline.py:1716`) off elevations, so
21-13's "no bogus wall-pairing LF on elevations" holds by construction, with a test to pin it.
`_route_deterministic` already degrades correctly: a raster elevation hits
`if resolved_type not in _PLAN_SHEET_TYPES: return None` (`takeoff_pipeline.py:1500-1502`) and falls
back to the legacy vision flow unchanged.

### Step 10 — new `room_fill.keynote_legend(page)` + `keynote_tags(page, clip)`
`keynote_legend` pairs each lone `\d{2}` number block with the text block at the same left-edge x
(the layout observed on Bob's page 4: numbers at x 1226…881 descending, text at the matching x), and
groups legends by their header (`KEYED NOTES`, `DEMO KEYED NOTES`). `keynote_tags` returns the
`(number, x, y)` tags inside a clip. Material keyword mapping (`CMU`, `EIFS`, `SPLIT FACE`, `BRICK`,
`METAL PANEL`, `STOREFRONT`, `STUCCO`, `DRYVIT`) belongs in the existing naming layer
(`object_vocabulary.py` / `component_library.py`), **not** in a new hardcoded dict.

### Step 11 — `fusion._fuse_elevation_areas` (beside `_fuse_room_fills`, `fusion.py:1516`)
Add `"wall_area"` handling for elevation results. `_ROOM_FILL_BASES` (`fusion.py:1601`) stays as is;
add `_ELEVATION_AREA_BASES = frozenset({"wall_area"})` and a separate binder, because
`select_fill_for_basis` (`room_fill.py:131`) dispatches on `BASIS_PLAN_KIND` (`room_fill.py:54`) which
has no elevation concept. Emit one component per (material, orientation) with
`provenance="geometry"`, `name_source="elevation_fill"`, and a `formula` string naming the drawing
title, the fpi, and the datum height. Cross-check against the existing
`perimeter_lf × wall_height` path in `_fuse_wall_classes` (`fusion.py:1356`, perimeter read at
`fusion.py:1379-1390`): if the two disagree by >15%, flag **both** rather than choose.

### Step 12 — `_resolve_project_wall_height` (`takeoff_pipeline.py:860`) gains a Tier-0 source
Elevation datums are the authoritative wall height and beat every keyword tier (and the
`_WALL_HEIGHT_DEFAULT_FT` fallback). Feed `elevation_datums`' span in as `wall_height_source="datum"`.
This is what makes Crow's `perimeter × height` cross-check exact rather than a default-height guess.

---

## 6. Offline verification (free — zero API)

1. **Scale parser, all four fixtures, before/after:**
   `python3 scripts/scale_probe.py "uploads/<each>.pdf"` — assert Bob's page 4 `distinct_fpi` becomes
   `[2.0, 4.0, 8.0]` (from `[0.2, 0.3333, 0.5, 2.0, 8.0]`), Bob's pages 1–3 report `10.6667`, and
   Crow / Moxy / Chelsea are **byte-identical** to the pre-change output. The full sweep printed
   `changed=7 unchanged=383`; pin that as the acceptance number.
2. **Elevation reaches the deterministic path:**
   `python3 -c "from bobbytailor.pipeline.takeoff_pipeline import _DETERMINISTIC_SHEET_TYPES as T; assert 'elevation' in T"`
3. **21-13 guarantee still holds** (the important negative test):
   `_deterministic_bundle(bobs_page4, …, "elevation")` must return `walls == []` **and**
   `wall_lf_by_class == {}` **and** `footprint is None` — while `elevation_areas` is non-empty. Today
   the same call returns `walls: 0` only because the sheet is never routed; after the change it must
   still return 0 because of the `_PLAN_SHEET_TYPES` gate. (Contrast: forcing `floor_plan` yields
   `walls: 22, wall_lf_by_class: 4` — assert the elevation path never does that.)
4. **Facade measurement, position/shape assertions only:**
   `python3 scripts/geom_probe.py "uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf"` →
   page 4 must emit ≥3 elevation areas; assert **blob width** 245–255 ft against
   `footprint_from_page(page 1).depth_ft == 250.0`, and `fill_ratio >= 0.4`. Never assert on 16,219.
5. **Crow two-route identity:** assert
   `abs(sum(elevation_areas on page 1) - footprint(page 0).perimeter_lf * datum_height) / (perimeter × height) < 0.15`.
   Measured today: `135,528` vs `134,246` → 0.95%.
6. **Chelsea generalization:** run the elevation pass on pages 9–12, 13–16, 18 and assert exactly one
   dominant component per titled elevation (21 drawings), all at their printed 8.0 / 4.0 ft/in.
7. **Rotation regression, existing engine:** `_deterministic_bundle` on Moxy pages 9 and 13
   (`rotation=90`) must return non-empty `room_fills` (today: empty). Assert
   `LEVEL 1 LOBBY - AR PLAN` is present with area > 300 SF.
8. **Whole offline suite:** `python3 -m pytest -q` (pytest.ini already sets `-m "not golden"`, so no
   paid fixture runs). Expect the 1132 tests green plus new unit tests; `tests/test_printed_scale.py`
   and `tests/test_sheet_pass_matrix.py` will need additions, not rewrites.

---

## 7. Risks

* **Silhouette over-capture.** The blob absorbs anything the outline touches — grid bubbles, dimension
  strings, roof/gable triangles. Crow's blob bbox reads 56–64 ft tall against a 45'-2" parapet. The
  datum crop (Step 5) is the mitigation; without it the numbers run ~20% high, and a drawing with no
  datum pair must be flagged rather than emitted.
* **Demolition and interior elevations double-count.** Bob's page 4 carries `FRONT ELEVATION
  DEMOLITION` (6,134 SF) alongside `FRONT ELEVATION NEW` (6,245 SF); Bob's page 0 index lists
  `A6.0 INTERIOR ELEVATIONS & DETAILS`. Title-based exclusion (Step 6) is mandatory, and a
  same-orientation NEW/DEMO pair should flag if both survive.
* **The CMU/EIFS split is not fully deterministic.** Keynote tags say *which* materials and *where a
  tag sits*; they do not draw the boundary. Emitting a confident split would be the §10 coincidence
  trap in a new costume. Gross-per-elevation confident + split flagged is the honest output.
* **Facades that are not drawn.** Bob's has no side elevations, so a silhouette-only sum can never
  reach a golden that covers the whole building. The `perimeter × datum height` route covers them —
  which is why Step 11 must emit the cross-check and flag disagreement instead of silently preferring
  one number.
* **Rendering cost.** Bob's page 4 at 120 dpi is a 3752×774 clip; Crow page 1 at 80 dpi is 2778×534.
  The pure-Python BFS in `_label_regions` (`room_fill.py:148`) is O(px) with a `deque` per component
  and was measurably slow on the Moxy pages (the probe ran ~1 min for two pages). Elevations are
  wide-format; pick DPI per clip so the pixel budget is bounded, and share one labeller (Step 4) so
  the cost is paid once per clip, not twice.
* **`MAX_REGION_SF = 900.0`** (`room_fill.py:73`) is a guest-room constant. It already truncates
  Moxy's Level-1 Lobby and would be nonsense for a 50,000 SF facade. It must become a parameter in the
  same change, or the elevation path will silently return `None`.

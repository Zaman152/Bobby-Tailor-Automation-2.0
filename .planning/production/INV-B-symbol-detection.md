# INV-B — Is Phase 25 (symbol detection) achievable? Columns / Ladder / Stairs

**Investigator:** Job B · **Date:** 2026-08-13 · **Cost:** $0.00 (all offline, direct module calls)
**Subject:** Crow – Cass White Road, `uploads/Crow - Cass White Road-Plans.pdf`, **page 0** (OVERALL FLOOR PLAN @ 1"=40', fpp 0.5556 ft/pt)

---

## TL;DR — blunt verdict

| Item | Golden | Deterministically reachable? | Best honest number | Verdict |
|------|--------|------------------------------|--------------------|---------|
| **Columns-H-35'** | 132 EA | **YES for 120 of them, position-verified, 100% lattice occupancy, zero false positives across 22 pages of 3 plan sets.** The remaining 12 are **not drawn on this sheet** — they need one stated extrapolation rule. | **120 measured**, 132 after grid completion | **ACHIEVABLE — 2 days.** Highest-value fix in the whole program. |
| **Ladder-H-20'** | 1 EA | **YES.** Pure text route. Keynote 1 = "ACCESS LADDER TO CONCRETE ROOF…", and it appears **exactly once** on the plan (plus once in the legend). | **1** | **ACHIEVABLE — 0.5–1 day.** Blocked by a one-line regex defect. |
| **Stairs** | 10 EA | **NO. Not by any route, deterministic or ML.** The stair objects are not on any of the 4 uploaded pages. They live on `A-401` details and the `A-111/112/113` enlarged plans, **which are not in the uploaded PDF**. | **flag "not in set"** | **NOT ACHIEVABLE. Human input required. Stop trying.** |

**Ceiling on Crow with the file the user actually uploads: 9 of 10 items, not 10.** Anyone promising "near-100% on Crow" from this 4-page PDF is promising something the document cannot supply. Say that out loud to the user now rather than after another week of detector work.

**Bonus finding that is arguably bigger than the column fix:** the **"Bollards 56 vs 28"** defect is not a bollard problem. `SYM-2` (count 56) is **56 of the 120 column markers**, all on-grid, mis-labelled as Bollards by the semantic pass. Fixing columns fixes Bollards' false positive at the same time. See §5.

---

## 1. Ground truth §10/§11 is CORRECT about the 136, and WRONG-BY-OMISSION about the columns

§10's conclusion stands exactly as written: the 136-count cluster is a collinear tick row.

Measured now, on page 0, using the closed-rectangle census (`scratchpad/p12_all.py`):

```
  size (pt)      n     xspan    yspan   y-bands
  (1.80, 0.72)  136   1885.2      0.0   [1200.0]        <- §10's "136 columns". CONFIRMED TICKS.
  (1.44, 1.56)  120   1846.8    435.0   [1308, 1395, 1482, 1569, 1656, 1743]   <- REAL COLUMNS
  (1.32, 1.32)   40   1846.9      0.0   [1199.0]        <- panel-joint ticks
```

§10 then concluded *"no 2-D small-marker lattice exists; columns detection is unsolved."* **That second half is false.** The `(1.44, 1.56)` class — 9.6" × 10.4" at plan scale, i.e. an HSS10×10-class column — is a genuine 2-D lattice with **yspan 435.0 pt spanning six distinct gridline Y values**.

§10's 2-D search missed it because of its own filter: it required *"both spans > 300 pt, count 30–250"* — but the search was run over **`cluster_symbols` GROUPS**, and `cluster_symbols` never produces a group containing these 120 markers (§4 explains why). The lattice was invisible to the search, not absent from the drawing.

---

## 2. Columns — the evidence, and the control that proves it is not a coincidence

### 2.1 The grid is fully recoverable from printed text

Grid bubbles on page 0 (`scratchpad/p3_isect.py`):

```
num gridlines 22  ['1'..'22']   at y=969.6, x 437.7 .. 2482.5
let gridlines  8  ['A'..'H']    at x=331.0, y 1201.0 .. 1831.0
num spacings [99.0, 97.2 x20, 99.0]      -> 55'-0", 54'-0" x20, 55'-0"  = 1136'-0"  ✓ printed
let spacings [108.0, 87.0 x6]            -> 60'-0", 48'-4" x6          =  350'-0"  ✓ printed
```

Both reconcile **exactly** to the sheet's own printed overall dimensions (`1136' - 0"`, `350' - 0"`). This is the drawing validating itself — not a tuned constant.

### 2.2 The markers sit on that lattice with 100% occupancy and zero strays

`scratchpad/p10_map.py`, class `(1.44, 1.56)`:

```
### 1.44x1.56 pt (9.6 x 10.4 in): total=120  on-grid=120  off-grid=0
       1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16  17  18  19  20  21  22
  A    0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0
  B    0   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   0
  C    0   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   0
  D    0   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   0
  E    0   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   0
  F    0   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   0
  G    0   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   0
  H    0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0
```

Six rows × twenty columns, **exactly one marker per cell, no cell empty, no marker off-grid.** That is not a count that happens to look right — it is a shape whose *positions* were predicted by the printed grid and then found.

### 2.3 The control test that kills the "it's just gridline dashes" objection

Gridlines on this sheet are drawn as 18 pt dash segments in the **same style class** as the column. So I probed an intersection and three non-intersection controls (`scratchpad/p4_control.py`):

```
--- INTERSECTION 10-C  (1314.3,1396.0)  n=7
   (1313.64,1394.28)->(1315.08,1394.28) len=1.44   \
   (1315.08,1394.28)->(1315.08,1395.84) len=1.56    |  CLOSED RECTANGLE
   (1315.08,1395.84)->(1313.64,1395.84) len=1.44    |  1.44 x 1.56 pt
   (1313.64,1395.84)->(1313.64,1394.28) len=1.56   /
   (1314.36,1390.20)->(1314.36,1385.64) len=4.56     <- grid tick
   (1311.00,1395.00)->(1315.56,1395.00) len=4.56     <- gridline dash (H)
   (1314.36,1412.64)->(1314.36,1394.64) len=18.00    <- gridline dash (V)

--- CONTROL mid-C between 10 and 11 (on gridline C)   n=1  (just the 18pt dash)
--- CONTROL on gridline 10 between C and D            n=1  (just the 18pt dash)
--- CONTROL bay centre (no gridline)                  n=0
```

The rectangle exists **only** at intersections. Off-intersection, on the same gridline, there is nothing but the dash. The marker is a distinct object.

### 2.4 The detector generalises and does NOT fire falsely

I built the candidate detector (`scratchpad/p19_det2.py`: closed-rect census → text grid axes → 2-D lattice with ≥2 distinct X *and* ≥2 distinct Y, ≥90% occupancy, no duplicate cells) and ran it over **22 pages across three unrelated plan sets**:

```
count, marker_pt, nX, nY, occupancy, marker_in_w, marker_in_h, axisX_len, axisY_len
CROW p0:    (120, (1.44, 1.56), 20, 6, 1.0, 9.6, 10.4, 22, 8)
CROW p1-3:  None
BOBS p0-6:  None
CHELSEA p0-11: None
```

**One fire, on the right page, with the right answer. Twenty-one clean negatives.** The `≥2 distinct Y` requirement is what structurally forbids §10's trap: every tick row has `yspan=0` → one distinct Y → rejected by construction, not by tuning.

### 2.5 The honest gap: 120 drawn vs 132 golden

**The sheet draws 120. It does not draw 132.** At `1-C` and `22-C` (`scratchpad/p11_ends.py`) there is no marker — only the continuous S.C.C.P. panel edge (`16.20`/`15.84` pt verticals) and a grid tick. The end-wall columns are inside the tilt-up panels and are shown on the structural drawings, not on A-101.

I also checked whether the answer key carries positional ground truth. It does not: diffing the take-off PDF against the plans (`scratchpad/p20_diff.py`) shows the estimator's only page-0 markup is a **21-point footprint polygon** tracing `439..2481 × 1200..1828`. **No per-column marks.** The 132 was entered as a number, almost certainly as grid arithmetic.

**So the extrapolation rule must be stated explicitly, not smuggled in:**

> A detected column LINE extends to every gridline on the perpendicular axis.
> Rows are **measured** (B..G have 100% occupancy; A and H have 0% — that is data, not assumption).
> Columns are **completed** (detected on 2..21; extended to 1..22 because the end-wall columns are hidden in the panel).
> → 6 measured lines × 22 grid lines = **132**.

Be honest with yourself about this: I derived "extend along the number axis, don't extend along the letter axis" **after** seeing that golden = 132. Without the answer key I would have reported "120 drawn". The rule is architecturally reasonable and only has ONE degree of freedom, but **it is unvalidated on a second building.** Ship it as a *flagged completion*, not as a silent number:

```
Columns-H-35'   120 EA   [MEASURED]  20x6 lattice @ grid B-G / 2-21, 100% occupancy
                +12 EA   [INFERRED]  end-wall grid lines 1 & 22 x rows B-G — not drawn on A-101,
                                     typical for tilt-up (columns cast into panel). CONFIRM.
                132 EA   total if end-wall columns are priced
```

That is one human click, it is truthful, and it hits golden when the user confirms. It also satisfies "flag, don't guess".

---

## 3. Ladder — achievable, blocked by a two-character regex

Page 0 carries a real KEYNOTES legend (`scratchpad/p13_text.py`), 12 entries:

```
1  ACCESS LADDER TO CONCRETE ROOF OF ELECTRICAL ROOM - SEE ENLARGED PLANS.
2  3'-0" X 3'-0" ROOF HATCH WITH ACCESS LADDER FROM CONCRETE ROOF ...
3  ELECTRICAL ROOM - 1 HOUR RATED
...
12 BRACING DOWN TO 14' A.F.F. - SEE STRUCTURAL
```

`cluster_symbols` already isolates the keynote bubble as `SYM-4` (54 instances) and already computes per-text subcounts:

```
SYM-4 count 54  subcounts {'1':2, '2':2, '3':2, '4':2, '5':3, '6':8, '7':5,
                           '8':1, '9':13, '10':12, '11':1, '12':3}
```

Locating the keynote-1 bubbles (`scratchpad/p22_ladder.py`):

```
keynote '1' bubble at (1319.6,  457.5)  in_legend=True
keynote '1' bubble at (1475.5, 1268.6)  in_legend=False
```

**One legend key, one plan callout → Ladder = 1. Golden = 1. ✓**

### The blocker (concrete, citable)

`src/bobbytailor/deterministic/room_fill.py:294`

```python
_KEYNOTE_NUM_RE = re.compile(r"^(\d{2})\.?$")
```

**Exactly two digits.** Keynotes 1–9 are structurally invisible to `keynote_legend()` and `keynote_tags()`. Proof on the real page:

```python
keynote_legend(page0) ->
  {'KEYNOTES': {'10': 'SANITARY LINE - PROVIDE 6" PVC CLEANOUTS AT 80\'-0"',
                '11': 'DOWNSPOUTS TO BE PIPED TO HUB DRAIN OR THRU RAMP',
                '12': "BRACING DOWN TO 14' A.F.F. - SEE STRUCTURAL"}}
keynote_tags(page0, plan_clip) -> only '10' x11 and '12' x2
```

Keynote 1 — the ladder — never enters the pipeline. The text-anchored infrastructure the project already built is being starved by `\d{2}`.

### Second-order care required

Keynotes **1** and **2** both contain the string "ACCESS LADDER", but keynote 2's subject is a *roof hatch*. A naive alias match on the manifest's `["ladder", "ship ladder", "roof ladder"]` returns **2**, not 1. The head-noun decision ("what is this keynote actually AN ITEM OF?") is a pure semantic judgement with **zero numeric content** — exactly what the vision labelling pass is architecturally allowed to do. Geometry supplies `count = 1`; vision decides that keynote 1 is the Ladder and keynote 2 is a hatch. Keep the numeric field out of the schema, as now.

---

## 4. Why `cluster_symbols` loses the columns — root cause, and why style-class partitioning cannot fix it

The four column edges are **four separate single-line paths** with the same style as the gridlines (`scratchpad/p7_path.py`):

```
PATH 26648 type s width 0.36  l [(1313.64,1394.28),(1315.08,1394.28)]
PATH 26649 type s width 0.36  l [(1315.08,1394.28),(1315.08,1395.84)]
PATH 26650 type s width 0.36  l [(1315.08,1395.84),(1313.64,1395.84)]
PATH 26651 type s width 0.36  l [(1313.64,1395.84),(1313.64,1394.28)]
PATH 29478 type s width 0.36  l [(1314.36,1412.64),(1314.36,1394.64)]   <- gridline dash
PATH 30745 type s width 0.36  l [(1311.00,1395.00),(1315.56,1395.00)]   <- gridline dash
```

Identical `(type, stroke, fill, width)` ⇒ **identical style class**. `symbols.py:216-238` (`_connected_components`, "partitioned by style class") therefore cannot separate them — the module docstring's claim at `symbols.py:13-17` that style partitioning keeps CAD blocks away from "the connective wall/grid network" is **false on this drawing**.

Worse, the gridline dash endpoint `(1314.36, 1394.64)` lies **0.805 pt** from the rect corner `(1313.64, 1394.28)` — inside `ENDPOINT_EPS_PT = 1.0` (`symbols.py:47`) — so the dash **unions into the column's component**:

```
TARGET COMPONENT: n_prims 6  bbox (1311.0, 1394.3, 1315.6, 1412.6)
  size_ft max 10.2   (passes MAX_SYMBOL_FT=15)
  styles [(2, 6)]
```

The component survives the size filter but its **shape signature now depends on how much gridline dash happened to attach**, and the dash phase differs per intersection. Result — the columns shatter:

```
groups whose representative bbox is ~1.44x1.56 pt:
   SYM-2 count 56, SYM-32 count 5, SYM-43 count 3, SYM-45 count 3   (+ 53 below MIN_INSTANCES=3)
```

And `SYM-2`'s 56 instances are all on-grid but only on **rows B, D, F, G** and 14 of 20 number lines — rows C and E have a different dash phase:

```
SYM-2 count 56  on-grid 56  off-grid 0
  B    0   1   1   1   1   1   0   1   0   0   1   0   1   1   1   1   1   1   0   0   1   0
  C    0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0
  D    0   1   1   1   1   1   0   1   0   0   1   0   1   1   1   1   1   1   0   0   1   0
  E    0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0
  F    0   1   1   1   1   1   0   1   0   0   1   0   1   1   1   1   1   1   0   0   1   0
  G    0   1   1   1   1   1   0   1   0   0   1   0   1   1   1   1   1   1   0   0   1   0
```

**Do not try to fix this by loosening or tightening `ENDPOINT_EPS_PT`, `QUANT_PT`, or the style key.** Every one of those is a global knob that will re-break the groups that currently work (Bollards, dock doors, keynote bubbles), and none of them can undo a connection that is geometrically real at 0.8 pt. The right move is a **separate, additive detector** that never touches `cluster_symbols`.

---

## 5. Bonus: "Bollards 56 vs 28" is the same bug

The brief lists Bollards 56 vs golden 28 as an open defect, and §11.0 records that `_dedup_colocated_count(56) → 56` falsified the concentric-dedup theory. Now we know why the dedup could never work: **`SYM-2` is not bollards.** It is 56 of the 120 column markers (§4), 100% on-grid, and the semantic pass named it "Bollards".

So the column fix has a second payoff: once the 120 markers are consumed by the lattice detector, `SYM-2` disappears as a bollard candidate and the false 56 goes away.

For what it is worth, Crow's bollard count also looks text-anchored, not shape-anchored — general note 13 on page 0 states: *"PROVIDE BOLLARDS AT ALL DRIVE-IN OVERHEAD DOOR JAMBS, FIRE PROTECTION RISERS, ELECTRICAL TRANSFORMERS AND EXPOSED ELECTRICAL PANELS"*, and note 14 gives the 6" O.D. spec. Bollards are a **derived quantity from a door schedule**, not a countable glyph on a 1"=40' plan. That belongs to whoever owns Job A/C, but it points the same direction as everything else here.

---

## 6. Stairs — not achievable, and here is exactly why

There is **no "STAIR" text anywhere on page 0** (`scratchpad/p13_text.py`). Every stair reference in the set is a cross-reference to a sheet that was not uploaded:

```
p1 (2368,103) 'E2  STAIR AND GUARDRAIL, TYP. SEE 6/A-401, 8/A-401, 10/A-401'
p2 (1508,1424) 'SCALE: 1/2" = 1'-0"   6  STAIR PLAN'
p2 (992,2010)  'SCALE: 1 1/2" = 1'-0" 8  STAIR RAIL'
p2 (266,2010)  'SCALE: 1/2" = 1'-0"  10  STAIR SECTION'
```

The E-tag route is dead: the tags exist **only in the legend**, never as placed callouts (`scratchpad/p15_e2.py`):

```
E1 1 [(2373.8, 81.2)]   E2 1 [(2373.8, 108.2)]   E3 1 [(2373.8, 135.2)]
E4 1 [(2373.8, 162.2)]  E5 1 [(2373.8, 189.2)]   E6 1 [(2373.8, 216.2)]
```

`E2` is marked **"TYP."** — an explicit instruction that the drawing is *not* enumerating instances.

A geometric tread detector (runs of ≥4 evenly spaced parallel 2–14 pt segments, `scratchpad/p21_stairs.py`) finds:

```
CROW p0 plan region: 0 tread-like runs
CROW p1 elevations:  1 tread-like run  (ang=90 L=3.5 n=5 at (2451,1870))
```

**Zero in the plan; one in an elevation.** There is no population of 10 anything.

And structurally there cannot be: page 0 is the key plan, and it defers three times — `SEE 1/A-111`, `SEE 1/A-112`, `SEE 1/A-113` — to enlarged plans that are **not in the uploaded 4-page PDF**. The 10 stairs are on sheets the user did not upload.

**No detector — deterministic, ML, or vision — can count objects that are not in the file.** The only correct behaviour is to emit `Stairs — NOT IN UPLOADED SET (referenced on A-401 / A-111-113)` and ask the user. Any number the system prints here is a fabrication. This also means the same golden fixture will keep scoring 9/10 forever unless the user uploads the full set, and that fact should be stated in the fixture, not discovered again next month.

---

## 7. Recommended build — deterministic, additive, ~3 days

**New module** `src/bobbytailor/deterministic/grid_lattice.py` (~250 LOC). It must not modify `symbols.py`.

1. **`closed_rects(prims, max_dim_pt)`** — index axis-aligned H/V segments by exact endpoint; emit `(x0,y0,x1,y1)` where all four edges are present. ~40 LOC. Already prototyped and correct.
2. **`grid_axes(page)`** — colinear runs of ≥4 tokens matching `^\d{1,2}$` or `^[A-Z]$`; return every candidate row/column axis. Validate that consecutive spacings reconcile to the sheet's printed overall dimension strings (Crow: 1136'-0" and 350'-0" — both matched exactly).
3. **`lattice_groups(rects, axes, fpp)`** — for each `(row-axis, col-axis, marker-size)` triple, snap centres (tol 6 pt) and **accept only if**: `n ≥ 12`, `≥2 distinct X`, `≥2 distinct Y`, occupancy `≥ 0.9`, **no duplicate cells**. Pick the largest survivor.
4. **Emit `LatticeGroup`** with `count`, per-instance cell IDs (`B-7`), marker size in inches, occupancy, and `completion_candidate = n_rows × len(full_perpendicular_axis)` **as a separate flagged field**.
5. **Bind by manifest, not by count** — a marker 6"–24" square at ≥12 grid intersections is a structural column; let the vision semantic pass choose the manifest name (`Columns-H-35'`) from the candidate registry as it does today. Zero numeric fields in the schema.

**Keynote fix** — `room_fill.py:294`: `^(\d{2})\.?$` → `^(\d{1,2})\.?$`. Then re-pin `keynote_legend`/`keynote_tags` tests; then route keynote text → manifest alias with head-noun disambiguation via the semantic pass (keynote 1 = Ladder, keynote 2 = hatch).

**Stairs** — no code. Wire into the existing "flag, don't guess" surface from Phase 28 as `NOT IN UPLOADED SET` with the cross-reference sheet IDs quoted from the drawing.

### Validation that costs nothing

Every acceptance test above runs offline against `uploads/`:
* Crow p0 → exactly one lattice, 120, 20×6, occupancy 1.0, marker 9.6"×10.4".
* Crow p1–3, Bob's p0–6, Chelsea p0–11 → **zero** lattices. (Already verified: 21/21 clean.)
* Tick-row regression: assert the 136 × `(1.80,0.72)` class and the 40 × `(1.32,1.32)` class are rejected for having one distinct Y. This is §10's trap encoded as a permanent test.

Do **not** add a test asserting `Columns == 132`. Assert `measured == 120` and `completion_candidate == 132`, so the extrapolation stays visible and falsifiable.

---

## 8. What I would tell the user, in one paragraph

We found the columns. They are real, we can prove where all 120 of them are, and the detector fires on exactly the right page and nowhere else across three plan sets. Two days of work turns Columns from MISSING into a number with a map behind it, and it simultaneously kills the false 56 that has been reported as Bollards. The Ladder is a half-day fix to a regex that has been hiding every single-digit keynote from the pipeline. **The Stairs are not in the PDF you uploaded** — they are on sheets A-111/112/113 and A-401, which the plan set references but does not contain — so no amount of engineering will produce that 10, and we will flag it for you rather than invent it. Realistic ceiling on Crow with the current file: **9 of 10 items**, one of them requiring a single confirmation click on the 12 end-wall columns. If you want 10 of 10, upload the full sheet set.

---

## Appendix — reproduction

All probes are free, offline, read-only. Scratchpad:
`/private/tmp/claude-501/-Users-muhammadumer-Documents-Projects-Bobby-Tailor-Automation-2-0/fcf374e8-0f31-46e2-8af8-8bff7b817d33/scratchpad/`

| Script | Proves |
|--------|--------|
| `p1_clusters.py` | the 48 `cluster_symbols` groups on page 0 with spans (no 120-group exists) |
| `p3_isect.py` | grid axes from text; primitive census at all 176 intersections |
| `p4_control.py` | the closed rect at intersections vs bare dash off-intersection |
| `p7_path.py` | the column is 4 single-line paths, same style as the gridlines |
| `p8_comp.py` | the gridline dash unions into the column component at 0.805 pt |
| `p10_map.py` | 120 markers, 6×20, occupancy 1.0, 0 off-grid |
| `p12_all.py` | full closed-rect size census with xspan/yspan/y-bands |
| `p17_sym2.py` | `SYM-2` = 56 columns on rows B/D/F/G — the "Bollards" false positive |
| `p19_det2.py` | detector across Crow + Bob's + Chelsea: 1 fire, 21 clean |
| `p20_diff.py` | take-off markup is a 21-point footprint polygon — no column positions |
| `p21_stairs.py` | 0 tread runs in the plan, 1 in an elevation |
| `p22_ladder.py` | keynote-1 bubble: 1 in legend, 1 on plan |

**Code citations:** `src/bobbytailor/deterministic/symbols.py:13-17` (false style-partition claim), `:47` (`ENDPOINT_EPS_PT`), `:56` (`MIN_INSTANCES`), `:216-238` (`_connected_components`), `:516` (`cluster_symbols`); `src/bobbytailor/deterministic/room_fill.py:294` (`_KEYNOTE_NUM_RE`), `:1644` (`keynote_legend`).

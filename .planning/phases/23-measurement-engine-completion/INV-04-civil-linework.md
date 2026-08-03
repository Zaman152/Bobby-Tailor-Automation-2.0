# INV-04 — "Civil linework LF" (Bob's Gas Piping 886 LF)

Investigation date: 2026-08-03. Read-only; every number below is pasted from a real
offline run (zero API calls). Scratch prototypes live in the session scratchpad, not the repo.

---

## TL;DR

1. **The premise in `docs/PIPELINE-GROUND-TRUTH.md` §9 is wrong.** Bob's Gas Piping is **not on a
   civil sheet**. The uploaded Bob's plan set has **7 sheets — CS-1, A1.1, A2.0, A3.0, A4.0, A8.1,
   A8.3 — and no C-sheet and no P-sheet at all**. The `C402.4` that §9 cites is an *IECC energy-code
   table reference* inside a note on A4.0, matched by a sheet-number regex. The gas run is drawn on
   **A3.0 ROOF PLAN (PDF page 3)**, which the pipeline already classifies as `roof_plan` — already
   inside `_PLAN_SHEET_TYPES`. **No civil-sheet engine is needed. Nothing about GAP 4 requires a new
   sheet type.**
2. **The piping is trivially separable from other linework — but not by width, colour, dash array or
   layer.** All of those are identical to the rest of the sheet. It is separable because it is drawn
   with an **annotated CAD linetype**: the line is *broken* at a regular ~33.7 pt pitch and the gap
   is filled with the literal word **`GAS`**, rendered as **39 micro stroke segments** (SHX vector
   text, invisible to `get_text()`). That repeating, signature-identical, line-breaking mark is the
   discriminator.
3. **Position-validated, not count-tuned.** The detector finds **164 mark blobs on page 3; 162 of
   them fall within 12 pt of the polyline the human estimator actually traced** (recoverable from
   the take-off PDF's own green markup vectors — used as an answer key only). That is a
   position/shape validation, exactly what §10 demands instead of matching a golden count.
4. **Across the other 79 pages of Crow + Chelsea + Moxy the detector fires ZERO times.** No false
   positives. (A naïve version *did* fire on Crow's "K.O." dock-panel tag row — the §10 coincidence
   trap — and is killed by the pitch/glyph-span ratio gate. Evidence below.)
5. **Measured result: 847.8 LF vs golden 886.77 LF = −4.4%** at the sheet's own 3/32" scale.
6. **Two scale bugs stand between that geometry and a correct number, and they are the real
   blockers.** Today the pipeline resolves page 3 at **1.0 ft/in instead of 10.667 ft/in**, so the
   same run would report **79.5 LF**. Both bugs are in `deterministic/printed_scale.py`, both are
   one-function fixes, and both also fix GAP 3 (Bob's elevations currently mis-scale the same way).
7. **Naming must be sheet-text-anchored with an explicit ambiguity gate.** The mark spells "GAS" but
   the glyph is vector, there is no OCR on this machine, and a template-match experiment
   **failed** (evidence below) — so do not pretend to read it. Name from the sheet's own text
   (`ALL GAS PIPING TO BE PREPPED AND PAINTED YELLOW. RE: P2.0.` is on A3.0) and **flag, don't
   guess**, whenever the sheet offers more than one linear-basis noun for more than one run family.

---

## 1. What a "civil sheet" looks like — there isn't one

```
$ python3 -c "... page-by-page title-block sheet number ..."
page 0  CS-1   COVER SHEET
page 1  A1.1   FLOOR FINISH PLAN
page 2  A2.0   REFLECTED CEILING PLAN
page 3  A3.0   ROOF PLAN
page 4  A4.0   FRONT ELEVATION DEMOLITION / ELEVATIONS
page 5  A8.1   (door + hardware schedules)
page 6  A8.3   STANDARD DETAILS
```

Bob's take-off (`uploads/Bob's Discount Furniture - Kennesaw, GA-Take offds.pdf`) is 4 marked-up
sheets, and page 0 of it is A3.0. Its text layer carries the estimator's own legend:

```
page 0: 'Gas Piping'   '886.77 LF'
page 1: 'Lintels'      '179.24 LF'
```

So Gas Piping is an **A3.0 roof-plan** quantity. The Chelsea set (32 pages) likewise has **no civil
sheet** — it is cover/elevations/finish plans/unit plans, and its golden CSV
(`tests/fixtures/chelsea/chelsea_golden.csv`) contains **no LF piping item**. There is no second
civil sample in `uploads/`.

**Action:** correct §9 of `docs/PIPELINE-GROUND-TRUTH.md`. The frontier is not "civil sheets", it is
**open-run linear measurement on any plan sheet**.

### Positional ground truth (answer key only)

The take-off PDF's markup layer is vector. The estimator's Gas Piping trace is 34 line segments in
colour `(0.47, 0.94, 0.03)` at width 4.8 (plus a 4-segment legend swatch, excluded):

```
n segs 34  total pt 5985.5
(674,627)-(702,627)  (702,627)-(702,904)  (702,904)-(848,904) ... (1576,549)-(1576,1910) len 1361.7 ...
```

`5985.5 pt ÷ 886.77 ft = 6.750 pt/ft` → `72 / 6.750 = 10.667 ft per paper inch` → **3/32" = 1'-0"**,
which is exactly the callout printed on A3.0. This independently confirms the sheet scale and is the
position key used for validation below. It is **never** pipeline input.

## 2. What the piping looks like in the vector data

`page.get_drawings()` style histogram, page 3 (6,318 paths / 44,854 line items):

```
1808 ('s',(0,0,0),0.96,'[] 0')
1695 ('s',(0,0,0),0.48,'[] 0')     <- the gas line lives in here, with everything else
1075 ('s',(1,1,1),0,   '[] 0')
 196 ('s',(0.6,0.6,0.6),0.24,'[] 0')
 ...
```

- **No optional-content layers:** `doc.get_ocgs()` → `{}`. `_visible_drawings()`
  (`src/bobbytailor/deterministic/dimensions.py:222`) has nothing to filter on.
- **No dash array:** every path reports `dashes='[] 0'`. The "dashing" is *exploded* into separate
  short line paths by the CAD export.
- **No distinguishing width or colour:** the run is black `w=0.48`, same as 1,695 other paths.
- **No text label on the run:** the only words within 40 pt of the traced polyline are keynote
  bubbles — `01` ×12 (the RTUs the branches terminate at), `07` ×9, `09` ×1. The literal sheet text
  `GAS` appears exactly **once** on page 3, in a general note, nowhere near the run.

The actual discriminator, seen by rendering the run at 6×:

> `— GAS — GAS — GAS — GAS —`

The word `GAS` is baked into the linetype and is drawn as vector strokes ("AutoCAD SHX text"), so
`page.get_text()` cannot see it. Measured signature on page 3:

| property | value |
|---|---|
| micro-strokes per mark | **39**, identical for every mark |
| mark bbox | **10 × 4 pt** (horizontal runs) / **4 × 10 pt** (vertical runs) |
| mark pitch along the run | **33.7 pt** (≈ 5.0 ft at 3/32") |
| pitch ÷ glyph span | **3.4** |
| the line is *absent* under every mark | `break_frac = 1.00` |

### Position validation — 162 / 164

```
candidate glyph blobs (>=20 strokes): 164
ON golden run (<=12 pt from the estimator's traced polyline): 162   OFF: 2
sample OFF: (1897,1183) (1873,1183)      # just past where the estimator stopped
```

This is a **position/shape** validation of detection, per HARD RULE 6. No count was matched.

## 3. Selection recipe (deterministic, validated)

A run is an **annotated linetype run**: a collinear chain of stroked segments that is periodically
interrupted by signature-identical vector glyph marks.

```
S1  Harvest every stroked line item on the page, keeping (p0, p1, length, width, colour).
S2  MICRO = items with length < 2.5 pt. Union-find them by endpoint proximity < 2.0 pt into blobs.
S3  A MARK = a blob with 18..120 strokes and max bbox span <= 24 pt.
    Its SIGNATURE = (stroke_count, round(max(w,h)), round(min(w,h))).      -> GAS = (39,10,4)
S4  DASHES = items with length >= 3.0 pt. Group by (angle bin 1 deg, perpendicular offset / 1.2 pt).
S5  Within a group, project onto the line direction and merge pieces whose gap <= 48 pt.
S6  For each merged span and each signature, take the marks within 9 pt perpendicular of the line
    and inside the span (+/- 48 pt). Require:
      a) >= 3 marks of ONE signature
      b) mean pitch >= 15 pt AND pitch <= 6 x glyph span          <- kills the Crow K.O. tag row
      c) pitch coefficient of variation <= 0.35                    <- it is a linetype, not a label row
      d) >= 80% of marks BREAK the line: no dash ink within +/- (glyph_span/2 + 1) pt of the mark,
         and dash ink present on BOTH sides within 0.6 x pitch     <- the decisive test
S7  Clamp the run to [first_mark - pitch, last_mark + pitch] intersected with the merged span.
S8  Dedupe near-identical parallel runs (same signature, |off| < 1.5 pt, > 90% overlap).
S9  Chain/close: absorb, ONE hop, any stroked segment 3..70 pt long with a free endpoint within
    4.0 pt of a run endpoint (terminal drops, risers and elbows carry no glyph and are short).
```

Steps b/d are what separate a *linetype* from *a row of repeated tags sitting on a line*.

### Cross-plan false-positive sweep (the honesty test)

```
#### Bob's Discount Furniture - Kennesaw, GA-plans.pdf
  page  3 sig=(39, 10, 4)   runs=14 marks=160 span=  5472.5pt +stubs=  5722.8pt pitch~33.7 ratio=3.4
       LF: span=810.7  span+stubs=847.8  (golden 886.77 -> -8.6% / -4.4%)
#### Crow - Cass White Road-Plans.pdf
  (no annotated-linetype runs)
#### Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf
  (no annotated-linetype runs)
#### Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf
  (no annotated-linetype runs)
```

**One family on one page across 83 pages. Zero false positives.**

Earlier iterations are the cautionary tale and must be preserved as regression tests:

| iteration | Crow p1 | Chelsea | why it fired |
|---|---|---|---|
| collinear + near-a-blob | 733 "runs", 35,908 pt | 13 pages | any line passing near any dense ink |
| + signature + regular pitch | `sig=(54,2,2)` 34 marks, pitch 53, `break_frac=1.00` | 5 pages | **the "K.O." dock-panel tag row** — 34 identical tags evenly spaced along the grade line, and the grade line really is broken at each. Rendering it shows a dock elevation, not piping. |
| + `pitch <= 6 x glyph span` | **none** | **none** | K.O. ratio = 53/2 = 26.5; Chelsea ratios 10–24; GAS ratio = 3.4 |

## 4. Measurement + the scale blockers (this is the actual blocker)

`geom_probe` on Bob's today:

```
=== page 3 type=roof_plan fpp=0.013888888888888888
  wall_lf_by_class: {'TC1': 30.5}
```

`fpp = 0.0138889` is **1.0 ft/in**. The sheet is **3/32" = 1'-0" = 10.667 ft/in**. The gas run would
report `5722.8 x 0.0138889 = 79.5 LF` against a golden of 886.77. Two independent defects:

### BUG-A — stacked fractions split across spans (`printed_scale.py:141 _paper_inches`)

`page.get_text('rawdict')` on the A3.0 callout returns three spans:

```
SPAN ArialMT 12.6  'SCALE: '
SPAN ArialMT  8.8  '3 32'          <- the stacked fraction; the slash is GONE and a SPACE is left
SPAN ArialMT 12.6  '" = 1'-0"'
```

`_DROPPED_SLASH_FRACTIONS` (`printed_scale.py:127`) keys on the *concatenation* `"332"`, so it never
fires on `"3 32"`; the whole/decimal branch at line 166 then grabs the first digit run `"3"` →
3 paper inches → **0.3333 ft/in, a 32× error**.

### BUG-B — the paper-inch scan is not anchored (same function)

`_paper_inches` regexes the whole of `text_before_eq`, so a leading drawing number wins:

```
'2 SCALE: 18" = 1'-0" FRONT ELEVATION NEW'   -> 0.5000 ft/in   (should be 8.0)
'3 REAR ELEVATION NEW SCALE: 18" = 1'-0"'    -> 0.3333 ft/in   (should be 8.0)
```

Both are on Bob's A4.0 — **this is also GAP 3's elevation-area blocker.**

**Verified fix** (anchor at the last `"` before `=`, then parse right-to-left, adding a
split-stacked-fraction rule):

```
text                                           expected   current    fixed
SCALE: 3 32" = 1'-0"                           10.6667    0.3333     10.6667   OK
2 SCALE: 18" = 1'-0" FRONT ELEVATION NEW       8.0000     0.5000     8.0000    OK
3 REAR ELEVATION NEW SCALE: 18" = 1'-0"        8.0000     0.3333     8.0000    OK
SCALE: 14" = 1'-0"                             4.0000     4.0000     4.0000    OK
SCALE: 12" = 1'-0"                             2.0000     2.0000     2.0000    OK
SCALE: 1" = 1'-0" / 1" = 40'-0" / 1" = 20'     (unchanged)                     OK
1/4" / 3/32" / 1 1/2" literal-slash forms      (unchanged)                     OK
SCALE: 1 12" = 1'-0"   (stacked "1 1/2")       0.6667     1.0000     0.6667    OK
SCALE: 1 16" = 1'-0"   (stacked "1/16")        16.0000    -          16.0000   OK
```

14/15; the only failure is the hypothetical triple-token `"1 1 2"`, which occurs in none of the four
plan sets — leave it returning the safe value and let the caller flag.

After the fix, every Bob's callout parses correctly:

```
page 1 type=floor_plan fpp=0.146850  printed 'SCALE: 3 32" = 1'-0"'   fpi=10.6667
page 3 type=roof_plan  fpp=0.013889  printed 'SCALE: 3 32" = 1'-0"'   fpi=10.6667   <-- still wrong fpp
page 4 type=elevation  fpp=0.111111  printed '... 18" = 1'-0" ...'    fpi=8.0000    <-- now correct
```

### BUG-C — callout↔viewport binding is not rotation-aware (`printed_scale.py:381`)

Page 3 still resolves 1.0 ft/in after BUG-A/B are fixed. `match_scales_to_viewports` documents "scale
labels sit at a drawing's bottom edge" and implements it as `y1 <= cy` — but **every Bob's page has
`/Rotate 270`** (`page.rotation == 270`, `mediabox 2160x3024`, `page.rect 3024x2160`), and
`get_drawings()` / `get_text()` both return **unrotated** coordinates. In unrotated space "below the
drawing" is "to the LEFT". Result:

```
 R1 kind=unknown      bbox=[72,99,2124,2295]     own_fpi=1.0     <- got a DETAIL's scale
 R3 kind=detail       bbox=[965,2295,2124,2789]  own_fpi=None
 main: None
   callout center=[52,2232]  title=''                   fpi=10.6667 (after fix)  <- the real one, x<72 so "outside"
   callout center=[650,2545] title='VENT PIPE DETAIL'   fpi=1.0
```

`identify_main_plan_scale` also returns `None` because that callout's title extraction
(`_title_above`, `printed_scale.py:303`) looks *above* in unrotated space and finds nothing.

**Verified fix — do the containment/below test in DISPLAY space** (`fitz.Rect(b) * page.rotation_matrix`):

```
run bbox display: [549, 263, 1954, 1486]
 R1 kind=unknown disp=[99, 36, 2295, 2088] contains_run=True
     own callout (display-below): gap=20  fpi=10.6667  text='SCALE: 3 32" = 1'-0"'
 R3 kind=detail  disp=[2295, 36, 2789, 1195] contains_run=False
     own callout (display-below): gap=316 fpi=1.0000   text='SCALE: 1" = 1'-0" 2 VENT PIPE DETAIL'
```

The run's own drawing gets its own scale; the detail keeps its own. Rotation-0 sheets (Crow, Chelsea,
Moxy) are unaffected because `rotation_matrix` is the identity there.

### Final measurement

`5722.8 pt x (10.6667 / 72) = 847.8 LF` vs golden **886.77 LF** → **−4.4%**.
The residual ~39 LF is terminal drops/risers more than one hop from a glyph-bearing span; a bounded
2-hop closure recovers it (an unclamped variant reached 897.6 LF, +1.2%) but starts absorbing leader
arrowheads at hop 2, so **ship 1 hop and accept −4.4%**, or gate hop 2 on collinearity with the
touched run.

## 5. Naming — text-anchored, with an ambiguity gate

Sheet text available on A3.0 for the linear-basis vocabulary:

```
'ALL GAS PIPING TO BE PREPPED AND PAINTED YELLOW. RE: P2.0.'
'ALL CONDENSATE DRAIN CONNECTIONS, TRAPS AND PIPING TO DISCHARGE AWAY FROM UNITS.'
'CONDUIT OR PIPE'
'EXHAUST DUCT'
```

Naming priority, most-authoritative first:

1. **SHX-text comment annotation.** AutoCAD's "capture SHX text as comments" export writes a
   `Square` annot with `title == 'AutoCAD SHX Text'` and `content == '<the literal string>'`. When
   such an annot's rect overlaps a mark bbox, **that string IS the label, exactly and for free**.
   Bob's has 46 of these (grid bubbles A–F/1–9 only, so it does not help here); Crow/Chelsea/Moxy
   have zero. Cheap to check, so check it first.
2. **Sheet-text anchor.** Harvest linear-basis phrases from the sheet's own general notes / legend /
   keynotes (`component_library.harvest_from_notes` / `harvest_component_library` already exist)
   matching `(<MATERIAL>\s+)?(PIPING|PIPE|CONDUIT|DUCT|DRAIN|CURB|FENCE|RAIL|SEWER|WATER|STORM)`.
   `GAS PIPING` → canonical `Gas Piping`.
3. **Bind, or flag.** If **exactly one** run family exists on the sheet and **exactly one** phrase
   survives as the head noun of a *material + system* pair (`GAS PIPING` is; `CONDUIT OR PIPE` and
   `EXHAUST DUCT` are equipment-callout fragments, `CONDENSATE ... PIPING` is a discharge note) →
   bind. Otherwise emit the measured LF with `needs_review=True` and
   `review_reason="N linetype families on this sheet, M linear-basis labels — cannot bind
   deterministically"`. **Never round-robin the names.**

### Rejected: reading the glyph by template matching

I tried it so nobody re-tries it blind. Rendering a mark upright at 24× and IoU-scoring it against
strings rendered with `fitz` Helvetica:

```
MARK glyph (112x258 px):
  .....####################.....
  ..#####.................####..
  ..####.....###..........####..
  .....#########......#####.....
  ...
template IoU vs sheet-text candidates:
   SS   0.318      W    0.289      G    0.267      RD   0.239
   ST   0.295      ED   0.278      GA   0.267      GAS  0.231   <- the truth ranks 10th of 12
   AIR  0.292      CD   0.239                      C    0.196
```

Vector SHX stroke fonts do not match filled outline fonts at this size. `tesseract` is **not
installed** (`which tesseract` → not found) and `TESSDATA_PREFIX` is unset, so `get_textpage_ocr()`
is unavailable. **Do not put glyph reading on the critical path.** The signature is for *grouping*
runs, never for *naming* them.

---

## 6. Implementation map

### New module `src/bobbytailor/deterministic/linetype_runs.py`

Mirrors `walls.py`'s shape: points-until-scale-bound, never raises, exposes a dataclass + one public
entry point.

```python
@dataclass
class LinetypeRun:
    polyline_pt: tuple            # ((x,y), ...) in UNROTATED page points
    length_pt: float              # span + closed stubs, points only
    mark_signature: tuple         # (stroke_count, w, h) — grouping key, NOT a name
    mark_count: int
    pitch_pt: float
    pitch_cv: float
    break_frac: float
    candidate_id: str             # "RUN-1", ordered by length descending
    confidence: str
    needs_review: bool
    review_reason: str

def extract_linetype_runs(page, exclude_rects=None) -> List[LinetypeRun]: ...
def run_lf(runs, fpp) -> float: ...     # pure fpp conversion, recompute-safe
```

Reuse from `walls.py` (do **not** fork it — walls require *paired* faces, piping is a single open
line, so `_pair_straight`/`_merge_chains` can never emit it):

- `_visible_drawings` (`dimensions.py:222`) for OCG-hidden filtering.
- `walls._harvest` **must be extended** to carry `width`/`color` per segment (today it returns bare
  4-tuples, `walls.py:204-273`) — factor a `_harvest_styled(page, doc)` that returns
  `(x0,y0,x1,y1,length,width,color)` and have `_harvest` project it down, so wall behaviour is
  byte-identical.
- `walls._angle_bin` (`walls.py:279`) and the interval-union / gap-bridging loop in `_merge_chains`
  (`walls.py:500-572`) as the model for S5/S7. Note `MIN_WALL_SEG_FT = 2.0` (`walls.py:48`) would
  discard the 3-pt dashes — do not apply a wall-length floor here.

### Ordered steps

1. **`printed_scale._paper_inches` (`printed_scale.py:141`)** — anchor the parse at the last `"`
   before `=` and scan right-to-left; add the split-stacked-fraction rules
   (`"N D"` where `N+D` is a `_DROPPED_SLASH_FRACTIONS` key → `N/D`; else where `D` alone is a key →
   `N + D`). Fixes BUG-A and BUG-B. Extend the module docstring's dropped-slash note to say the
   flattening may leave a SPACE, not only a concatenation.
2. **`printed_scale.match_scales_to_viewports` (`printed_scale.py:381`)** — take an optional `page`
   (or a `rotation_matrix`) argument and run both the `_contains` test and the "region directly
   above the label" fallback on display-space rectangles (`fitz.Rect(b) * rot`). Default `None`
   keeps today's behaviour for every rotation-0 sheet. Apply the same transform in `_title_above`
   (`printed_scale.py:303`) so `identify_main_plan_scale` can see the roof-plan title.
3. **New `linetype_runs.extract_linetype_runs`** — implement S1–S9 exactly as §3. Constants at module
   top, each with the observed value in a comment: `MICRO_MAX_PT=2.5`, `GLYPH_STROKES=(18,120)`,
   `GLYPH_MAX_SPAN_PT=24`, `DASH_MIN_PT=3.0`, `OFF_TOL_PT=1.2`, `PERP_TOL_PT=9.0`, `GAP_TOL_PT=48`,
   `MIN_MARKS=3`, `MIN_PITCH_PT=15`, `MAX_PITCH_OVER_SPAN=6.0`, `PITCH_CV_MAX=0.35`,
   `BREAK_FRAC_MIN=0.80`, `STUB_MAX_PT=70`, `STUB_SNAP_PT=4.0`. Guard with the same
   `MAX_SEGMENTS = 200_000` cap as `walls.py:84` and the same never-raise wrapper.
4. **New `linetype_runs.run_scale_fpp(page, run, viewports, printed_by_region)`** — return the fpp of
   the **drawing that contains the run**, resolved in display space, exactly as `_measure_room_fills`
   already does for areas (`takeoff_pipeline.py:1773`). If no containing viewport has its own
   callout, return `None` → the run is emitted with `needs_review` and no quantity, **never measured
   at a borrowed page scale**.
5. **`TakeoffPipeline._deterministic_bundle` (`takeoff_pipeline.py:1587`)** — after the `room_fills`
   block (`takeoff_pipeline.py:1738`), add an equally additive `linetype_runs` block wrapped in
   `try/except`, and add `"linetype_runs": linetype_runs` to the returned dict
   (`takeoff_pipeline.py:1743`). Gate it on the presence of runs, **not** on the sheet type — A3.0 is
   `roof_plan` today but the same linetype appears on plumbing and site sheets.
6. **`fusion.build_registry` (`fusion.py:432`)** — register each run as
   `{"bbox_pt": run_bbox, "kind": "linetype_run"}` under `RUN-n`, so any vision answer naming a run
   is ground-validated like every other candidate.
7. **New `fusion._fuse_linetype_runs(bundle, components, vocab_map, sheet_text)`** — modelled on
   `_fuse_room_fills` (`fusion.py:1516`). Add `_LINETYPE_BASES = frozenset({"linear"})` beside
   `_ROOM_FILL_BASES` (`fusion.py:1602`). Implement the §5 priority: SHX annot → sheet-text phrase →
   flag. Emit `{"name", "quantity": round(length_pt*fpp,2), "unit": "LF", "provenance": "geometry",
   "candidate_id": "RUN-n", "name_source": "linetype_shx"|"sheet_note", "formula": "%.1f pt of
   annotated linetype (mark 'GAS' x N @ %.1f pt pitch) @ %.2f ft/in", "needs_review", "review_reason"}`.
   Call it from `fuse_sheet` next to `_fuse_room_fills` (`fusion.py:1924`).
8. **`component_library`** — add a `linear` classification for `(<MATERIAL> )?(PIPING|PIPE|CONDUIT|
   DUCT|DRAIN|CURB|FENCE|RAIL|SEWER|WATER|STORM)` phrases harvested from general notes, so
   `classify_basis` / `apply_deterministic_basis` yield `basis="linear", unit="LF"` for `Gas Piping`
   without any vision pass.
9. **Ambiguity gate** — in step 7, if `len(run_families) != 1 or len(linear_phrases) != 1`, emit the
   quantity with `needs_review=True` and no confident name. This is the §10 discipline; the Crow K.O.
   row is the exact case it protects against if the pitch gate is ever loosened.
10. **`docs/PIPELINE-GROUND-TRUTH.md` §9** — replace "civil linework on C402.4" with "annotated
    linetype on the A3.0 roof plan; the sheet set contains no civil sheet".

### Offline verification (all free, zero API)

```bash
# 1. The scale parser — pure unit test, no PDF needed.
python3 -c "import sys;sys.path.insert(0,'src');from bobbytailor.deterministic.printed_scale import parse_scale_ratio as p;\
print(round(p('SCALE: 3 32\" = 1\'-0\"'),4)==10.6667, round(p('2 SCALE: 18\" = 1\'-0\" FRONT ELEVATION NEW'),4)==8.0)"
# expect: True True

# 2. The sheet's own scale reaches the run.
python3 scripts/scale_probe.py "uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf"
# expect page 3: distinct_fpi=[1.0, 10.6667]  main=10.6667 (today: [0.3333, 1.0] main=None)

python3 scripts/geom_probe.py "uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf"
# expect page 3 fpp = 0.148148 (today 0.013889); page 4 fpp = 0.111111 unchanged

# 3. POSITION recall — the only honest detection test. Assert >= 95% of detected marks on page 3
#    fall within 12 pt of the take-off PDF's green (0.47,0.94,0.03) markup polyline.
#    Observed: 162/164 = 98.8%.   (answer key only; never pipeline input)

# 4. FALSE-POSITIVE sweep — assert extract_linetype_runs() returns [] for every page of
#    Crow (4), Chelsea (32) and Moxy (40).   Observed: 0 runs on all 76 pages.

# 5. QUANTITY band — assert 840 <= Gas Piping LF <= 935 (886.77 +/- 5%).  Observed: 847.8 (-4.4%).
#    Do NOT assert equality and do NOT tune constants to close the last 4%.

# 6. Regression fixtures to add under tests/fixtures/: the Crow p1 "K.O." tag row
#    (sig (54,2,2), 34 marks, pitch 53, break_frac 1.00) must be REJECTED by the pitch/span gate,
#    and the 5 Chelsea 3-mark candidates (pitch 108-237) must be REJECTED.

pytest -q            # 1132 offline tests; golden marker excluded by default
```

### Risks

- **BUG-C's display-space change touches every sheet's scale binding.** It is the highest-blast-radius
  edit here. Keep the `page`/rotation argument optional and defaulted to `None` so rotation-0 sheets
  (Crow, Chelsea, Moxy = 76 of 83 pages) take a literally unchanged code path, and run
  `scale_probe.py` on all four sets before/after to diff `main` and `own_printed_fpi` per page.
- **One-sample generalisation.** The entire recipe is validated on exactly ONE run family on ONE page.
  The `GAS` linetype is an AutoCAD stock pattern (so are `W`, `SS`, `ST`, `OHE`, `G`), which is why
  the signature test is generic — but nothing in `uploads/` proves it fires on a second project. Ship
  it behind the ambiguity gate and expect the learning loop to supply the second sample.
- **Naming is the weak link, not measurement.** If a sheet carries two run families and two linear
  nouns, the gate flags and the item scores MISSING. That is correct behaviour and will *lower* a
  naive accuracy number relative to guessing — the same decision §10 flagged for the user.
- **Stub closure is the one calibrated parameter.** `STUB_MAX_PT`/1-hop were chosen against a single
  known LF. Treat the ±5% band as the contract, never an exact match, and never widen the hop count
  to chase the last 4% — hop 2 demonstrably absorbs leader arrowheads.
- **Coordinate-space confusion is a live hazard.** `get_drawings()` and `get_text()` return
  **unrotated** coordinates; `get_pixmap(clip=...)` expects **display** coordinates. A crop taken with
  raw drawing coords on a `/Rotate 270` page silently renders the wrong region. Any new code that
  renders for debugging must multiply by `page.rotation_matrix`.
- **`_harvest` signature change in `walls.py`.** Run `gitnexus_impact` on `_harvest` before editing;
  keep the existing 4-tuple return by projecting from the new styled harvester.

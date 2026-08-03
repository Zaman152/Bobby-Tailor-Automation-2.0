# INV-00 — Evidence from scoring the saved runs (free, zero API)

Produced by the orchestrator on 2026-08-03 by scoring already-saved run artifacts with
`scripts/score_report_dir.py`. No API credits spent. This is **measured behaviour of the current
code**, not inference from the symptom log — it should anchor the Phase 23 plan.

---

## 1. The room-fill binding is completely non-functional in the pipeline

**This is the single highest-value finding.** `docs/PIPELINE-GROUND-TRUTH.md` §14 reports the room
engine measuring Moxy Gyp Ceiling to **7.0% blind error** — but those numbers came from a **probe**,
not from the pipeline. The pipeline emits nothing.

Timeline proves the run was not stale:

| Commit / run | Time (07-17) |
|---|---|
| `b4e084d` enclosed-region room engine | 03:37 |
| `9142713` wire the room engine in | 04:03 |
| `9eae50e` **bind measured room areas to line items** | 04:18 |
| `8d6b26f` **classify fix** (mixed sheet must still be measurable) | 04:41 |
| `VisionOnly_Moxy_Knoxville_20260717_045741` run START | **04:57** |

The run postdates **every** room-engine and classifier fix. Its `takeoff.json` nonetheless contains:

```
'room_fill'   appears 0 times
'room_fills'  appears 0 times
'unit_count'  appears 0 times
'plan_name'   appears 0 times
```

And the manifest's `unit_type` prototype entries landed as **empty line items**:

```
ACC BUNK      | 0.0 | (no unit)
ACC KING TUB  | 0.0 | (no unit)
ADA KING RIS  | 0.0 | (no unit)
BUNK A        | 0.0 | (no unit)
BUNK B        | 0.0 | (no unit)
```

**Conclusion:** `_fuse_room_fills` either never runs in the real pipeline, or its output never
survives into `takeoff_summary`. The measurement capability exists and is accurate; the wiring does
not. INV-01 must treat this as the primary defect — fixing it is likely the largest single accuracy
jump available in the whole program.

### 1b. Proven by direct invocation — the measurement engine WORKS

I called `TakeoffPipeline._measure_room_fills` directly on the real Moxy prototype pages (zero API).
**Beware the page index:** searching page text for `ID-411` finds the drawing INDEX first (page 8);
the real prototype sheets are pages 23–38 (ID-407…ID-422), and ID-411 is **page 27** — matching
§13.5's "Moxy p27 → 13 scales @ 4.0". An investigation that probes page 8 will wrongly conclude the
engine returns nothing.

| Sheet | golden SF/unit | AR fill | RCP fill | FC fill | verdict |
|---|---|---|---|---|---|
| ID-411 KING SUITE B (p27) | 353.4 | 369.9 | **341.7 (3.3%)** | 190.9 | works — identical to §14's table |
| ID-415 QQ C (p31) | 284.3 | 260.4 | **284.3 (0.0%)** | 150.5 | exact |
| ID-412 KING SUITE C (p28) | 231.0 | 517.9 | **458.3 (98% over)** | 211.0 | 2× defect |
| ID-416 BUNK A (p32) | 231.0 | 515.5 | **454.7 (97% over)** | 154.1 | 2× defect |

Every fill carries `plan_name`, `plan_kind` (AR/FF/RCP/FC/EM), `scale_fpi=4.0`, `candidate_id`,
`needs_review`. So the engine produces correctly-scaled, correctly-titled, discipline-tagged regions.

**Two consequences for the plan:**

1. **INV-01's target is the DOWNSTREAM path only.** Do not re-engineer measurement. The suspect is
   `_fuse_room_fills(deterministic_bundle, components, vocab_map, room_mix)` (`vision/fusion.py:1924`)
   and specifically `room_mix`: the manifest's `unit_type` entries are landing as empty `0.0` line
   items, which is exactly what you would see if they were consumed by the ordinary
   manifest→line-item path instead of being assembled into the room-mix multiplier. Verify whether
   `room_mix` is non-empty at the call site before changing anything else.
2. ~~**The 2× clip defect has a sharp new clue.** On both defective sheets the over-reach hits AR and
   RCP but not FC/EM… the window swallows the adjacent opposite-hand twin.~~
   **RETRACTED 2026-08-03 — this diagnosis was WRONG. See INV-02, which refutes it with three
   independent probes.** I inferred "the clip leaked" from the ~455 SF readings without testing the
   clip. INV-02 tested it: widening the clip by ±80 pt/side changes ID-412 by **0.0 SF** and ID-416 by
   0.5 SF (they are the *least* clip-sensitive of all 16 sheets), every counted region sits inside 47%
   of the clip, and the drawing's **own printed overall dimensions** `17'-0 1/8" × 26'-9 1/8"` =
   **455.2 SF** match the fill's 458.3 SF at ratio **1.007**. A KING SUITE C really is ~455 SF — a
   suite, not a standard room.
   **The real defect is the multiplier**, not the geometry: `total_for_units()`
   (`room_fill.py:268`) multiplies that correct area by `unit_count: 2` taken from
   `human_inputs/moxy_knoxville.json` — a value a prior session derived from golden `Doors-WD 2 EA`,
   which on a suite means *entry door + connecting door*, not two units. **The human input is wrong,
   and it is applied silently at `confidence: "high"`.** Same signature on ID-412/416/420/422.
   Lesson for this programme: an unverified human multiplier is as dangerous as a hallucinated
   quantity, and my own "measure it and eyeball the ratio" reasoning reproduced exactly the
   peeking-style error §14.3 warns about. `docs/PIPELINE-GROUND-TRUTH.md` §14.2 needs the same
   correction.

### 1c. THE ROOT CAUSE — the title-block window silently deletes 16 of Moxy's 40 sheets

Traced end to end. `run_sheet` (takeoff_pipeline.py:1213) classifies via
`classify_sheet_type_from_text(title_block_text, full_page_text)`; `plan_passes` returns `[]` for
`title_sheet`, and an empty pass list means **skip the sheet entirely — zero API, zero geometry**
(takeoff_pipeline.py:1220-1228). The title-block text comes from
`pdf_analyzer.get_title_block_text` (pdf_analyzer.py:165-180), which assumes ANSI/ASME Y14.1 and
takes the bottom-right quadrant:

```python
w[1] > height * 0.80 and w[0] > width * 0.55     # pdf_analyzer.py:178
```

Run pipeline-accurately over all 40 Moxy sheets: **18 sheets get `passes=0`, including every one of
p23–p38 — all 16 guestroom prototypes**, i.e. every sheet that holds a guestroom quantity.

The title block IS in the bottom-right (on p27 `ID-411` sits at 94% W / 96% H). The defect is that
`x > 55%` of a **3024 pt** wide sheet is far too wide: it swallows the adjacent keynote column, and
84 words of electrical prose drown the handful of title words. Proven by narrowing only the x bound
on the same page:

| window | chars | text | classify |
|---|---|---|---|
| `x>55%W` (current) | 497 | `BED. COORDINATE LOCATION OF OUTLET WITH RECESS CUTOUT...` | **`title_sheet`** → SKIPPED |
| `x>88%W` | 115 | `SHEET NO. JOB NO. DATE SHEET TITLE PHASE A KING SUITE B GUESTROOM ID-411` | **`floor_plan`** → processed |

`'KING SUITE'` and `'ID-411'` are present in BOTH strings — the classifier is not failing to see the
title, it is being outvoted by prose. That makes this a signal-to-noise defect, not a keyword defect,
so the §12 whole-word fix could not have caught it.

**This single constant explains the entire Moxy failure**: the sheets are discarded before geometry,
so `_measure_room_fills` never runs on them, so no `room_fills` reach fusion, so `room_mix` has
nothing to multiply, so every measured item is 0 — while `_measure_room_fills` called directly on the
same pages returns correct areas (§1b).

### 1d. DO NOT fix it by changing the constant — proven regression

Sweeping the x-fraction across all four real plan sets:

| Plan set | skipped @ `x>55%` (current) | skipped @ `x>88%` |
|---|---|---|
| Moxy (40pp) | **18** | **2** — floor_plan 11 → 26 |
| Crow (4pp) | 0 | 0 (unchanged) |
| Bob's (7pp) | 1 | 1 (unchanged) |
| **Chelsea (32pp)** | **2** | **10** — floor_plan 9 → 1, roof_plan 5 → 1 |

Retuning 0.55 → 0.88 fixes Moxy and **breaks Chelsea**, discarding 8 more sheets including nearly
every floor plan. This is the documented fixture-blindness trap: a constant tuned on one CAD template
silently destroys another. **Any Phase 23 plan that changes this number is wrong.**

**The principled fix** — identify the title block by its own STRUCTURE, not by a fixed fraction of
the page. The winning window on Moxy contains the field labels `SHEET NO.`, `JOB NO.`, `DATE`,
`SHEET TITLE`, `PHASE`; a title block is reliably identifiable by carrying such labels (and/or the
sheet-ID pattern), whereas keynote prose is long-form sentences. Candidate approaches, cheapest first:
search progressively narrower bottom-right windows and keep the first whose text looks like a title
block (label-dense, low average sentence length) rather than prose; or locate the sheet-ID token and
take its enclosing ruled box; or drop long prose runs from the extracted text before classifying.

**Mandatory acceptance criterion for the fix (all four sets, one command):** Moxy skipped drops to
≈2 AND Crow (0), Bob's (1), Chelsea (2) do **not** increase. Anything that improves one set while
regressing another is rejected. This check is free — no API — and must be part of the test suite so
the regression can never recur.

**Second-order finding (feeds INV-08):** a sheet carrying five measurable room fills was silently
discarded with only `logger.info`. Any sheet skip must appear in the run's coverage ledger as an
explicit, reviewable decision — this defect was invisible in every report the project produced.

### 1e. End-to-end proof that the classifier fix unlocks the accuracy (free simulation)

Simulated the complete chain the pipeline would run if the sheets were not discarded — for each
prototype page, take its **RCP** fill (the discipline that carries ceiling, per §14 rule 3) and
multiply by the manifest room mix:

| page | unit type | SF/unit | × n | subtotal |
|---|---|---|---|---|
| p23 | KING A | 229.4 | 26 | 5,964 |
| p24 | KING B | 235.5 | 15 | 3,532 |
| p25 | KING C | 217.6 | 5 | 1,088 |
| p26 | KING SUITE A | 362.5 | 5 | 1,812 |
| p27 | KING SUITE B | 341.7 | 2 | 683 |
| p28 | KING SUITE C | **458.3** | 2 | 917 |
| p29 | QQ A | 272.6 | **90** | **24,534** |
| p30 | QQ B | 309.5 | 6 | 1,857 |
| p31 | QQ C | 284.3 | 15 | 4,264 |
| p32 | BUNK A | **454.7** | 2 | 909 |
| p33 | BUNK B | 274.6 | 1 | 275 |
| p34 | ADA KING RIS | 347.2 | 1 | 347 |
| p35 | ACC KING TUB | 347.7 | 3 | 1,043 |
| p36 | ACC QQ RIS | **451.1** | 2 | 902 |
| p38 | ACC BUNK | **458.5** | 2 | 917 |
| | | | **TOTAL** | **49,046 SF** |

Golden Gyp Ceiling = **58,680 SF** → **16.4% error, versus the pipeline currently reporting the item
as absent.** The §13.2 typical-unit × count model is confirmed end-to-end on real geometry.

Two honest caveats, both pointing at real remaining work rather than at this number:
- The golden 58,680 covers **all** ceilings, not just guestrooms. The prototypes legitimately cannot
  sum to it; the missing ~9,600 SF should come from the non-prototype plans (Level 1 lobby, Pop-Up
  Hub, Level 7). So a chunk of the residual is coverage, not error — which is exactly why INV-08's
  coverage ledger matters for interpreting any score.
- ~~The clip defect affects FOUR sheets, not two.~~ **CORRECTED:** p28/p32/p36/p38 (ID-412/416/420/422)
  measure ~451–459 SF because those units genuinely *are* that size (suites/accessible units), and
  INV-02 proved the fill matches each drawing's own printed dimensions to ~0.7%. The four-sheet
  signature is real but it is a **bad `unit_count` in the manifest**, not a clip leak. Their
  contribution to the 49,046 total is therefore roughly double what it should be, so the honest
  measured total is *lower* still and the missing coverage (non-guestroom ceilings) is
  correspondingly *larger* than the 16.4% headline suggests.

**Bottom line for planning: the highest-value single change in the entire programme is the
title-block/classifier fix.** It converts an item reporting nothing into one reporting within ~16%,
and it is a signal-to-noise fix in one function, gated by a free four-plan-set regression check.

Reproduce with:

```python
sys.path.insert(0,'src')
from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline
from bobbytailor.deterministic.viewports import segment_viewports
from bobbytailor.deterministic.printed_scale import extract_printed_scales
page = fitz.open(MOXY)[27]
TakeoffPipeline()._measure_room_fills(page, segment_viewports(page), extract_printed_scales(page), 'ID-411')
# -> 5 RoomFillResult dataclasses (NOT dicts — use dataclasses.asdict)
```

---

## 2. Scored Moxy run (with manifest) — 8% overall

`score_report_dir.py --golden tests/fixtures/moxy/moxy_golden.csv --dir output/VisionOnly_Moxy_Knoxville_20260717_045741`

```
Overall quantity accuracy: 8%   Name/found rate: 88%   Qty acc when found: 10%
  Counts (EA)     n= 6  found=50%   qty_ok=33%
  Measured(SF/LF) n=18  found=100%  qty_ok=0%     <-- ZERO
```

| Item | Golden | AI | Note |
|---|---|---|---|
| Gyp Wall | 129,521 SF | 191 | 99.9% off |
| Gyp Ceiling | 58,680 SF | — | no value emitted |
| Guestroom-Wall Covering | 27,014 SF | — | no value |
| WC-1 … WC-10 | 6,908 SF total | — | no values |
| Base / Lintels / Hand Rail | 3,541 / 1,530 / 65 LF | — | no values |
| CMU Wall | 6,916 SF | 474 | 93% off |
| Exposed Structure | 3,771 SF | 66 | 98% off |
| Gyp Soffit | 260 SF | 36 | 86% off |
| Guard Rail | 189 LF | 83 | 56% off |
| Doors-WD / Doors-HM / Door Frame-HM | 213 / 10 / 215 | — | schedule not parsed |
| Lift, Mobilization | 1, 1 | 1, 1 | PASS (Mobilization is a constant) |

**Name/found rate 88% is circular and meaningless** — the manifest supplied the names. Only the
QUANTITY column is a real measure, and it is 0% on everything measured.

---

## 3. Scored Crow run (plans-only) — 40% overall, and the split is diagnostic

`score_report_dir.py --golden tests/fixtures/crow_cass/crow_cass_golden.csv --dir output/VisionOnly_Crow_A2_20260715_215449`

```
Overall quantity accuracy: 40%   Name/found rate: 60%   Qty acc when found: 67%
  Counts (EA)     n= 6  found=33%   qty_ok=17%    <-- the whole gap
  Measured(SF/LF) n= 4  found=100%  qty_ok=75%    <-- works
```

| Item | Golden | AI | Status |
|---|---|---|---|
| Exposed Structure | 395,673 SF | 397,600 | PASS 0.5% |
| Sealed Concrete | 395,673 SF | 397,600 | PASS 0.5% |
| Internal Tilt up walls | 108,443 SF | 106,998 | PASS 1.3% |
| Mobilization | 1 | 1 | PASS (constant) |
| CMU Wall | 2,204 SF | 8 | FAIL — wall-class binding flip |
| Bollards | 28 | 0 | FAIL |
| Columns-H-35' | 132 | — | MISSING (emitted as "Structural Column 136" in EXTRAS) |
| Ladder-H-20', Lift, Stairs | 1, 1, 10 | — | MISSING |

**This cleanly separates the programme:**
- Crow's residual gap is **counts** (→ Phase 25 symbol detection) and **wall-class binding**
  (→ Phase 24). Its *measurement* is already good (75% qty_ok, three items inside 1.3%).
- Moxy's and Bob's gap is **measurement** (→ Phase 23).

So Phase 23 will barely move Crow and should move Moxy/Bob's enormously. Do not judge Phase 23 by a
Crow re-run.

---

## 4. Naming residue visible in Crow EXTRAS

The pipeline emitted, unmatched to golden: `Structural Column 136 EA`, `Canopy 397,600 SF`,
`Vapor Barrier 397,600 SF`, `Block Fill & Paint 40,086 SF`, `Dock Bumper 56 EA`, `Building Footprint
397,600 SF`, `Building Perimeter 2,972 LF`, plus ~25 unnamed `SYM-n` count rows.

Two separate problems visible here:
1. **The footprint value is bound to SIX line items at once** (verified by filtering `takeoff_summary`
   for the value):

   ```
   Building Footprint  397600.0 SF
   Canopy              397600.0 SF
   Concrete Pad        397600.0 SF
   Exposed Structure   397600.0 SF     <- correct (golden 395,673)
   Sealed Concrete     397600.1 SF     <- correct (golden 395,673)
   Vapor Barrier       397600.0 SF
   ```

   Anything roof/floor-shaped indiscriminately inherits the footprint. Two are genuinely correct;
   the other four are duplicates. **An estimator bidding from this report would price the floor six
   times.** This is a HIGH-severity fusion-binding defect (not a measurement defect) and it also
   inflates the apparent "found" rate. It needs an explicit one-area-one-item arbitration rule:
   a measured region may back at most one line item unless the plan states that two finishes
   genuinely occupy the same area (floor finish + slab, say), and any such sharing must be
   recorded as deliberate rather than emergent.
2. `Structural Column 136` is the documented §10 coincidence (136 collinear dimension ticks ≈ 132
   real columns). It must NOT be "fixed" by matching it to golden — Phase 25 handles this properly.

---

## 5. Tooling status

`scripts/score_report_dir.py` works correctly after the Phase 22 restructure and needs no changes.
It is the free scoring harness for every iteration — use it against saved run dirs before ever
spending on a live run.

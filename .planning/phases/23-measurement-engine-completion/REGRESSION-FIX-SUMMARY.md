---
phase: 23
type: regression-fix
subsystem: fusion / aggregation / measurement
tags: [regression, arbitration, building-layers, D-11, library-fallback, plan-titles, INV-00, SP-9]
evidence-run: output/VisionOnly_P23V_Crow_20260804_141952
status: complete
---

# Phase 23 Regression Fix — Crow 40% → 10% → 40%

A paid plans-only Crow validation run ($0.38) taken after phase 23 closed scored **10% overall
quantity accuracy against a 40% pre-phase-23 baseline**, with measured-item accuracy collapsing from
**75% qty_ok to 0%**. Four defects, three of them introduced by phase 23. All four are fixed; the
verification is FREE — the saved run replayed through the fixed code, no API.

## Scoreboard

| metric | before phase 23 | phase-23 regression | after this fix |
|---|---|---|---|
| overall quantity accuracy | 40% | **10%** | **40%** |
| qty accuracy when found | 67% | 11% | 44% |
| measured items (SF/LF) qty_ok | 75% | **0%** | **75%** |
| Exposed Structure | 397,600 (0.5% err) | blank | **397,600 (0.5%)** |
| Sealed Concrete | 397,600 (0.5% err) | **0.15 SF** | **397,600 (0.5%)** |
| Internal Tilt up walls | 106,998 (1.3% err) | 142,661 (31.6% err) | **106,997 (1.3%)** |

The baseline is **restored, not exceeded**. Nothing here was tuned to golden — no threshold, name or
constant was chosen by watching a score move. Where a fix happened to recover a golden item, that is
evidence the contract was wrong, not the target.

---

## D1 — `one_area_one_item` arbitration had no declared-sharing exception

**Committed:** `fix(fusion): one-area-one-item arbitrates PER BUILDING LAYER, not per region`

### What broke

INV-00 §4 asked for an arbitration rule *with* an exception:

> a measured region may back at most one line item **unless the plan states that two finishes
> genuinely occupy the same area (floor finish + slab, say)**, and any such sharing must be recorded
> as deliberate rather than emergent.

Plan 23-13 shipped the rule. The exception was written into the code as a `shared_area="declared"`
flag the arbitration READ — and which **nothing in `src/` ever WROTE**. `grep` confirms the only
writers were the arbitration's own outputs. So every producer emitted undeclared rows, and every row
after the first was suppressed.

The live run's own audit record, verbatim:

```json
{"source":"arbitration","answer":"Sealed Concrete","reason":"one_area_one_item",
 "quantity":397600.0,"detail":"backed by the same measured region (footprint) as
 'Concrete Pad', and the sharing is not declared — a measured region backs at most
 one line item"}
```

…and the same for `Exposed Structure`, `Canopy` and `Building Footprint`. **Sealed Concrete and
Exposed Structure are golden items** (395,673 SF each, 0.5% error before phase 23). The survivor,
`Concrete Pad`, is not in golden at all — it won only by being emitted first out of vocabulary
iteration order.

Cost: roughly **-30 accuracy points**, the single largest contributor.

### The corrected contract

> A measured region backs at most one line item **PER BUILDING LAYER**.

A shell warehouse's footprint genuinely carries the structural slab, the sealed-concrete finish
troweled onto it, and the exposed roof structure above. Those are three distinct layers occupying one
plan area — which is not the same thing as three copies of one quantity.

**Naming a layer IS the declaration.** It is a statement about what the object *is*, made before any
quantity exists, so the sharing can never be emergent — which is exactly what INV-00 §4 demanded.
An object that names no layer inherited the region only because its measure basis is area-shaped, and
is still suppressed with a reason:

| object | layer | outcome |
|---|---|---|
| Concrete Pad | `slab` | published |
| Sealed Concrete | `floor_finish` | published |
| Exposed Structure | `roof_structure` | published |
| Canopy | — (a discrete element with its own extent) | suppressed, audited |
| Vapor Barrier | — (part of the slab assembly) | suppressed, audited |
| Building Footprint | — (the region itself, not a thing built in it) | suppressed, audited |

Winner selection was fixed at the same time: the anchor is now chosen by **naming authority**
(`_share_rank`) instead of emission order, so an estimator-standard library name outranks a learned
verbatim string and `Concrete Pad` can no longer beat `Sealed Concrete` by arriving first.

### Tests corrected (both made STRICTER, never weakened)

- `test_on_the_real_crow_bundle_the_footprint_backs_one_item_per_layer` — asserted exactly ONE
  survivor and 5 suppressions. Now names all three survivors, asserts one item per layer with no
  layer claimed twice, and names all three suppressions.
- the `test_fuse_wall_area_*` footprint block — asserted that exactly one of Sealed Concrete /
  Exposed Structure survives. Now asserts BOTH survive, carry their `building_layer`, and are marked
  `shared_area="deliberate"`.

---

## D2 — a `library` fallback published an unflagged near-zero

**Committed:** `fix(aggregator): a degenerate library-named reading publishes a BLANK, not a number`

### What broke

```
Sealed Concrete   0.15 SF  conf=medium  needs_review=False  src=library
Concrete Curb     0.05 LF  conf=medium  needs_review=False  src=library
Pipe Handrail     0.02 LF  conf=medium  needs_review=False  src=library
```

Tracing each back through `raw_line_items` shows all three came from the same place — a printed
**DETAIL DIMENSION**, not a quantity:

| published row | the reading it actually was |
|---|---|
| Sealed Concrete 0.15 SF | `"TAPERED CONCRETE SLAB SEE STRUCTURAL"`, value `12`, unit `in` |
| Concrete Curb 0.05 LF | `4"-0"` curb width, value `4`, unit `in` |
| Pipe Handrail 0.02 LF | `1 1/2" O.D. HANDRAIL @ CONC. SLAB`, value `1.5`, unit `in` |

The dimension was pushed through the slab-volume calculator as though it were an area
(`12 sf × 4" / (12 × 27) = 0.15 cy`), the cubic yards were published under an SF/LF unit, and the
library alias table renamed the detail annotation into an estimator-standard object.

The 0.15 SF row is **strictly worse than a blank**: it is unflagged, AND it occupied the
`Sealed Concrete` row that the real 397,600 SF measurement would have filled.

### The corrected contract

> A library-named reading too small to be a real measured building quantity publishes **no number**.
> `quantity=None` + `NOT MEASURED` beats a fabricated small number.

"Too small" is a unit-dignity floor, not a fitted threshold: a building quantity in SF/LF/SY/CY/CF
below **one whole unit** is not a small measurement, it is a mis-scaled or mis-typed one. No drawing
carries 0.15 square feet of floor finish. Counts (EA) are deliberately excluded — a count is counted,
not dimensioned, and a genuinely measured zero stays a zero.

**Dropping the number is only half the contract.** An object whose sole evidence was a degenerate
reading still gets a ROW, saying "not measured" — otherwise the fix would trade a fabricated 0.15 SF
for a silent deletion, and INV-08's whole point is that a deletion and a zero read identically to a
client. Where a real measurement of the same object DID land, the bucket keeps its quantity and
carries a note that the degenerate reading was dropped rather than summed into it.

### Scope correction made during the work

The brief's phrasing ("a library-sourced fallback must NEVER publish a quantity at
`needs_review=False`") was first implemented as a blanket flag on every library-named row. That broke
two existing tests which encode a deliberate and correct contract — under the plans-only mandate the
deterministic component library is *the authoritative naming source that replaces the manifest*, not
a hypothesis, so a library-named measurement is `MEASURED`. The blanket flag was reverted rather than
weakening those tests. The brief's own stated remedy — *"prefer `quantity=None` + NOT MEASURED over a
fabricated small number"* — is what shipped, and it answers the "unflagged" complaint completely: the
offending rows now carry `needs_review=True` **and** no number. `Pipe Guardrail 46.2 LF`, a real
library-named measurement, was never cited as a defect and still publishes.

---

## D3 — D-11 violated: the elevation cross-check published a quantity

**Committed:** `fix(pipeline): the elevation datum ladder cross-checks the wall height, never publishes it`

### What broke

The run's own `coverage_warnings` promises:

> `[A-201] elevation cross-check: silhouette sum 133478 SF vs the independent perimeter x datum-height
> route 2972.0 LF x 48.00 ft = 142656 SF — agreement within 6.4%. **The second route is a cross-check
> only and publishes no quantity (D-11)**`

And the summary published:

> `Tilt Up Wall = 142,661.0 SF` — which is `2,972 × 48 + 5`, i.e. **exactly the perimeter × datum-height
> product the note says it will not publish**, scored at 31.6% error.

The leak was not in the elevation binder, which behaves correctly. Plan 23-14 added the elevation
datum span as **Tier 0** of `_resolve_project_wall_height`, authoritative over every plan callout, on
this argument recorded in its docstring:

> *"Crow's T/ PANEL ladder is the authoritative wall height; the 36' CLEAR callout is an interior
> clearance that understates the panels by 20%"*

The live run falsified it. The datum height simply **left the elevation route through the height
resolver and multiplied the measured perimeter somewhere else**, reconstituting the forbidden
product under a different function's name.

| route | value | error vs golden 108,443 SF |
|---|---|---|
| perimeter × plan callout (36' CLEAR) | 106,992 SF | **1.3%** |
| perimeter × datum ladder (48 ft) | 142,656 SF | 31.6% |

### The corrected contract

> A second measurement route **cross-checks** the first; it does not replace it.

The datum span now sits **below** the plan's own stated height and above only the blind default.
Where the plan states a height, that statement stands and the ladder is reduced to a note that flags
disagreement (`_wall_height_cross_check_note`, ±10% tolerance). Where the plan states nothing there is
no first route to displace and no reconciliation to fabricate, so a measured ladder still beats a
guessed 30 ft — 23-14's genuine contribution is kept.

On Crow the note now reads:

> *wall-height cross-check: the published 36.00 ft (plan) DISAGREES with the elevation datum ladder's
> 48.00 ft by 33% — BOTH are flagged, neither is preferred, and the ladder publishes no height (D-11).*

### Test corrected

`test_a_datum_span_beats_every_keyword_tier` encoded the defective precedence directly. It is now
`test_the_plans_own_stated_height_outranks_the_datum_ladder`, with the falsifying evidence in the
section comment, plus four new tests pinning that the ladder flags agreement and disagreement and
publishes nothing.

---

## D4 — Crow's main floor plan was never enumerated as a drawing

**Committed:** `fix(room_fill): read a drawing title in either convention, coded or not`

### What broke

A-101 reported `plan_titles: 0`, `drawings_measured: 0` and the coverage note *"no measurable plan
drawing on this sheet"* — on the sheet that IS the floor plan. Only the four 1½"=1'-0" detail
viewports were enumerated, all correctly excluded as off-scale.

`PLAN_TITLE_RE` matched only `"<NAME> - <AR|RCP|FF|EM|FC> PLAN"` — one drawing office's house style,
generalised into a universal. Crow titles its main 1"=40' drawing `1 OVERALL FLOOR PLAN`. This is the
exact mirror of the Moxy title-block defect: a convention read as a law.

### The fix, and its honest boundary

`plan_title_of` now reads both conventions. The uncoded form is **anchored to the whole line**, which
is what keeps it honest — a general note (`"...SEE ENLARGED PLANS AND ROOF PLAN."`) contains a kind
word and "PLAN" but is a sentence, not a title, and cannot pass.

```
before:  page 0 {'plan_titles': 0, 'printed_scales': 5, 'viewports': 5}
after:   page 0 {'plan_titles': 1, 'printed_scales': 5, 'viewports': 5}
```

**The enumeration fix alone would have introduced a NEW double-count**, caught before shipping:
once the drawing is enumerated, `Sealed Concrete` is measured BOTH as the 397,600 SF footprint and as
a 1,716.7 SF enclosed sub-region of that same drawing, and the aggregator would have summed them to
399,316.7 SF. So a second arbitration rule shipped with it:

> The same named object measured on two different regions of one sheet is two **ROUTES** to one
> quantity, not two quantities.

Only the case with a principle behind it is decided: a whole-building plane bound to the measured
**footprint** outranks a fill-derived measurement of the same object, because the footprint IS that
object's extent — `_fuse_project_area_items` exists precisely because these planes *"fell back to ~6
SF room slivers without a footprint binding"*. Where no footprint row is involved, nothing is
suppressed; a guessed precedence would be worse than a duplicate an estimator can see.

**What is NOT fixed** is logged as **DEF-23-R1** in `deferred-items.md` with evidence: the drawing is
now enumerated and measured at its correct 1"=40' scale, but the enclosed-region fill returns
1,716.7 SF rather than the building's 397,600 SF, because the warehouse outline is not a closed path
in this sheet's vector layer. That is a measurement-engine change, not a title-recognition one, and
forcing it would be fitting a fill until one number agreed. The fill is flagged and cannot
double-count, so it is safe to ship as-is.

### Test corrected

`test_bobs_real_cover_sheet_stays_skipped` asserted `page0["titles"] == 0`. Bob's page 0 is a sheet
INDEX listing `REFLECTED CEILING PLAN`, `ROOF PLAN`, `DEMOLITION PLAN` and more — entries pointing at
drawings on OTHER sheets, which the broadened pattern now correctly recognises as title CANDIDATES.
The assertion was reading zero only because the pattern was blind to Bob's naming style, and that
blindness was the D4 defect itself.

It now asserts the same invariant its Moxy sibling has always asserted —
`sum(measurable_signal.values()) == 0`, the scale-gated signal. **This is stricter, not weaker:** it
covers titles, scales, viewports and schedules together instead of one raw candidate count, and it
holds whatever house style a set prints. Verified independently: Bob's page 0 gated signal is
`{'plan_titles': 0, 'printed_scales': 0, 'viewports': 0, 'schedules': 0}` — unchanged, still skipped,
still `not_applicable`, still not overruled.

---

## Verification (all FREE — no API key touched, no paid run)

**Replay of the saved run through the fixed code.** Every corrected number is produced by *calling*
the fixed function, never typed in by hand:

- the four `one_area_one_item` rejections were fed back into the real `_arbitrate_one_area_one_item`
  together with the survivor — it kept Concrete Pad (`slab`), Sealed Concrete (`floor_finish`) and
  Exposed Structure (`roof_structure`), and rejected Canopy and Building Footprint;
- the three degenerate readings were fed back into the real `aggregate_takeoff` — all three came back
  `qty=—  NOT MEASURED  needs_review=True`;
- the tilt-up wall was recomputed as the measured perimeter × the height the real
  `_resolve_project_wall_height` returns for Crow's real plan text (36.00 ft, source `plan`);
- the D4 double-count was asserted suppressed on the real Crow bundle.

Re-scored result:

```
Overall quantity accuracy: 40%   Name/found rate: 90%   Qty acc when found: 44%
  Counts (EA)   n= 6  found=83%  qty_ok=17%
  Measured(SF/LF) n= 4  found=100%  qty_ok=75%

PASS      Exposed Structure                 395,673.42    397,600.00     0.5  measured
PASS      Internal Tilt up walls≈Tilt Up Wall    108,442.66    106,997.00     1.3  measured
PASS      Sealed Concrete                   395,673.42    397,600.00     0.5  measured
PASS      Mobilization                            1.00          1.00     0.0  count
```

The remaining failures (Bollards, CMU Wall, Columns, Ladder, Lift, Stairs) are the **count-side**
naming problem INV-00 §3 already attributes to Phase 24/25, untouched here by design.

**Offline gate.** Full suite green; `tests/test_phase23_acceptance.py` and
`tests/test_four_set_coverage.py` both green.

---

## Note on commit sequencing

D1 was committed after its own full-suite run. D2, D3 and D4 were implemented with targeted module
runs each, then verified together by one full-suite run before being committed as three separate,
atomically-scoped commits (they touch disjoint modules: `aggregator.py`; `takeoff_pipeline.py`;
`room_fill.py` + the `fusion.py` cross-region rule). A per-commit full suite costs ~46 minutes; this
sequencing was a deliberate, recorded trade rather than an omission.

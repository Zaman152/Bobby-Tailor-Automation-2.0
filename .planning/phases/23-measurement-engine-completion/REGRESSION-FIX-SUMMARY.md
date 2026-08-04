---
phase: 23
type: regression-fix
subsystem: fusion / aggregation / measurement
tags: [regression, arbitration, building-layers, D-11, library-fallback, plan-titles, INV-00, SP-9,
       cost-telemetry, budget-truncation, unit-class, provenance]
evidence-run: output/VisionOnly_P23V_Crow_20260804_141952
evidence-run-2: output/VisionOnly_P23V2_Crow_20260804_181352
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

---
---

# Round 2 — Crow $0.599 validation run (evidence: `output/VisionOnly_P23V2_Crow_20260804_181352`)

A second paid plans-only Crow run, taken after the Round 1 fixes above, exposed **four further
defects**. None is a scoring regression; all four are *honesty* defects — the report told the user
things that were not true about what the run cost, what it covered, and where its numbers came from.
All four are fixed, one commit each. **Every verification below is FREE**: the saved run re-read, and
its own recorded values replayed through the fixed functions. No API key was touched.

| defect | what the report said | what was true |
|---|---|---|
| **C1** | `api_usage.total_cost_usd = $0.1766` | the guard had spent **$0.598807** (3.4x) |
| **C2** | `coverage_pct_pages: 100.0`, both truncated sheets `"measured"` | the budget exhausted mid-run and A-401/A-601 skipped their remaining passes |
| **C3** | `Tilt Up Wall 5.0 SF`, `confidence: high`, `needs_review: false` | the object measures **106,992 SF**; the 5 was a count of panel symbols |
| **C4** | `items_human_input: 5` | **no manifest, no human input file** existed on this run |

Nothing here was tuned to golden. C3's success criterion is *"the suppressed 106,992 SF candidate is
reinstated when its superseder dies"*, verified by replaying the saved rejection records through the
real fixed function — not by watching a number move toward 108,443.

---

## C1 — cost telemetry under-reported the run by 3.4x

**Committed:** `fix(23-regression): report the guard's actual spend, not the sum of sheet stamps`

### What broke

The same run, two numbers, from one artifact:

```json
"api_usage": { "total_cost_usd": 0.1766, ... }
"budget":    { "cap_usd": 0.6, "spent_usd": 0.598807, "exhausted": false }
```

`reporter.py:101` summed only the per-sheet `_cost_usd` stamps. That sum cannot be complete, for two
structural reasons:

1. **The project-level passes belong to no sheet.** The naming-convention and object-vocabulary reads
   run ONCE for the whole set, before the per-sheet loop (`run_project` → `_build_naming_conventions`),
   and charge the run `BudgetGuard`. No per-sheet stamp can ever carry them — **$0.422162 of this run,
   70% of its cost, was structurally invisible.**
2. **Sheets 2-4 stamped `$0.0` with an empty `_model_used`.** A sheet whose merged dict never inherits
   the analyzer's usage stamp reads free.

This is load-bearing: every cost estimate the app shows and every budget the user sets is downstream
of this number.

### The corrected contract

> `api_usage.total_cost_usd` **is** the BudgetGuard's ledger. The guard is the only complete record —
> it is the thing that actually refused the last charge.

The split is **published, not fabricated**: `sheet_attributed_cost_usd` is what sheets stamped, and the
entire remainder goes to ONE honest `project_level_cost_usd` bucket. No per-sheet ratio split is
invented. The remainder is signed on purpose — a negative value would mean sheets stamped more than
the guard accepted, a real discrepancy that must surface rather than be clamped away. Rounding moved
4dp → 6dp to match the guard's own precision; at 4dp the equality was already off by $0.000407.

A run with no guard (pre-21, the scraper path) still uses the per-sheet sum — unchanged.

### Verification (free)

```
sheet-attributed 0.176645   guard 0.598807   project_level 0.422162
old reported     0.1766  ->  under-report factor 3.39
```

Pinned by `test_reported_total_cost_equals_budget_guard_spend`, which replays the exact Crow shape
(sheet 1 at $0.176645, sheets 2-4 at $0, guard at $0.598807) and asserts
`total_cost_usd == budget.spent_usd`.

---

## C2 — budget truncation was silent

**Committed:** `fix(23-regression): make budget truncation loud — a cut-short run is not complete`

### What broke

The guard exhausted mid-run and A-401/A-601 skipped their remaining passes. The report said nothing:
the phrase **"budget exhausted" occurs 0 times** anywhere in `takeoff.json`, both truncated rows read
`"disposition": "measured"`, and `coverage_pct_pages` read **100.0**. A silent coverage loss —
precisely the class phase 23 abolished everywhere else.

Two independent root causes:

**1. `exhausted` answers the wrong question.** It asks whether budget *remains*. Crow finished with
**$0.0012 of its $0.60 cap unspent**, so `exhausted` was `false` — while the guard had refused a
~$0.21 charge and stopped scheduled work.

```
BudgetGuard(0.6); charge(0.598807); charge(0.21) -> BudgetExceeded
  exhausted       False      <- budget remains
  refused_charges 1
  truncated       True       <- ...and work was stopped anyway
```

`BudgetGuard` now counts refusals and exposes `truncated`. `exhausted` keeps its old meaning verbatim;
nothing was renamed.

**2. `run_sheet`'s `_budget_exhausted` flag died on the sheet dict.** It never reached the coverage
ledger, so the row kept its `measured` default. `_record_sheet_coverage` now propagates it.

### The corrected contract

> A run that stopped early must never present as complete.

- New sheet disposition **`measured_budget_truncated`**. It earns its own value because its gap has a
  different *cause* and a different *remedy* from `MEASURED_PARTIAL`: a partial is explained by
  something on the page (an off-scale viewport, a drawing with no printed scale) and never closes; a
  truncation is explained by the cap and closes by raising it and re-running.
- `SheetCoverage.budget_truncated` is a separate field, so the fact survives when a stronger
  disposition (`ERRORED`, a skip) outranks it.
- Truncated sheets are **excluded from `sheets_measured`**, so `coverage_pct_pages` can no longer read
  100% on a run that stopped early.
- The ledger raises a loud escalation naming the pages, and it **leads** `coverage_warnings` because it
  invalidates the completeness of everything after it. It is derived from the *guard*, not from any
  sheet, so a truncation taken on a project-level pass — which leaves no ledger row — is still loud.
- `summary.txt` gains `!! BUDGET EXHAUSTED — THIS RUN IS INCOMPLETE` under API USAGE and a
  `CUT SHORT (budget spent)` line under COVERAGE. The Excel **About** sheet gains a `RUN INCOMPLETE`
  fact, since that workbook is what a client actually bids from.

### Tests corrected (both made STRICTER)

- `test_seven_sheet_dispositions_are_distinct` → `test_every_sheet_disposition_is_distinct`: asserts
  eight AND that the list equals `SHEET_DISPOSITIONS`.
- `test_every_page_is_accounted_for_in_exactly_one_disposition` (the four-set gate) now includes
  `sheets_budget_truncated` in the sum. **Without that term the accounting invariant would silently
  lose truncated pages — the exact shape of the defect the new disposition exists to prevent.**

### Verification (free)

An end-to-end `run_project` on a stubbed analyzer whose second charge blows the cap: the ledger row
lands `measured_budget_truncated` with a reason, `sheets_measured` drops to 0, `coverage_pct_pages`
goes 100% → **0.0%**, and both strings reach `summary.txt`.

---

## C3 — a two-stage rejection cascade published a confident wrong number

**Committed:** `fix(23-regression): undo a supersession whose superseder dies; never publish a number
in the wrong unit class`

The worst failure class in the run: **the right answer was in the audit trail the whole time.**

### What broke

From the saved run's own `fusion_rejected`, verbatim:

```json
{"candidate_id":"WALL-TC1","source":"wall_classes","answer":"Tilt Up Wall",
 "reason":"superseded_by_room_fill","quantity":106992.0,"unit":"SF"}

{"candidate_id":"FILL-2","source":"arbitration","answer":"Tilt Up Wall",
 "reason":"one_area_one_item","quantity":31104.0,"unit":"SF",
 "detail":"backed by the same measured region (fill:FILL-2) as 'Concrete Pad' ..."}
```

Stage 1 suppressed the 106,992 SF thickness-class estimate **because FILL-2 was about to publish the
same object from a measured region**. Stage 2 then killed FILL-2. Both died, nothing named
"Tilt Up Wall" was left — so a symbol **count of five tilt-up panels** inherited the name and shipped:

```
Tilt Up Wall  5.0 SF   item_type: concrete_slab  formula: "count"
                       confidence: high   needs_review: false
```

Golden asks 108,443 SF; the suppressed candidate is **1.3%** from it.

### (a) A supersession whose superseder dies is not a supersession

Stage 1 was **correct at the time**. Its correctness was *conditional* on FILL-2 surviving, and that
condition was never re-checked.

`_suppress_superseded_wall_items` now returns its `(superseded, superseders, rejection_record)`
triples — keyed on the superseder's **identity**, not its name — and a new
`_reinstate_orphaned_supersessions` runs after arbitration. If no superseder survived, the original is
restored and **its rejection record is withdrawn from the audit trail**; the trail must not claim a
suppression that was undone.

Two guards stop this recreating the double-count the supersession existed to prevent:

- the superseder must actually be gone (identity, not name);
- **nothing else of that name may survive** — if another row publishes the object, the original stays
  suppressed.

A reinstated row is **flagged**, and its reason names the disagreeing route's number. It is restored
after two independent arbitration decisions fired on it, and the two routes differed by 3.4x; an
estimator is owed the magnitude *and* that history.

### (b) A number may not publish in a unit of a different measurement class

Both directions shipped on the same run:

| published | what it actually was |
|---|---|
| `Tilt Up Wall 5.0 SF` | a **count** of five panels, rendered as an **area** |
| `LED Wall Pack 34,214 EA` (`formula: "count x 1.1"`) | a 31,104 SF wall **area**, rendered as a **count** |

There is no factor between "how many" and "how much", so such a number means nothing. New module
`src/bobbytailor/pipeline/units.py` holds **one** definition of what a unit measures — *two*
definitions of this rule is how the two halves of this defect drifted apart — shared by two
enforcement points:

- **fusion `_withhold_unit_class_violations`** (final publication gate): a component whose measure
  BASIS conflicts with its bound UNIT has its quantity withheld and the withheld value recorded. The
  row **survives**, flagged. A blank with a reason is honest; a deletion is not.
- **aggregator**: canonicalising a NAME may not silently reclassify its UNIT. Naming precedence let the
  library's `SF` overwrite the reading's own `EA` — which is *literally* how `5.0 SF` was produced. A
  class-crossing canonicalisation now withholds the number and materialises an explicit BLANK row
  (`unit_class_conflict_unmeasured`), mirroring the existing degenerate-reading contract. Where a real
  same-class measurement of the object landed, that keeps its quantity and carries a note that the
  conflicting reading was **not summed** into it.

Both fire only when **both** classes are known and differ. An unrecognised unit or unmapped basis is
left alone: a wrong guess here blanks a *good* quantity, which is worse than the defect.

### Test corrected (made STRICTER)

`test_aggregate_uses_manifest_name_and_unit_verbatim` asserted that a `0.15 CY` reading — a printed
detail dimension pushed through the slab-**volume** calculator, the same family Round 1's D2
documented — publishes as a `Bollards` row sourced `"manifest"`. That is 0.15 cubic yards of concrete
presented as a count of bollards: the same defect one class over. It now uses a COUNT reading (so the
manifest's naming authority is still pinned) and a new sibling,
`test_a_manifest_unit_may_not_reclassify_the_measurement`, asserts the volume case publishes a BLANK
while keeping the manifest's name and unit.

### Verification (free — the saved records through the real functions)

The three-row cascade, rebuilt from the saved rejection records' own numbers and run through
`_suppress_superseded_wall_items` → `_arbitrate_one_area_one_item` →
`_reinstate_orphaned_supersessions` in `fuse_sheet`'s exact order:

- exactly one `Tilt Up Wall` row publishes, at **106,992.0 SF**, and it is the *original* object;
- its `superseded_by_room_fill` record is gone from `fusion_rejected`;
- the superseder's own `one_area_one_item` rejection stands — it really was arbitrated away;
- with the anchor removed (a VALID supersession) the room-fill row publishes instead and the estimate
  stays suppressed;
- with another same-named row surviving, **no reinstatement happens** — no double count.

And the combined end state through the real `aggregate_takeoff`:

```
PUBLISHED: 106992.0 SF | NEEDS REVIEW | needs_review=True
  - a reading in a DIFFERENT measurement class was NOT summed into this quantity
    ('tilt-up concrete panel' read 5.0 LF via formula 'count' and this row publishes in SF
     — linear vs area)
  - reinstated: ...
```

---

## C4 — `HUMAN INPUT` on a run with no human input

**Committed:** `fix(23-regression): HUMAN INPUT is earned — stop labelling machine reads human`

### What broke

`coverage.items_human_input: 5`, on a plans-only run with **no manifest and no human input file of any
kind**:

| row | source | provenance |
|---|---|---|
| Doors - Steel 70 EA | `plan_schedule_legend` | HUMAN INPUT |
| Doors - Hollow Metal 29 EA | `plan_schedule_legend` | HUMAN INPUT |
| Door Frames - Hollow Metal 29 EA | `plan_schedule_legend` | HUMAN INPUT |
| Doors - Aluminum 6 EA | `plan_schedule_legend` | HUMAN INPUT |
| Mobilization 1 EA | (app-injected convention) | HUMAN INPUT |

The four door rows were parsed **by the app** off the door schedule printed on the plans. The fifth is
the app's own injected convention. All five presented app-generated data as human-vouched — which
inverts the one distinction this vocabulary exists to draw, and inflates apparent trust in exactly the
rows a reviewer would otherwise check.

Root cause: `_row_status` returned `HUMAN INPUT` for **any** row sourced `plan_schedule_legend`. But
`takeoff_legend` has two very different producers and the tag could not tell them apart:

| producer | origin |
|---|---|
| `devtools/companion_takeoff.py` | an estimator's own take-off, from a **human input file** |
| `deterministic/schedule_extraction.py` (Crow's doors), `plan_deterministic_legends.py`, `rooms.py`, `footprint_takeoff.py`, vision tables | read off the **plans** |

### The corrected contract

> `HUMAN INPUT` means a human handed us this number, in a file. It is **earned**, never defaulted into.

Legends now declare their origin: `legend_origin: "human_input"` on the companion-take-off ingest,
`"plan_parsed"` on every plan-read constructor. The calculator propagates it onto the emitted item and
the aggregator onto the bucket. A **missing** marker defaults to `plan_parsed` — fail-closed. The class
is not deleted: a companion take-off still publishes as `HUMAN INPUT`.

**Mobilization** gets a new status, `ITEM_STANDARD = "STANDARD ITEM"`. Nobody measured it and nobody
supplied it — the app injects it. `NOT MEASURED` would lie in the other direction (its quantity is
real and publishable), so it gets the value that says exactly what it is. `coverage.summary()` gains
`items_standard`; `summary.txt` renders the line only when one exists; the Excel About legend
documents it and sharpens the `MEASURED` / `HUMAN INPUT` wording.

### Test corrected (made STRICTER)

`test_the_legend_row_is_not_flagged_by_the_trace` asserted a legend row with no `legend_origin`
publishes as `HUMAN INPUT` — the very conflation this defect *is*. It now asserts `MEASURED`, and a
new sibling asserts the human-input half of the contract still holds.
`test_every_row_carries_a_provenance_from_the_four_value_vocabulary` was renamed and now also pins
Mobilization's status.

### Verification (free — the saved run's own rows through the real aggregator)

```
BEFORE HUMAN INPUT rows: ['Door Frames - Hollow Metal', 'Doors - Aluminum',
                          'Doors - Hollow Metal', 'Doors - Steel', 'Mobilization']
AFTER  HUMAN INPUT rows: []
  the four door rows -> MEASURED
  Mobilization        -> STANDARD ITEM
```

---

## Verification summary

**Offline gate, run in full before every one of the four commits** (~47 min each):

| after | result |
|---|---|
| baseline | 1870 passed, 1 skipped, 2 deselected |
| C1 | **1873** passed (+3) |
| C2 | **1882** passed (+9) |
| C4 | **1889** passed (+7) |
| C3 | **1944** passed (+55) |

`tests/test_phase23_acceptance.py` and `tests/test_four_set_coverage.py` green throughout (the
four-set gate is invoked by acceptance check 1).

**No paid API was invoked at any point.** No `pytest -m golden`, no `accuracy_gate.sh`, no
`vision_only_benchmark.py`, no `golden_convergence.py`, no `ANTHROPIC_API_KEY`, `.env` never read.
Every verification is either the saved run re-read for free or its own recorded values replayed
through the fixed functions.

### On the score, stated honestly

Re-scoring the saved artifact still reports **30% overall / 33% qty-when-found**, because
**the artifact is unchanged** — the scorer reads the JSON the paid run wrote, not the fixed code. What
these commits change is what the *next* run will produce; that comparison costs money and was
deliberately not made. Claiming an accuracy improvement here would be exactly the kind of unearned
statement C1–C4 are about.

What *is* demonstrated, by calling the fixed functions on the saved run's own recorded values:

- the reported cost equals the guard's spend (C1);
- a truncated run cannot report 100% page coverage (C2);
- the 106,992 SF candidate is reinstated when its superseder dies, and the 5.0 count is withheld
  rather than summed (C3);
- a manifest-free run reports zero `HUMAN INPUT` rows (C4).

### Note on a defect NOT fixed

The scorer output shows `+ SYM-1 … SYM-35` and `+ ROOM-3 … ROOM-6` as EXTRA items — unnamed geometry
clusters published under their candidate IDs. That is the autonomous-naming gap already recorded as
the count-side problem for Phase 24/25, and it is untouched here by design.

# Bobby Tailor — Ground-Truth Report (plans-only autonomous takeoff)

_Generated 2026-07-15 during the accuracy R&D session. Honest state, no spin._

## 1. Real accuracy achieved (Crow Cass, plans-only, manifest-free)

The benchmark runs the **plans PDF only** through the production pipeline, then scores the
output against the human take-off PDF (used solely as the answer key — never fed to the pipeline;
a planted decoy take-off + decoy manifest make the run **fail loudly** if it ever reads them).

| Item | Golden | Pipeline | Status | Why |
|------|--------|----------|--------|-----|
| Doors-HM | 29 | 29 | ✅ EXACT, every run | door type+Count schedule + abbreviation key |
| Door Frames-HM | 29 | 29 | ✅ EXACT, every run | same |
| Sealed Concrete | 395,673 SF | 397,600 | ✅ 0.5%, stable | footprint geometry bound to floor item |
| Mobilization | 1 | 1 | ✅ | default |
| Columns | 132 | detected 136, **not named** | ✗ | cluster found; naming not mined from plan |
| Bollards | 28 | detected ~56, **not named / 0** | ✗ | same |
| CMU Wall | 2,204 SF | wrong class bound | ✗ | wall-class→name mapping missing |
| Internal/Exterior Tilt-up | 108,442 SF | wrong/missing | ✗ | S.C.C.P. int/ext labels not mined |
| Exposed Structure | 395,673 SF | named "Metal Roof Deck" | ✗ | estimator finish term not in plan |
| Guard/Hand Rail | 420/438 LF | ~3–5 LF | ✗ | rail linework not measured |

**Overall quantity accuracy: ~27%** (bounces 13–40% between identical runs due to vision-pass
variance, now being stabilized by ensemble voting). **Foundation is verified correct**: footprint
397,600 SF (0.5% off), wall LF per class matches, 136-column cluster detected, scale read from the
plan's own printed labels. The gap is **naming + binding + reliability**, not measurement.

**Starting point for context:** the very first manifest-free run scored **7%** — proving the prior
"97%" was entirely produced by a hand-authored `manifests/crow_cass.json` (deleted). Everything since
is genuinely autonomous.

## 2. What the system is

A **deterministic-geometry-first + vision-as-labeler** takeoff engine. 844 offline tests.
- `deterministic/` — measures the drawing: `printed_scale` (reads each drawing's scale label),
  `scale_solver` (RANSAC fallback/cross-check), `viewports`, `dimensions`, `walls`, `rooms`,
  `footprint_takeoff`, `symbols` (cluster + count), `tables`/`schedule_extraction`/
  `plan_deterministic_legends` (schedules incl. door type+count), `component_library` (harvests
  names/aliases/abbreviations from plan text).
- `vision/` — labels only (never numbers): `object_vocabulary` (LLM reads the plan, enumerates
  object types + measure basis), `overlay` (Set-of-Mark), `schemas` (candidate-ID enums, no numeric
  fields), `fusion` (binds labels→geometry with provenance ranking), `ensemble` (voting),
  `verify_retry`, `claude_analyzer`.
- `pipeline/` — orchestration: `pdf_analyzer` (entry), `takeoff_pipeline` (per-sheet run_sheet +
  run_project), `calculator`/`aggregator`/`reporter` (quantities → report), `sheet_pass_matrix`
  (model routing).
- `learning/` — SQLite store: capture human corrections → distill → retrieve on future runs.

## 3. Complete PDF-upload workflow

1. **Upload / select** — user uploads a PDF or picks a StackCT plan set → `run_pdf_analysis(pdf, project_name)`.
2. **Plans-only guard** — `resolve_project_manifest(allow_discovery=False)`; no sibling take-off /
   manifest is ever discovered (LOCKED contract, enforced + test-tripwired).
3. **Per-page prep** — render each page, extract title-block + full-page text, classify sheet type
   (floor_plan / elevation / detail / schedule …).
4. **Plan-level harvest (once)** — door schedule (type+Count parser), component library
   (abbreviations HM=Hollow Metal, schedules, keynotes), project vocabulary (LLM object types +
   measure basis, merged with the deterministic library, deterministic authoritative), project wall
   height (from plan clear-height text), learned context (from prior corrections).
5. **Per-sheet `run_sheet`** (vector path):
   - Deterministic bundle: `segment_viewports` → **printed-scale reader** (primary) + RANSAC
     (cross-check) → `resolve_scale_v2` → `extract_dimension_samples` → `extract_walls` +
     `wall_lf_by_class` → `extract_rooms` → `cluster_symbols` (counts) → `footprint_from_page`.
   - Vision passes (semantic-only, **voted N×**): semantic overlay (main-plan region + wall-class
     labels), symbol gallery (in-context Set-of-Mark + repetition counts), all picking from
     candidate IDs / vocabulary labels.
   - `fuse_sheet`: binds each vision label to its geometry candidate by `candidate_id`;
     wall_area→LF×height (SF), floor/roof_area→footprint SF, symbol→count; `merge_with_provenance`
     ranks geometry > text_layer > schedule_table > learned > vision so a number can never be
     overwritten by a lower source.
   - Verify-retry: out-of-band quantities get a bounded targeted-crop question before human review.
6. **Aggregate** — `calculator` + `aggregator` roll per-sheet components into `takeoff_summary`
   (ITEM_NAME_MAP + library alias resolution); unnamed items surface as `needs_review` (flag-don't-guess).
7. **Report** — `reporter.generate_report` → `takeoff.json` (line items, provenance, needs_review,
   api_usage, scale_calibration, fusion_rejected audit), `summary.txt`, screenshots, logs, history.
8. **Learn** — verify/scale/measurement endpoints write corrections to `learning.db` → distill →
   applied automatically on the next run of that project (and similar ones).

## 4. How vision + geometry fusion works (the core idea)

- **Geometry produces every number.** Counts come from symbol-cluster sizes; LF from wall linework;
  SF from closed room/footprint polygons — all at the scale read from the drawing's printed label.
- **Vision produces only semantics.** The structured-output schemas have **zero numeric fields** and
  candidate-ID **enums** — the model can only answer "candidate SYM-1 is a `Column`", never "there
  are 132 columns". This structurally prevents vision hallucination of quantities.
- **Fusion binds them by ID** and enforces a provenance rank so deterministic quantities always win.
- **Ensemble voting** runs the identification passes N× and takes the majority, so labels stop
  flipping between runs.

## 5. Where the gaps are (honest)

1. **Plan-native naming under-mined (biggest, fixable).** The plan's keynotes/notes/details DO name
   Columns, Bollards, S.C.C.P. (tilt-up) interior/exterior, 8" CMU wall, Stairs, Ladder — but the
   extractor isn't mining them, so those clusters stay `SYM-*` and the floor is named "Concrete Pad".
2. **Wall-class → name mapping missing.** Thickness classes (TC1=1714 LF …) aren't mapped to
   tilt-up / CMU by thickness + plan text, so wall SF binds to the wrong class.
3. **Aggregator collapses unnamed `SYM-*` into one `Component` blob** instead of surfacing each as a
   flagged count row (bug).
4. **Rail LF not measured** — rail linework on the ramp isn't picked up.
5. **Reliability variance** — mitigated by voting, not yet eliminated.
6. **Estimator-only finish vocabulary** — "Sealed Concrete", "Exposed Structure" are the estimator's
   words for "concrete slab" / "metal roof deck"; these specific finish terms are **not in the plan**.

## 6. Where human intervention is still needed, and why

- **Only the small residual in gap #6** genuinely needs a human: when the estimator's private finish
  name isn't printed anywhere in the plan, no autonomous read can invent it. **The human corrects it
  once** ("Concrete Pad → Sealed Concrete"); the learning store applies that mapping to every future
  run — so intervention trends to zero with use.
- **Not needed** for: scale (read from the plan's printed label — no calibration), object names that
  the plan does print (columns/bollards/tilt-up/CMU/stairs — being mined now), quantities (geometry),
  or manifests (deleted; the plan is the only input).

## 7. Best solution / revised architecture (incorporating "AI reads the plan's naming conventions")

1. **Deterministically extract ALL plan text** — keynotes, general notes, detail labels,
   abbreviations, schedules, legends, title blocks.
2. **AI naming-convention pass** — feed that text (+ the drawing) to the model, which returns *this
   plan's* naming conventions as a structured library: object → {canonical name, aliases, measure
   basis, thickness/height hints, interior/exterior variant}. Voted for reliability. This generalizes
   to any plan far better than a hardcoded lexicon.
3. **Bind names to geometry** — clusters/wall-classes/rooms get their names from that library;
   ambiguous → flagged, never guessed. Nothing skipped.
4. **Geometry measures; fusion binds; provenance protects; ensemble stabilizes.**
5. **Learning loop** accumulates the estimator's naming/aliases over time → the residual finish-term
   gap closes with use, building a complete cross-project component library.
6. **Record-replay** the real vision responses once so the real pipeline can be iterated offline for
   near-zero credits between paid validation runs.

**Target:** 100% autonomous on any plan for everything the plan itself contains; the learning loop
carries the estimator-specific naming residual to ~100% over a few uses. Validated by re-running on a
second real project (Bob's Discount / Moxy / Chelsea) to confirm generalization.

## 8. Generalization test (2026-07-15) — DECISIVE: the pipeline does NOT yet generalize

Ran the exact same pipeline plans-only on **Bob's Discount** (7-page set) vs its take-off. Result:
**8% overall, only Mobilization passed** (vs Crow's 67% name-found after tuning). The gains on Crow
were partly **Crow-specific fitting**. Three concrete, general failures:

1. **AI naming pass is fragile** — on Bob's it sent ~35k tokens of plan text and the model returned
   `invalid_json`; the voted naming library fell back to a thin deterministic set. The naming schema/
   output needs to be robust (chunking, smaller/stricter schema, retry-on-invalid, or a smaller text
   digest) — not one giant prompt.
2. **No measurable floor plan** — Bob's "plans" set is title + schedules + a civil elevation
   (`C402.4`); no `floor_plan` sheet, so the entire vector-geometry engine (walls/rooms/footprint/
   symbols) never ran. The pipeline assumes a single measurable floor plan (Crow's shape). Real plan
   sets vary: schedule-heavy, civil-heavy, multi-sheet architectural. The engine must handle **all
   sheet compositions**, not just one floor plan.
3. **Schedules skipped / format-specific** — Bob's door schedule format differs from Crow's
   type+Count parser; its schedules were classified "non-takeoff" (FLOORING LEGEND, RCP LEGEND, PAINT
   COLORS) and skipped. Schedule extraction is fitted to Crow's formats.

**Honest conclusion:** the *architecture* (geometry measures, AI reads the plan's naming, fusion
binds, learning accumulates) is validated on Crow, but the *implementation is not general* — it is
tuned to one plan's structure. Reaching "100% on any plan" is a substantial multi-session program:
robust/chunked naming extraction, sheet-composition-agnostic measurement (schedule + civil + multi-
plan, not just one floor plan), per-format schedule parsing, the learning loop, then re-validation
across Crow + Bob's + Moxy + Chelsea. This is the real state; the earlier Crow numbers should NOT be
read as "the app works."

## 9. Opus reader fix + the measurement-engine frontier (2026-07-15)

Routed the once-per-project naming/reading pass to **Opus 4.8**, fed it a **lean distilled digest**
(keynotes/abbreviations/detail labels/schedule headers, ~5–10k chars vs 35k raw), added
retry-on-invalid-JSON + tolerant extraction, and **streamed** the call (a 32k `max_tokens` on Opus
tripped the SDK's ">10 min ⇒ streaming required" guard and killed the pass instantly).

**Result:** the reader now **generalizes** — on Bob's it produced a valid 24-object manifest (Sonnet
had returned invalid JSON), and Bob's **name-found rate rose 8% → 33%** (Doors, Canopy now found).

**But Bob's overall is still ~8%, and this pinpoints the real remaining frontier: the MEASUREMENT
engine is floor-plan-centric.** Bob's golden quantities are Gas Piping 886 LF (~~civil linework~~ —
see the correction below), Exterior Painting CMU 16,219 SF + EIFS 3,053 SF (elevation wall areas),
Lintels 179 LF (structural) — **none measured by the floor-plan walls/rooms/footprint engine.** Crow
is a warehouse (everything on one floor plan); Bob's is a retail fit-out (quantities across
~~civil~~ + elevations + schedules).

**So the naming is now general; the measurement is not.** The next program is a
**sheet-type-aware measurement layer**: ~~civil linework LF (piping/curb/utilities on C-sheets)~~
open-run linear LF on ANY plan sheet (see the correction below), elevation wall-area SF
(painting/EIFS/cladding on elevations), schedule-driven counts per format, in addition to the
floor-plan engine — then the fusion binds the (now-general) names to whichever measurement produced
the number. Plus the learning loop, then re-validate across all 4 plans.
Session API spend to date ≈ $16. Context is very large — continue in a FRESH session using this doc
+ memories as the plan.

> ### CORRECTION (2026-08-04, phase 23 / plan 23-16, decision D-01) — there is no civil sheet
>
> **The old claim (struck above):** Bob's Gas Piping 886 LF is *civil linework*, and reaching it
> needs a *civil-sheet* engine reading *piping/curb/utilities on C-sheets*. The evidence offered
> for it was a `C402.4` sheet reference found in the set.
>
> **The falsifying evidence.** The uploaded Bob's plan set has **seven sheets and no C-sheet and no
> P-sheet at all**, read straight off the per-page title blocks:
>
> | page | sheet | title |
> |---|---|---|
> | 0 | CS-1 | COVER SHEET |
> | 1 | A1.1 | FLOOR FINISH PLAN |
> | 2 | A2.0 | REFLECTED CEILING PLAN |
> | 3 | A3.0 | **ROOF PLAN** ← the gas run is drawn here |
> | 4 | A4.0 | FRONT ELEVATION DEMOLITION / ELEVATIONS |
> | 5 | A8.1 | door + hardware schedules |
> | 6 | A8.3 | STANDARD DETAILS |
>
> The `C402.4` cited as proof of a civil sheet is an **IECC energy-code table reference inside a
> note on A4.0**, matched by a sheet-number regex. The take-off's own legend puts `Gas Piping
> 886.77 LF` on **page 0 of the marked-up set, which is A3.0** — a `roof_plan`, a sheet type
> already inside `_PLAN_SHEET_TYPES`. The Chelsea set (32 pages) likewise contains no civil sheet.
> The run itself is an **annotated CAD linetype**: the line is broken at a regular ~33.7 pt pitch
> and each gap carries the literal word `GAS` drawn as 39 SHX micro-strokes.
>
> **Citation:** `INV-04-civil-linework.md` §1 (the seven-sheet listing and the energy-code table
> reference), §2 (the linetype), §3 (the selection recipe).
>
> **The delivered contract.** No civil-sheet engine was built and none is needed. The frontier was
> **open-run linear measurement on any plan sheet**, and that is what shipped:
> `deterministic/open_runs.py` chains open polylines, `extract_linetype_runs` finds the run by its
> repeating line-breaking glyph mark (160 of 160 detected marks within 12 pt of the polyline the
> estimator actually traced, and **zero** runs across all 76 pages of Crow + Chelsea + Moxy), and
> `run_scale_fpp` measures it at its own drawing's printed 3/32" = 1'-0". Bob's gas main reaches a
> line item at **877.6 LF** inside the ±5% band, named `Gas Piping` from the sheet's own general
> note. (Plans 23-10, 23-12, 23-15.)

## 10. DECISIVE offline finding (2026-07-15) — "136 Columns" was COINCIDENTAL; no real column cluster

Iterated the **deterministic geometry offline for FREE** (new tools `scripts/geom_probe.py`,
`scripts/fusion_probe.py` — run just `_deterministic_bundle`, zero API) on the real Crow floor plan
(page 1, fpp 0.555 / 40 ft-per-in). Rescored the two saved live runs (A2 $0.40, MAN $0.34) against
the take-off — they are the SAME plan and expose the variance directly:

| Item | Golden | run A2 | run MAN |
|------|--------|--------|---------|
| Bollards | 28 | **0** | **0** |
| CMU Wall | 2,204 SF | **8** | **11,294** |
| Columns | 132 | **MISSING** | 136 |
| Internal Tilt-up | 108,442 | 106,998 ✓ | **0** |
| Stairs | 10 | MISSING | 3 |
| Exposed Structure / Sealed Concrete / Doors-HM / Frames-HM / Mobilization | — | ✓ | ✓ |

**Only ~5 items are genuinely stable** (footprint-area, schedule, default). Everything vision-bound
flips. Root causes, now proven from the raw geometry (not inferred):

1. **The "136 columns" is NOT columns.** The 136-count symbol cluster (SYM-3) has its 136 instances
   **all at Y=1863.2 — a single horizontal row** spanning the plan width. So do SYM-2 (204), SYM-4
   (136), SYM-6/8 (68), SYM-10 (44)… **every high-count small-marker group has yspan=0**: they are
   **dimension-tick / grid-bubble rows along the bottom**, not 2-D object arrays. A 2-D search for a
   small-marker lattice (both spans > 300 pt, count 30–250) returns **zero** candidates. The real 132
   columns are simply **not isolated as a cluster** by the shape-signature clusterer. The prior
   session's "136-column cluster detected" (and the MAN run's Columns=136) was a **coincidental count
   match** to golden 132 — dimension ticks that happened to number ~136. `_is_regular_grid` correctly
   returns False on all of them; `deterministic_symbol_name` returns None for every group. **Columns
   detection is unsolved.**
2. **Naming variance is real and separate.** Same geometry, the cluster's NAME flips: "Structural
   Column" (A2, from vision vocab, kept verbatim) vs "Columns-H-35'" (MAN, from the naming library).
   The benchmark's strict tokenizer matches golden "Columns-H-35'" to "Columns" (subset) but NOT to
   "Structural Column" → A2 scores MISSING. The library/vocab **verbatim path bypasses ITEM_NAME_MAP
   normalization**, so synonyms never converge.
3. **Bollards=0** is a vocabulary candidate "Bollards" that never bound to any cluster (defaulted 0);
   the perimeter-jamb binding needs the AI naming pass to emit the hint AND a perimeter ring — neither
   fires reliably. No real bollard detection.
4. **CMU / tilt-up wall-class binding is vision-primary** (`_fuse_wall_classes` line ~1311): WHICH
   thickness class (of 18 TC classes: TC1 6841 LF @ 4", … TC3 1120 @ 15.2", TC16 63 @ 16") is "CMU"
   vs "tilt-up" is chosen by the stochastic label → 8 ↔ 11,294 flip.

**Why this matters:** the honest measurable accuracy is ~5–6 solid items (footprint SF, schedule
counts, tilt-up-when-perimeter-binds, mobilization). Column/bollard/CMU "hits" are coincidental or
unstable. **Building a bespoke column/bollard detector cannot be validated offline** — there is no
ground-truth object-position data, only the golden COUNT, so tuning to hit 132 just reproduces the
coincidence trap. Genuine progress on these requires **paid live validation runs (user-authorized
only — never autonomous)** and/or the **human-correction learning loop**. Offline-only, the safe
correctness move is to stop emitting coincidental object rows (flag, don't guess) — but that removes
the coincidental Columns hit and lowers the naive metric, so it is a decision for the user, not a
silent change. Reaching "100% on any plan" remains the multi-session capability program of §8–§9.
The free offline geometry-iteration harness now exists (`scripts/geom_probe.py`,
`scripts/fusion_probe.py`).

## 11. Scale R&D (2026-07-16) — two real, systemic scale bugs found + fixed

New zero-API tool `scripts/scale_probe.py` reports every page's viewports, each viewport's OWN
printed scale, and where a page carries several. Findings, all verified on the real PDFs:

**11.0 Sheet map correction (important).** Crow's real floor plan is **page 0**
(`OVERALL FLOOR PLAN` @ 1"=40', footprint 397,600 SF / perimeter 2,972 LF — the source of every
passing number). **Page 1 is the ELEVATIONS sheet** (N@40, E@20, S@40, W@20); page 2 is 13
details/sections; page 3 is door jambs/types. §10's probes ran on page 1 — the elevations — so its
symbol analysis described the wrong sheet. **§10's conclusion still holds on page 0**: SYM-1 there
is 136 marks at a single Y (`yspan=0`) — collinear dimension ticks, not a 2-D column grid; no 2-D
small-marker cluster ≈132 exists. Also disproved on real data: the documented "56 marks → 28
bollards" concentric dedup — `_dedup_colocated_count(56) → 56` (multiplicity 1.0), so the 56-mark
2-D cluster is 56 distinct marks and never resolves to golden 28 by that route.

**11.1 Multi-scale pages are the norm, and every page was measured with ONE scale.**
All 4 Crow pages and 4 of 7 Bob's pages carry more than one drawing scale. Quantities are computed
at the single resolved page scale, so any geometry inside an off-scale viewport was measured with
the wrong fpp and emitted as junk take-off rows. **This bites the floor plan itself**: Crow page 0's
four S.C.C.P. details at 1 1/2"=1'-0" are **60× off** against the plan's 1"=40'. A detail is also a
blow-up of an object the plan already shows, so counting it double-counts. **Fixed:**
`_deterministic_bundle` excludes any viewport whose own printed scale disagrees with the resolved
page scale (>5%). Real effect on Crow page 0: symbol groups **48 → 36**, wall classes **15 → 13**,
footprint untouched (397,600 SF).

**11.2 Stacked-fraction scales lose their slash → 144× errors (high severity).**
CAD exports typeset a scale fraction as ONE stacked glyph in its own text span; the PDF text layer
flattens it and the slash vanishes. Real spans from Bob's page 4:
`['SCALE: ', '18', '" = 1\'-0"']` — i.e. `1/8" = 1'-0"` (8.0 ft/in) read as `18" = 1'-0"`
(**0.056**). **Crow writes literal slashes and never trips this, which is exactly why it survived —
it is invisible on the fixture the pipeline was tuned against.** Bob's golden quantities are
elevation areas, so it hit the sheets that matter. **Fixed** in `_paper_inches`: a bare digit-run
that is the concatenation of a standard architectural fraction (18→1/8, 14→1/4, 12→1/2, 34→3/4,
316→3/16 …) maps back to the fraction. Unambiguous — every literal reading ("18 paper inches = 1
foot") is architecturally impossible — and tests pin that 1"=40', 3"=1'-0", 1 1/2"=1'-0" and literal
1/8" are untouched. Bob's page 4: `[0.056, 0.083, 0.2, 0.333, 0.5]` → `[0.2, 0.333, 0.5, 2.0, 8.0]`.

**11.3 Best model on the binding passes.** `(*, semantic)` and `(*, vocabulary)` now route to
`CLAUDE_MODEL_DENSE` (Opus 4.8). The semantic/symbol-gallery pass is what picks WHICH candidate is
Columns/Bollards and WHICH wall class is CMU — the bindings that flip run-to-run. Safe by
construction: those schemas have zero numeric fields and candidate-ID enums, so a better model buys
binding reliability, never a hallucinated quantity.

**11.4 `identify_main_plan_scale` returning None on Bob's is CORRECT, not a bug** — Bob's plans set
genuinely contains no floor plan (titles are all `VENT PIPE DETAIL`, `FRONT ELEVATION NEW`,
`ROOF LADDER SECTION`…). That is the §9 measurement-engine frontier (elevation/civil/schedule
measurement), not a scale defect.

**Still open (needs a user-authorized paid validation run — cannot be validated offline):** real
column/bollard detection, CMU vs tilt-up wall-class disambiguation, rail LF. Do NOT tune these to
the golden COUNT — validate against position/shape, or the coincidence trap of §10 repeats.
Offline suite: **1099 green**.

## 12. MOXY run (2026-07-17) — human-in-the-loop, 40 pages. Honest: **4% (1/24 items)**

First run of the **human-in-the-loop** contract (distinct from the plans-only benchmark): a human
supplies `human_inputs/moxy_knoxville.json` — 24 item names/units/aliases + `scale_ft_per_in: 8.0`
(Moxy prints no text scale except page 2's `1/8" = 1'-0"`) — and the pipeline still produces every
NUMBER. The manifest schema has **no quantity field** (`object_manifest.py`: "The manifest is NOT a
take-off"), so the answer key cannot leak; verified programmatically before the run. NOTE: with a
take-off-derived manifest the **name-found rate (82%) is circular and meaningless** — only the
QUANTITY accuracy is a real measure.

**THE bug this run exposed — `"COVER"` matched `"WALL COVERING"` and silently deleted 27/40 sheets.**
`classify_sheet_type_from_text` tested keywords as bare SUBSTRINGS over full-page text and `_KW_TITLE`
held the bare word `COVER`. `title_sheet` means *skip the sheet entirely, zero API, no geometry* — so
every guestroom floor plan on this hotel (whose primary finish IS wall covering) was thrown away
before measurement, i.e. all 129,521 SF of Gyp Wall. Bob's lost 3 sheets; Crow's page 0 — the
OVERALL FLOOR PLAN every passing number comes from — classifies title_sheet on its page text too and
survives only because its title block says "FLOOR PLAN" and is checked first. Fixed with
whole-word matching (the same flaw made PLAN match PLANT, SECTION match SECTIONAL) + bare
COVER/INDEX trusted only in the title block. Sheets skipped: **Moxy 28→2, Bob's 3→1, Crow 1→0**.

**Honest accuracy after the fix (aggregate AI total vs golden total, the only fair read — Moxy's
golden has duplicate per-room rows):**

| Item | Golden | AI | % |
|------|--------|-----|---|
| Gyp Wall | 129,521 SF | 2,745 | 2.1% |
| Gyp Ceiling | 58,680 SF | 0 | 0% |
| Guestroom-Wall Covering | 27,014 SF | 15 | 0.1% |
| CMU Wall | 6,916 SF | 126 | 1.8% |
| Base / Lintels / WC-1..WC-10 / Exposed Structure | 3,541 LF / 1,530 LF / 7,432 SF / 3,771 SF | 0 | 0% |
| Doors-WD / Door Frame-HM / Doors-HM | 213 / 215 / 10 EA | 0 | 0% |
| Mobilization | 1 | 1 | ✅ (a constant) |

**1 of 24 items within 5% = 4% — and the only pass is the hardcoded Mobilization default.**
The classifier fix is real and necessary (26 sheets recovered; raw numbers rose — Gyp Wall 845→2,745,
Guard Rail 0→140, Stairs 6→10), but it moved a 2% score to 4%: **unblocking the sheets proved the
measurement engine cannot measure this building at all.** Run: 22 sheets contributed, $1.89, 21 min.

## 13. Moxy document study (2026-07-17) — the measurement model, and why 100% is blocked

Read the plans against the take-off page by page (not inferred — read). Findings:

**13.1 The take-off is PER SHEET.** Each take-off page is the same sheet as the plan page with a
"Legend" box overlaid listing what was measured *on that sheet*. Extracted map (all 40):
`ID-411 → Door Frame-HM 2, Doors-WD 2, Guestroom-Wall Covering 366.43, Gyp Ceiling 706.76, Gyp Wall
1,566.65`; `ID-202 → Guard Rail 23.01 LF, Hand Rail 23.50 LF`; `CS-02 → Lift 1, Mobilization 1`; etc.

**13.2 THE MODEL: typical-unit × count.** Sheets ID-407…ID-422 are **prototype guestroom drawings** —
one room per sheet (KING A, KING SUITE B, QQ A, BUNK B, ADA KING RIS…) at 1/4"=1'-0". The estimator's
number is *that one room × how many of that type exist*. `Doors-WD` per sheet **is** the multiplier
(one entry door per room). Dividing golden by it yields per-unit areas of **212–377 SF — textbook
guestrooms**, which independently confirms the model:

| sheet | type | units | ceiling/unit | wall/unit |
|-------|------|-------|--------------|-----------|
| ID-413 | QQ A | **90** | 253.8 | 691.2 |
| ID-407 | KING A | 26 | 221.1 | 627.8 |
| ID-411 | KING SUITE B | 2 | 353.4 | 783.3 |
| ID-417 | BUNK B | 1 | 271.1 | 500.5 |

ID-413 alone (90 × QQ A) is 22,843 SF = 39% of the whole Gyp Ceiling total.

**13.3 ~~BLOCKER A — the multiplier is NOT IN THE INPUT.~~ FALSIFIED — see the correction below.**
The drawing index (p1) lists **`CS-04 GUESTROOM MATRIX`** and `LEVEL 01–07 RCP PLAN`s, but the
40-page PDF contains **neither CS-04 nor the guestroom floors (LEVELS 02–06)** — only Level 1 Lobby,
Pop-Up Hub, Level 7, and the 18 prototype sheets. p2's "UNIT TYPE" is a *legend of tag symbols*, not
counts; Level 7 carries no unit tags. ~~**Nothing in this PDF states "90 × QQ A".**~~ The estimator
had the full set; our input is a subset. ~~No LLM or geometry can derive a number the document does
not contain — this is an INPUT gap, not a code gap. Resolution (user decision 2026-07-17): **the
human supplies unit counts in the manifest** (an estimator knows the room mix) — the sanctioned
human-in-the-loop channel.~~

> ### CORRECTION (2026-08-04, phase 23 / plan 23-16, decision D-01) — the multiplier IS in the input
>
> **The old claim (struck above):** "the multiplier is NOT IN THE INPUT"; "nothing in this PDF
> states 90 × QQ A"; therefore the unit counts must come from a human via the manifest. The same
> claim was carried in `_manifest_room_mix`'s docstring, which asserted the mix "is routinely not in
> the drawing set at all … so **no reading of the plan can recover it**". Both were reasoned from
> the ABSENCE of CS-04 and of the guestroom floor plans; neither was tested against the sheets the
> PDF does contain.
>
> **The falsifying evidence — a blind census of the set's own unit key plans.** Pages 7 and 8
> (`ID-001 LEVEL 01 KEY PLAN` / `ID-002 LEVEL 05 KEY PLAN`, selected structurally by their printed
> DRAWING titles, not by a page-text search) carry **214 room tags with 214 distinct room numbers
> and zero duplicates**. Counting them — before any golden number was read — yields:
>
> | unit type | from the drawings | §13.2's golden multiplier |
> |---|---|---|
> | QQ A | **90** | 90 |
> | KING A | **26** | 26 |
> | K SUITE B (= KING SUITE B) | **2** | 2 |
> | BUNK B | **1** | 1 |
>
> **4 of 4 exact.** The room mix is in the input; it was simply on two sheets nobody had read as
> data. (The census measures 214 tags where the investigation first reported 217; the three-tag
> difference is multi-line room names and touches none of the four multipliers above.)
>
> **Citation:** `INV-05-finish-schedule-binding.md` §2 Key B (the census), plan `23-05-SUMMARY.md`
> (the fail-closed reader) and `23-08-SUMMARY.md` (the wiring and the D-10 precedence).
>
> **The delivered contract.** `room_tags.derive_room_mix` reads the census on every run and
> `TakeoffPipeline._resolve_room_mix` publishes it under one precedence: **the drawings win**
> wherever the census has a count, the manifest fills only names the drawings never state, a
> disagreement is **flagged on the row that uses the number** naming both values and both sources,
> and a census that cannot be trusted (a duplicated room number) refuses **wholesale** rather than
> publishing a partial count. Eleven of Moxy's fifteen unit types are now drawing-derived and every
> count carries `unit_count_source` into its formula string. `human_inputs/moxy_knoxville.json` is
> **not edited** — the two counts it gets wrong (`BUNK A`, `KING SUITE C`: 2 where the drawings say
> 1) are surfaced as flags, which is how the estimator finds them.

**13.4 BLOCKER B — the room engine cannot extract Moxy's rooms.** With the scale now correct
(§13.5), on ID-411: `extract_walls` → 41 walls, but `extract_rooms` → 8 fragments of **17 SF** each
(expected ~353). No closed room path exists in the vector data (a search for closed paths of 100–900
SF returns **zero**) — Moxy draws rooms as loose axis-aligned strokes (type='s'), so Recipe C's
centerline polygonization never closes them. The printed dimensions ARE in the text layer (63 on
ID-411, incl. `17'-0"` × `20'-7 1/8"` = **350.1 SF vs golden 353.4 = 0.9%** — the estimator's own
method), but a naive "two biggest dims" rule generalizes at **14–106% error** because each sheet has
FOUR viewports (AR/FF/RCP/EM) whose dimension strings intermix, and rooms are not rectangles.
**Remaining work = bind dimensions/geometry to the AR-plan viewport and close a non-rectangular
outline.** That is a real CV task, not tuning.

**13.5 FIXED — the scale reader only understood Crow's format.** `extract_printed_scales` required
the literal word `SCALE`, so **all 40 Moxy sheets read ZERO scales** and fell back to a project-level
assumption. Moxy prints the bare ratio under the viewport title (`KING SUITE B - AR PLAN` /
`1/4" = 1'-0"`). Since area scales by the SQUARE, measuring a 1/4" sheet at an assumed 1/8" is a **4×
error on every room**. Now reads Moxy p27 → 13 scales @ 4.0 ft/in, p9 @ 5.33. Commit 7ee4cc9.

**Honest status:** Moxy needs (a) manifest unit counts [user-agreed], (b) a viewport-bound room
extractor. Until (b) exists, Gyp Ceiling/Gyp Wall stay ~0 regardless of manifest and scale.

## 14. The room-measurement engine (2026-07-17) — Gyp Ceiling 0 → 7.0% *(by direct probe, NOT by a run — see the correction in §14 below)*

**`deterministic/room_fill.py` (Recipe E).** A room is **not a polygon in the file — it is a REGION
ENCLOSED BY INK**, so rasterize the drawing and flood-fill it. Built because every vector route
failed on Moxy: `extract_rooms` → 17 SF fragments (room is 353), **zero** closed room paths exist,
dimension-pairing 14–106%, wall-extent bbox 3–44%.

Three rules carry the accuracy:
1. **Sum EVERY enclosed region** in the unit (bedroom + bathroom + entry). A single-seed fill stops
   at the bathroom wall — a systematic **~30% under**.
2. **Measure at THAT drawing's own printed scale.** Area scales by the SQUARE; a 1/4"=1'-0" sheet
   measured at an assumed 1/8" is a 4× error.
3. **Select the drawing by DISCIPLINE, not size** — a ceiling comes off the **RCP** plan, a
   floor/wall off the **AR** plan (`BASIS_PLAN_KIND` / `select_fill_for_basis`). Picking "the largest
   region on the sheet" = **33% mean error**; by discipline = **3.3%**.

Anchor each fill on its `"<NAME> - <KIND> PLAN"` title — the generic viewport segmentation shatters a
unit plan into 167 + 65 + 41 SF pieces.

**Prototype × room mix.** `_fuse_room_fills` emits the line item; the multiplier comes from manifest
entries `{"name": "QQ A", "measure": "unit_type", "assumptions": {"unit_count": 90}}`, matched to the
fill's `plan_name`. It is a COUNT, never a quantity — and it is an estimator input *because it is
genuinely absent from the drawing set* (§13.3). A prototype whose type is not in the mix is emitted
as the single measured unit and **flagged**, never multiplied by a guess.

**Blind result (no golden peeking), Moxy Gyp Ceiling — was 0.**

> ### CORRECTION (2026-08-04, phase 23 / plan 23-16, decision D-01) — how this figure was produced, and the table recomputed
>
> **The old claim (implicit in this section's heading and its TOTAL row):** that the pipeline had
> taken Moxy Gyp Ceiling from 0 to a **7.0%** blind error — i.e. that a RUN produced these numbers.
>
> **The falsifying evidence, in two parts.**
>
> 1. **The figure came from a PROBE calling the engine directly, not from a run.** The saved run
>    that postdates every room-engine and classifier commit of that day
>    (`VisionOnly_Moxy_Knoxville_20260717_045741`) contains `room_fill` **0 times**, `unit_count`
>    **0 times** and `plan_name` **0 times**, and every `unit_type` prototype landed as an empty
>    `0.0` line item. **A real run could not reach these sheets at all**: the classifier discarded
>    **18 of Moxy's 40 pages**, including all 16 guestroom prototypes (pages 23–38), because
>    `COVER` matched inside an electrical keynote reading `LIGHT SWITCH COVER PLATE` that bled into
>    the title-block crop. `title_sheet` means an empty pass list, which means the sheet is skipped
>    before geometry runs. The numbers below are real measurements of real drawings; what was not
>    real was the claim that a client would receive them.
> 2. **The TOTAL row does not equal the sum of its own rows.** The nine per-sheet rows sum to
>    **44,011** measured against **41,912** golden (+5.0%), not the **45,837 / 42,835 = 7.0%**
>    printed. Whatever the total was computed over, it was not this table, and the two cannot both
>    be the basis.
>
> **Citation:** `INV-00-live-run-evidence.md` §1 (the run artifacts and the direct-invocation
> proof), `INV-08-coverage-flags.md` §1.1–§1.2 (the 18 skipped pages and the deciding keyword),
> plans `23-01-SUMMARY.md` and `23-06-SUMMARY.md` (the fix: Moxy 18 → 2 classifier-discarded pages,
> with Crow, Bob's and Chelsea byte-identical).
>
> **The recomputation, on ONE stated basis.** Basis: **the shipped engine's measured RCP fill for
> each prototype sheet × the unit count the in-plan census resolves for that plan name** (§13.3's
> correction), scored against the same golden per-sheet figures this table already quoted. Measured
> offline today, zero API — all nine per-sheet values reproduce the originals exactly:
>
> | sheet | plan | measured/unit | × units (source) | = measured | golden | err |
> |---|---|---|---|---|---|---|
> | ID-415 | QQ C | 284.3 | 15 (census) | 4,264.5 | 4,255 | **+0.2%** |
> | ID-414 | QQ B | 309.5 | 6 (census) | 1,857.0 | 1,843 | **+0.8%** |
> | ID-417 | BUNK B | 274.6 | 1 (census) | 274.6 | 271 | **+1.3%** |
> | ID-409 | KING C | 217.6 | 5 (census) | 1,088.0 | 1,064 | **+2.3%** |
> | ID-411 | KING SUITE B | 341.7 | 2 (census) | 683.4 | 707 | **−3.3%** |
> | ID-407 | KING A | 229.4 | 26 (census) | 5,964.4 | 5,748 | **+3.8%** |
> | ID-410 | KING SUITE A | 362.5 | 5 (census) | 1,812.5 | 1,884 | **−3.8%** |
> | ID-408 | KING B | 235.5 | 15 (census) | 3,532.5 | 3,297 | +7.1% |
> | ID-413 | QQ A | 272.6 | 90 (census) | 24,534.0 | 22,843 | +7.4% |
> | **TOTAL** | | | | **44,010.9** | **41,912** | **+5.0%** |
>
> **This table EXCLUDES four sheets, and all four now carry a multiplier flag.** ID-412 (KING SUITE
> C) and ID-416 (BUNK A) are published at the census count **1** while the manifest declares **2** —
> a disagreement, flagged, with the manifest untouched; ID-420 (ACC QQ RIS) and ID-422 (ACC BUNK)
> have no key-plan tag at all, so their count of 2 is manifest-only and is flagged as **not derived
> from the drawings**. Correcting those multipliers legitimately moves the Gyp Ceiling total
> **AWAY** from golden, and **that movement is not a regression** — it is the point of §14.3. This
> total is therefore a record of one basis, not a target: nothing in the suite asserts against it.
> (Plans 23-08, 23-13.)

**The original table, as published on 2026-07-17 (measured by direct probe, not by a run):**

| sheet | measured/unit | × units | golden | err |
|-------|---------------|---------|--------|-----|
| ID-415 | 284.3 | 4,264 | 4,255 | **0.2%** |
| ID-414 | 309.5 | 1,857 | 1,843 | **0.7%** |
| ID-417 | 274.6 | 275 | 271 | **1.3%** |
| ID-409 | 217.6 | 1,088 | 1,064 | **2.3%** |
| ID-411 | 341.7 | 683 | 707 | **3.3%** |
| ID-407 | 229.4 | 5,964 | 5,748 | **3.8%** |
| ID-410 | 362.5 | 1,813 | 1,884 | **3.8%** |
| ID-408 | 235.5 | 3,533 | 3,297 | 7.1% |
| ID-413 | 272.6 | **24,534** | 22,843 | 7.4% |
| **TOTAL** | | **45,837** | **42,835** | **7.0%** (5.0% excl. the 2 defects) |

**14.1 A mixed sheet must still be measurable (the bug that hid all of the above).** Moxy's guestroom
prototypes carry interior elevations AND the AR/RCP plans holding every quantity. The word ELEVATION
won the classifier, so all 16 classified `elevation`, never reached `_DETERMINISTIC_SHEET_TYPES`, and
the engine never ran: **run 3 measured 1 fill in the whole project and scored 2%.** A sheet is a
COLLECTION of drawings; its type is only the dominant one. An explicit `"- AR/RCP PLAN"` viewport
title now outranks a stray ELEVATION keyword (not FF/EM/FC — those carry no take-off geometry).
Moxy floor_plan **10 → 26**; Crow/Bob's unchanged.

**14.2 OPEN DEFECT — do not paper over.** ID-412/ID-416 measure **~2×** (458 vs 231): ~~the clip
reaches the adjacent opposite-hand plan.~~ **FALSIFIED — see the correction below.** The 900 SF
plausibility guard does not catch them. Setting it to ~420 SF would make them pass and would
**overfit to guestrooms** — it silently breaks on a lobby. **Fix the clip, not the threshold** —
that instruction stands, and is the one part of this passage the evidence upholds.

> ### CORRECTION (2026-08-04, phase 23 / plan 23-16, decision D-01) — the clip is EXONERATED; the multiplier is the defect
>
> **The old claim (struck above):** ID-412 and ID-416 read ~2× because *the clip reaches the
> adjacent opposite-hand plan*. It was inferred from the ~455 SF readings; the clip itself was
> never tested. (The investigator who first proposed it has formally retracted it —
> `INV-00-live-run-evidence.md` §1b, "RETRACTED 2026-08-03 — this diagnosis was WRONG".)
>
> **The falsifying evidence — three independent geometric probes, all free and offline.**
>
> 1. **Clip-width sweep.** Varying the clip's half-width over a **240 pt range** changes ID-412 by
>    **0.0 SF** and ID-416 by **0.5 SF** — while it moves ID-415 by **+57.5 SF (+20%)** and ID-407
>    by **+38.8 SF (+17%)**. If the 2× came from the clip, the two "defective" sheets would be the
>    MOST clip-sensitive; they are the LEAST.
> 2. **Where the counted ink physically sits.** Every enclosed region the fill counts on ID-412 lies
>    inside a 339 × 502 pt column — **47% of the 715 × 612 pt clip**. Nothing from a neighbour is
>    inside it. (Adjacent clips do overlap by 8–48% on *every* prototype sheet, and the two
>    "defective" ones are not even the worst — ID-416 is the 4th lowest.)
> 3. **The drawing's own printed dimensions.** ID-412 prints `17'-0 1/8" × 26'-9 1/8"` = **455.2
>    SF** against a measured fill of **458.3 SF** — a ratio of **1.007**. A clip that had swallowed
>    a second unit would read ≈ 2.0. Thirteen of the sixteen prototypes land in 0.976–1.073, and
>    ID-412 and ID-416 are among the *tightest* fits in the whole set.
>
> **The real defect is a unit count in the human input.** `human_inputs/moxy_knoxville.json`
> declares `unit_count: 2` for these sheets, derived from the golden `Doors-WD 2 EA` — but on a
> suite those two wood doors are an **entry door plus a connecting door in ONE unit** (the sheet's
> own key note 3 reads *"WHEN CONNECTING DOOR IS USED…"*). So a correct 458.3 SF was multiplied by
> 2 and published at `confidence: "high"`. Four sheets share the signature: **ID-412, ID-416,
> ID-420, ID-422**. The 900 SF guard could never have caught it — it sat on the **wrong side of the
> multiplication**, seeing 458 SF and passing it, while the 917 SF that was actually wrong was
> produced later in fusion where no guard looked.
>
> **Citation:** `INV-02-clip-defect.md` §2 (region positions), §3 (the clip-width sweep and the
> overlap table), §4 (the printed-dimension probe and the multiplier), §5 (the wrong-side guard);
> retraction in `INV-00-live-run-evidence.md` §1b.
>
> **The delivered contract, on both halves.**
> - *The threshold:* `_MAX_UNIT_SF = 900.0` and `flag_implausible_unit` are **deleted**. Their
>   replacement is `cross_check_extent`, a **dimensionless ratio** against the drawing's own printed
>   overall extent (`EXTENT_TOLERANCE = 1.25`, read off the observed distribution: thirteen honest
>   sheets at 0.976–1.073, a genuine two-plan leak at ≈ 2.0). The same number governs a 250 SF guest
>   room and a 12,000 SF ballroom — asserted by scaling both sides by fifty. It **flags, never
>   filters**: a sheet printing no dimension pair is NEEDS REVIEW carrying its measurement, and a
>   test greps `room_fill.py` so no new square-foot constant can reintroduce the shape. (Plan 23-11.)
> - *The root cause:* a multiplier-review flag now fires on **exactly** ID-412/416/420/422 and on
>   none of the nine census-confirmed sheets, keyed off a structural census-vs-manifest disagreement
>   rather than a blanket "count > 1"; any count above one downgrades confidence and carries its
>   source. (Plan 23-13.)
> - *"Fix the clip, not the threshold" is still owed in part.* The clip WAS made rotation-correct
>   and page-space-bounded (plan 23-07 — it was rendering a band across the whole sheet on
>   `/Rotate 270` pages). The fully geometric, viewport-bounded clip cell is **NOT done**: its
>   proposed partition rule is falsified on the fixtures (best variant reproduces 4 of 16 sheets),
>   and it is blocked behind an unanswered domain question — *what should a dimension-string
>   corridor contribute to a room's measured area?* — recorded as **DEF-23-SP4**. That is stated
>   here rather than quietly dropped.

**14.3 Methodology warning (cost us hours).** "Best of AR/RCP" and "closest to golden" are **PEEKING**
and inflated this engine's apparent accuracy from 33% → 3%. Fix the selection rule BLIND, then score.

**14.4 Excel export.** `scripts/export_takeoff_excel.py` writes a client-ready workbook where every
row carries its provenance — MEASURED / HUMAN INPUT / NEEDS REVIEW / NOT MEASURED — plus an About
sheet defining each. A take-off a client bids from must say where each number came from, and a blank
must never be read as a zero.

## 12b. Why manifest + scale did not produce 100%

The manifest is the shopping list; the scale is the ruler. **Neither measures anything.** The
manifest said "Gyp Ceiling is an item, in SF" and the scale said "1 inch = N feet" — but the code had
no per-room measurement step, so it computed 0, converted 0 correctly, and reported 0. Names + units
cannot rescue a measurement that was never taken.

**Why (this is §9's frontier, now confirmed at scale):** Moxy is a hotel interior fit-out. Its
quantities are per-ROOM partition wall LF × height across ~20 guestroom floor plans, per-room ceiling
areas, wall-covering areas keyed by finish type (WC-1…WC-10) via a finish schedule → room mapping,
and a 213-door schedule. The engine measures a single main-plan footprint + thickness-class wall
linework — Crow's shape. **Nothing in the current measurement layer produces per-room areas**, so
Gyp Ceiling / WC-* / Base / Doors are all 0. Honest bottom line: **the app does not work on Moxy**;
reaching accuracy here is the room-level measurement program (extract_rooms → per-room wall/ceiling
areas → finish-schedule binding → per-format door schedules), not tuning.

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
engine is floor-plan-centric.** Bob's golden quantities are Gas Piping 886 LF (civil linework),
Exterior Painting CMU 16,219 SF + EIFS 3,053 SF (elevation wall areas), Lintels 179 LF (structural) —
**none measured by the floor-plan walls/rooms/footprint engine.** Crow is a warehouse (everything on
one floor plan); Bob's is a retail fit-out (quantities across civil + elevations + schedules).

**So the naming is now general; the measurement is not.** The next program is a
**sheet-type-aware measurement layer**: civil linework LF (piping/curb/utilities on C-sheets),
elevation wall-area SF (painting/EIFS/cladding on elevations), schedule-driven counts per format, in
addition to the floor-plan engine — then the fusion binds the (now-general) names to whichever
measurement produced the number. Plus the learning loop, then re-validate across all 4 plans.
Session API spend to date ≈ $16. Context is very large — continue in a FRESH session using this doc
+ memories as the plan.

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

**13.3 BLOCKER A — the multiplier is NOT IN THE INPUT.** The drawing index (p1) lists
**`CS-04 GUESTROOM MATRIX`** and `LEVEL 01–07 RCP PLAN`s, but the 40-page PDF contains **neither
CS-04 nor the guestroom floors (LEVELS 02–06)** — only Level 1 Lobby, Pop-Up Hub, Level 7, and the 18
prototype sheets. p2's "UNIT TYPE" is a *legend of tag symbols*, not counts; Level 7 carries no unit
tags. **Nothing in this PDF states "90 × QQ A".** The estimator had the full set; our input is a
subset. No LLM or geometry can derive a number the document does not contain — this is an INPUT gap,
not a code gap. Resolution (user decision 2026-07-17): **the human supplies unit counts in the
manifest** (an estimator knows the room mix) — the sanctioned human-in-the-loop channel.

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

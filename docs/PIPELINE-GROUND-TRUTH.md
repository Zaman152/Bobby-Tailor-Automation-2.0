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

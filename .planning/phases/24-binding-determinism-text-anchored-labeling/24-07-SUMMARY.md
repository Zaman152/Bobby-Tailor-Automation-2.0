---
phase: 24-binding-determinism-text-anchored-labeling
plan: 07
subsystem: vision (overlay + schema + prompts) / pipeline vector passes
tags: [set-of-mark, text-anchor, schema-topology, dependency-ordering, prompt-injection, pdf_text, floorplanvlm, V4-DET-01, V4-DET-03]

# Dependency graph
requires:
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 01
    provides: "`bundle['candidate_anchors']` — the per-candidate anchor record, and the RECORDED-ABSENCE vs NO-RECORD distinction (INV-08) this plan's exclusion rule is built on"
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 04
    provides: "the orphan-room branch and the `unnamed_geometry` ledger that every candidate this plan declines to ask about flows into"
  - phase: 23-measurement-engine-completion
    provides: "the in-context Set-of-Mark migration on the full sheet that made SYMBOL_GALLERY_PROMPT's crop-gallery wording stale"
provides:
  - "`render_overlay(..., anchors=)` — the marker chip carries the drawing's own printed words beside the candidate ID"
  - "right-edge chip clamping, so a longer label slides left instead of off the sheet (T-24-32)"
  - "the symbol pass asks ONLY about clusters the drawing names; a RECORDED ABSENCE is excluded from the request rather than asked and discarded"
  - "`_build_anchor_hint` — the per-candidate anchor table, `wrap_pdf_text`-delimited, so the anchor survives the 1568px downscale (T-24-27)"
  - "`_ids_shown_on` — the request's enums are built from the IDs actually MARKED on the images sent, never wider"
  - "dependency-ordered `semantic_labeling_schema`: wall_classes -> regions -> rooms, every ID field an enum of an already-defined ID"
  - "an omittable bounding-wall citation (present-and-empty), routing to 24-04's orphan-room branch"
  - "a programmatic no-numeric-field guard discovered by module introspection, so a later schema cannot ship uncovered"
  - "SYMBOL_GALLERY_PROMPT describing the in-context full-sheet render actually issued, with an explicit primary/secondary/insufficient evidence ladder"
affects: [24-08, 24-09, 24-10, 25 detection, any consumer of the vector vision passes]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Do not ask a question you will discard the answer to: a candidate with no anchor is absent from the request, not filtered from the response — cheaper, and it cannot flip"
    - "A recorded absence is not an absent record (INV-08), applied to a whole vision pass: a failed anchor computation must not silently empty the request"
    - "Schema topology as a correctness device — a level may only reference IDs defined above it, so a topological gap becomes UNEXPRESSIBLE rather than merely flagged (FloorplanVLM, VISION-MODEL-EVIDENCE §4)"
    - "Omittability under a required-every-property contract is expressed as an ALLOWED EMPTY LIST, so 'I cannot cite one' is a first-class answer and not an invented reference"
    - "A structural ban proven by module introspection rather than by naming its subjects, failing loudly on a builder it cannot construct"
    - "Prompt tests assert on CLAUSES, never on whole text — an exact-text assertion makes every future wording improvement a test failure"
    - "An adapter at the pass boundary keeps a schema-shape change from propagating: fusion, the reporter and the merged result read the keys they always read"

key-files:
  created:
    - .planning/phases/24-binding-determinism-text-anchored-labeling/24-07-SUMMARY.md
  modified:
    - src/bobbytailor/vision/overlay.py
    - src/bobbytailor/vision/schemas.py
    - src/bobbytailor/vision/prompts.py
    - src/bobbytailor/pipeline/takeoff_pipeline.py
    - tests/test_vision_schemas.py
    - tests/test_pipeline_deterministic.py
    - tests/test_symbol_identification.py
    - .planning/phases/24-binding-determinism-text-anchored-labeling/deferred-items.md
    - .planning/ROADMAP.md
    - .planning/STATE.md

key-decisions:
  - "The exclusion rule fires on a RECORDED ABSENCE only, never on 'this ID is missing from the anchor map'. A candidate with no record was never interrogated; treating that as 'nothing names it' would let a failed anchor computation silently empty an entire vision pass (INV-08, the same rule 24-04 applies to a present-and-empty bounding-wall citation)."
  - "The request's enums are built from `_ids_shown_on(images)` — the IDs actually drawn on the images sent — not from the candidate set proposed. `render_overlay` partitions and the batch caps at 20, so the marked set can be a strict SUBSET; asking beyond it is the same defect as asking about an unanchored cluster, in a different costume."
  - "The anchor is delivered TWICE by design: on the chip and in the user hint. The chip is the text-anchored evidence the model reads in place of a shape; the hint is its survivable delivery, because a few characters of drafting text can be unreadable after the 1568px downscale."
  - "Omittability is an ALLOWED EMPTY LIST, not an optional property. The GA contract requires every property in `required`; a present-and-empty `bounding_wall_ids` is a positive statement ('I can cite none') that 24-04's orphan-room branch reads, whereas an answer omitting the key leaves the field ABSENT and is a different fact."
  - "The SCHEMA topology changed; the internal label contract did not. One adapter in `_run_sheet_vector` maps the dependency-ordered answer back onto `main_plan_region` / `wall_class_labels` / `room_labels`, so 196 fusion and voting tests are unchanged and the blast radius stops at the pass boundary."
  - "`_main_region_from_answer` returns None when MORE than one region claims to be the main plan, not just when none does. Two claims are a contest, and picking the first would be guessing which of two disagreeing answers to trust; the deterministic main-plan selection is the measurement authority either way."
  - "The no-numeric test discovers builders by module introspection and FAILS LOUDLY on a builder whose arguments it cannot supply, rather than skipping it. A silently-skipped builder is exactly how a quantity field would arrive."
  - "T-24-28 (injection via text rendered onto the chip) is ACCEPTED, not mitigated. Text rasterised into an image cannot be delimiter-wrapped; the standing untrusted-data clause covers drawing content generally and the chip carries a short nearest-word token, not a free paragraph. Recorded rather than silently assumed."
  - "The one STRICT RULE altered in SYMBOL_GALLERY_PROMPT is `Prefer \"unknown\" over guessing when the CROP is ambiguous` -> `when the MARKER is ambiguous`. The rule is preserved; only the stale noun naming an image the pipeline no longer sends was corrected."

patterns-established:
  - "Anchor-bearing Set-of-Mark: chip text is `ID + the plan's own words`, and a recorded absence renders the bare ID with no placeholder and no empty separator — byte-identical to the pre-24-07 chip"
  - "Evidence ladder in a prompt: primary (the plan's printed callout), secondary (position and repetition), explicitly insufficient (the drawn shape alone) with the unknown sentinel as the fallback"
  - "Positive control beside a structural ban: `test_the_raster_path_remains_the_one_schema_permitted_a_number` proves the no-numeric assertion is a real constraint and not vacuous"

requirements-completed: []  # V4-DET-01 (prompt half) and V4-DET-03 are DELIVERED; the phase gate 24-10 remains their closer. See "Requirement status" below.

coverage:
  - id: D1
    description: "The Set-of-Mark marker chip carries the candidate's anchor text alongside its ID; a recorded absence renders the bare ID byte-identically to before"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_vision_schemas.py#test_anchor_chip_carries_the_candidate_id_and_its_anchor_text"
        status: pass
      - kind: unit
        ref: "tests/test_vision_schemas.py#test_anchor_chip_without_an_anchor_is_the_bare_id_with_no_placeholder, #test_render_overlay_with_a_recorded_absence_is_byte_identical, #test_render_overlay_with_an_anchor_actually_changes_the_raster, #test_the_marker_budget_and_partition_survive_anchor_text, #test_the_chip_box_is_clamped_inside_the_right_edge"
        status: pass
    human_judgment: false
  - id: D2
    description: "A candidate with a RECORDED ABSENCE is excluded from the request entirely and stays flagged unlabeled, never named from shape"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_vision_schemas.py#test_the_symbol_pass_asks_only_about_candidates_the_drawing_names, #test_the_symbol_pass_is_skipped_rather_than_sent_with_no_candidates, #test_an_absent_anchor_map_is_not_read_as_every_candidate_unanchored, #test_a_recorded_absence_and_an_absent_record_are_not_the_same_thing"
        status: pass
      - kind: unit
        ref: "tests/test_symbol_identification.py (restricted candidate set)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The per-candidate anchor table reaches the user hint only inside the <pdf_text> delimiters (T-24-27)"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_vision_schemas.py#test_the_anchor_hint_is_wrapped_in_the_pdf_text_delimiters, #test_the_anchor_hint_carries_the_full_text_the_chip_had_to_bound, #test_the_anchor_hint_is_empty_when_no_listed_candidate_is_anchored"
        status: pass
      - kind: other
        ref: "takeoff_pipeline._build_anchor_hint -> wrap_pdf_text (takeoff_pipeline.py:891)"
        status: pass
    human_judgment: false
  - id: D4
    description: "semantic_labeling_schema is dependency-ordered (wall_classes -> regions -> rooms) with every ID field an enum of an already-defined ID"
    requirement: V4-DET-03
    verification:
      - kind: unit
        ref: "tests/test_vision_schemas.py#test_dependency_ordered_levels_precede_every_reference_to_them, #test_dependency_ordered_still_guards_every_id_list, #test_semantic_labeling_enums_equal_candidate_lists, #test_the_semantic_pass_sends_the_dependency_ordered_schema, #test_the_request_never_asks_about_a_marker_it_did_not_send"
        status: pass
    human_judgment: false
  - id: D5
    description: "No vector-path schema builder carries a numeric property, proven across every builder discovered by introspection"
    requirement: V4-DET-03
    verification:
      - kind: unit
        ref: "tests/test_vision_schemas.py#test_no_numeric_fields_anywhere_on_any_vector_path_builder + #test_the_raster_path_remains_the_one_schema_permitted_a_number"
        status: pass
    human_judgment: false
  - id: D6
    description: "A room that cannot cite a bounding wall answers with an EMPTY list and is ledgered by 24-04's orphan-room branch rather than published"
    requirement: V4-DET-03
    verification:
      - kind: unit
        ref: "tests/test_vision_schemas.py#test_dependency_ordered_a_room_may_cite_no_bounding_wall, #test_dependency_ordered_rooms_are_absent_rather_than_empty_enum, #test_the_room_wall_citation_lands_on_the_record_fusion_reads, #test_the_room_wall_citation_writes_to_a_dataclass_record_too"
        status: pass
    human_judgment: false
  - id: D7
    description: "SYMBOL_GALLERY_PROMPT describes the in-context full-sheet render actually issued and names the chip text as primary evidence; every STRICT RULE and the injection clause survive"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_vision_schemas.py#test_the_symbol_prompt_describes_the_in_context_render_it_receives, #test_the_symbol_prompt_tells_the_model_to_read_the_anchor_text, #test_every_semantic_prompt_keeps_the_injection_mitigation, #test_every_semantic_prompt_still_forbids_reporting_a_number"
        status: pass
    human_judgment: false
  - id: D8
    description: "The accuracy benefit of the text anchor (the 0.03-0.39 -> 0.65-0.92 mechanism) on THIS codebase's drawings"
    requirement: V4-DET-01
    verification: []
    human_judgment: true
    rationale: "Unmeasurable offline BY THE PLAN'S OWN SUCCESS CRITERIA. The figure comes from published benchmarks on other datasets (assumption A3); measuring it here requires a paid run, which is forbidden autonomously. This plan is judged on whether the anchor is present, correct and delimited — never on an accuracy percentage."

# Metrics
duration: ~6h wall clock across 2 sessions (interrupted)
completed: 2026-08-06
status: complete
---

# Phase 24 Plan 07: Dependency-Ordered Schema Topology + Anchor-Bearing Set-of-Mark Summary

**The marker chip now carries the drawing's own printed words instead of a bare ID, unanchored clusters are never asked about at all, and the vector schema is dependency-ordered so a room that cannot cite a bounding wall says so rather than inventing one.**

## ⚠ This plan was INTERRUPTED and closed out in a second session

This is recorded first because it changes how the commit list should be read.

| Session | Date | What landed |
|---|---|---|
| **Session 1** (interrupted) | 2026-08-06, 00:43–02:14 +0500 | Task 1 (`e7b648b`) and Task 2 (`2b3e56a`), each committed atomically with its own full-suite run. Execution stopped after Task 2. |
| **Session 2** (close-out) | 2026-08-06, ~05:30–07:00 +0500 | Task 3 found **written but UNCOMMITTED** in the working tree. Verified against the plan's acceptance criteria rather than assumed correct, then committed as `7cbdf40`. Full suite, both gates, SUMMARY and state updates completed here. |

**No work was redone.** The close-out session's first action was to check the two landed commits against
the plan's `must_haves` and each task's `<acceptance_criteria>`, and it re-ran every acceptance command
for all three tasks — not only Task 3's — before committing anything. Nothing in Tasks 1 or 2 needed
correction, and nothing in the uncommitted Task 3 diff needed correction either; it was committed on
verified merit, not because it happened to exist.

**What was verified rather than trusted, in the close-out session:**

- Task 1's chip/exclusion/delimiter behaviour re-read at the source (`_build_anchor_hint` at
  `takeoff_pipeline.py:866-892`, the exclusion loop at `:4090-4160`), confirming the anchor table
  really does pass through `wrap_pdf_text` and that the restriction fires on a recorded absence only.
- Task 2's numeric ban re-run as a live command and re-read as a test
  (`test_no_numeric_fields_anywhere_on_any_vector_path_builder`), confirming the guard is
  introspective and has a positive control.
- Task 3's four acceptance commands re-run from a cold interpreter, all four matching the plan's
  stated expected output.
- The schema's top-level key order (`wall_classes, regions, rooms, confidence`) checked against the
  rewritten prompt's numbered task order — they match, which is the point of the reorder.
- `ROOM-1` confirmed as the real room candidate-ID prefix (`deterministic/rooms.py:353`), so the
  prompt's "room faces like ROOM-1" describes chips that actually exist.

## Performance

- **Duration:** ~6h wall clock across two sessions (interrupted between Task 2 and Task 3)
- **Tasks:** 3 of 3
- **Files modified:** 7 source/test files (+1235 / −72 across the three commits)
- **Suite:** 2092 (pre-plan baseline) → 2109 (T1) → 2122 (T2) → **2131 passed, 1 skipped, 2 deselected** (T3)

## Accomplishments

- **The chip speaks the drawing's language.** `overlay._draw_marker` drew `label = candidate_id` and
  nothing else — a box and an identifier, which is precisely the symbol-conveyed condition the
  evidence base measures at 0.03–0.39 against 0.65–0.92 for text-anchored classes
  (`VISION-MODEL-EVIDENCE-2026.md` §3). `render_overlay(..., anchors=)` now threads 24-01's anchor
  records so a chip reads `SYM-9 DOCK BUMPER`. A recorded absence renders the bare ID with no
  placeholder and no empty separator — byte-identical to the old chip.
- **The question is not asked when the drawing has no answer.** A cluster with a RECORDED ABSENCE is
  excluded from the request entirely rather than asked and then discarded. Not asking is cheaper and
  it cannot flip. Those clusters flow to 24-04's ledger and stay flagged unlabeled — never named
  from their outline. On Crow, 40 of 107 clusters were anchored and 67 were recorded absences.
- **The anchor is delivered twice.** The chip is the evidence; `_build_anchor_hint` is its survivable
  delivery, because a few characters of drafting text can be unreadable after the 1568px downscale.
  The table is drawing-derived untrusted text and is `wrap_pdf_text`-wrapped (T-24-27).
- **A topological gap became unexpressible.** `semantic_labeling_schema` was FLAT — `main_plan_region`
  plus `wall_class_labels`, with no expressible relationship between a room and the walls bounding
  it. The observable consequence in both saved paid runs was four room candidates published at
  roughly 10–11 SF each on a 397,600 SF warehouse. The schema is now declared skeleton-first
  (`wall_classes` → `regions` → `rooms`), each level referencing only IDs defined above it.
- **A room may honestly cite nothing.** `bounding_wall_ids` is required (the GA contract) with an
  ALLOWED EMPTY LIST, so the model is never forced to invent a reference. That present-and-empty
  citation is exactly what 24-04's orphan-room branch reads.
- **Zero numeric properties, structurally.** A test discovers every vector builder by module
  introspection rather than naming them, fails loudly on a builder whose arguments it cannot supply,
  and is paired with a positive control asserting the raster path DOES carry an integer — so the ban
  is a real constraint and not a vacuous assertion.
- **The symbol prompt stopped describing images that are no longer sent.** It still said "The images
  form a crop gallery: each tile shows one symbol group... A crop of the sheet's legend may be
  included." The vector path stopped sending tiles when Phase 23 migrated to in-context Set-of-Mark.
  It now names the full-sheet render, the multi-image partition, and an explicit evidence ladder:
  chip text PRIMARY, position and repetition SECONDARY, drawn shape ALONE insufficient → answer
  "unknown".

## Task Commits

1. **Task 1: The marker chip carries the anchor, and unanchored candidates are not asked about** — `e7b648b` (feat) — *session 1*
2. **Task 2: Dependency-ordered schema topology, with zero numeric fields** — `2b3e56a` (feat) — *session 1*
3. **Task 3: Correct the symbol prompt to describe the images actually sent** — `7cbdf40` (feat) — *session 2, close-out*

**Plan metadata:** see the `docs(24-07)` commit accompanying this file — *session 2, close-out*

## Files Created/Modified

- `src/bobbytailor/vision/overlay.py` — `anchors=` parameter through `render_overlay` /
  `_render_one_overlay` / `_draw_marker`; right-edge chip clamp (T-24-32). Default call unchanged.
- `src/bobbytailor/vision/schemas.py` — `semantic_labeling_schema` reordered to
  `wall_classes → regions → rooms`; every ID field an enum; `bounding_wall_ids` allowed-empty;
  `additionalProperties: false` and full `required` at every level; zero numeric properties.
- `src/bobbytailor/vision/prompts.py` — `SYMBOL_GALLERY_PROMPT` rewritten to the in-context
  full-sheet render with an evidence ladder; `SEMANTIC_LABELING_PROMPT` task list re-ordered to the
  schema's own order and given the room task with its empty-list instruction.
- `src/bobbytailor/pipeline/takeoff_pipeline.py` — `_anchor_texts`, `_recorded_absence_ids`,
  `_build_anchor_hint`, `_ids_shown_on`, `_main_region_from_answer`,
  `_apply_room_wall_references`; anchor pass-through on both the semantic and symbol overlays; the
  unanchored-exclusion and empty-candidate short circuit; the label-contract adapter.
- `tests/test_vision_schemas.py` — +651 lines across the three tasks: anchor-chip, dependency-order,
  introspective no-numeric, and the clause-level prompt invariants.
- `tests/test_pipeline_deterministic.py`, `tests/test_symbol_identification.py` — updated for the
  restricted candidate set and the new schema shape.

## Decisions Made

See `key-decisions` in the frontmatter — nine decisions, the load-bearing ones being the
recorded-absence-only exclusion rule (INV-08), building enums from the IDs actually MARKED rather
than proposed, allowed-empty as the expression of omittability, and the pass-boundary adapter that
kept the schema change from reaching fusion.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Missing Critical] The request asked about candidates whose markers it never sent**
- **Found during:** Task 2 (session 1)
- **Issue:** `render_overlay` partitions a large candidate set across several images and the request
  caps at 20 images, so the set MARKED can be a strict subset of the set proposed. The schema enums
  were being built from the proposed set, asking the model about candidates whose markers it never
  received — the same defect as asking about an unanchored cluster, in a different costume.
- **Fix:** `_ids_shown_on(images)` reads `info['overlay_ids']` off the images actually sent and the
  enums are built from that intersection; an empty intersection raises rather than issuing a request.
- **Files modified:** `src/bobbytailor/pipeline/takeoff_pipeline.py`
- **Committed in:** `2b3e56a`

**2. [Rule 2 — Missing Critical] Room candidates had to be MARKED, not merely enumerated**
- **Found during:** Task 2 (session 1)
- **Issue:** The dependency-ordered schema asks each room which walls bound it. Listing a room in the
  enum without drawing its marker would ask the model about geometry it never saw. A registry bbox
  of all zeros is position UNKNOWN, never position (0,0).
- **Fix:** Room candidates are added to the overlay, and a room with an all-zero bbox is neither
  marked nor asked about (24-01's rule).
- **Files modified:** `src/bobbytailor/pipeline/takeoff_pipeline.py`
- **Committed in:** `2b3e56a`

**3. [Rule 3 — Blocking] The schema topology change would have reached fusion, the reporter and the
  merged result**
- **Found during:** Task 2 (session 1)
- **Issue:** Renaming the answer keys would have rippled through 196 fusion and voting tests and two
  downstream consumers, for no semantic gain.
- **Fix:** One adapter in `_run_sheet_vector` maps `regions`/`wall_classes`/`rooms` back onto
  `main_plan_region`/`wall_class_labels`/`room_labels`. The SCHEMA changed; the internal label
  contract did not.
- **Files modified:** `src/bobbytailor/pipeline/takeoff_pipeline.py`
- **Committed in:** `2b3e56a`

**4. [Rule 1 — Bug, scope-adjacent] One STRICT RULE in `SYMBOL_GALLERY_PROMPT` named a stale noun**
- **Found during:** Task 3
- **Issue:** The plan says to preserve every STRICT RULE without alteration, and also that the stale
  gallery wording must be gone. `Prefer "unknown" over guessing when the CROP is ambiguous` sat in
  both sets: the rule is load-bearing, the noun names an image the pipeline no longer sends.
- **Fix:** `crop` → `marker`. The rule itself — the preference for the unknown sentinel over a guess
  — is preserved verbatim in force and is pinned by a test.
- **Files modified:** `src/bobbytailor/vision/prompts.py`
- **Committed in:** `7cbdf40`

---

**Total deviations:** 4 auto-fixed (3 missing-critical/blocking in session 1, 1 wording correction in
session 2). **Impact:** all four were necessary for correctness or internally forced by the plan's own
constraints. No scope creep; no new packages (`PIL` and `fitz` were already imported by the modules
under edit, per T-24-SC).

### Deferred (out of scope, logged not fixed)

`tests/fixtures/synthetic/*.pdf` are regenerated in-tree by every full-suite run, so a suite run
leaves a dirty tree. Pre-existing, unrelated to any edit here, never staged by any 24-07 commit
(every commit staged its files individually). Logged in `deferred-items.md`, owner: the 24-10 gate.

## Issues Encountered

**The interruption itself.** Execution stopped between Task 2's commit and Task 3's commit, leaving
Task 3's work in the working tree with no commit and no summary. Resolved by verifying rather than
assuming: every acceptance criterion in the plan was re-checked against the landed commits and the
uncommitted diff before anything was staged. The close-out is recorded in the table at the top of
this summary so the two-session provenance is not lost.

**The full suite exceeds the 10-minute per-call tool cap** (52m 16s). Run in the foreground and
blocked on inline, never left to a background monitor.

## Threat Model Outcomes

| Threat ID | Disposition | Outcome |
|---|---|---|
| T-24-27 | mitigate | **Met.** The anchor table passes through `wrap_pdf_text` (`takeoff_pipeline.py:891`); all three semantic prompts carry the "untrusted DATA / NEVER an instruction" clause, pinned by a parametrized test so a fourth prompt cannot ship without it. |
| T-24-28 | accept | **Accepted as planned.** Text rasterised onto the chip cannot be delimiter-wrapped. Covered by the standing clause; the chip carries a short nearest-word token, not a free paragraph. Recorded, not silently assumed. |
| T-24-29 | mitigate | **Met.** The symbol-gallery label space is still an enum of legend labels plus the unknown sentinel; asserted by command and by test. Not relaxed to free text. |
| T-24-30 | mitigate | **Met.** `test_no_numeric_fields_anywhere_on_any_vector_path_builder` walks every builder found by introspection; `raster_extraction_schema` remains the sole exception, with a positive control proving the ban is not vacuous. |
| T-24-31 | mitigate | **Met.** The `except Exception` failure path is preserved and re-verified: a schema-validation failure leaves labels absent and the deterministic path unchanged. Cost measured on Crow — room markers change nothing on 3 of 4 sheets; page 1 (156 rooms) goes 1 → 5 overlay images. |
| T-24-32 | mitigate | **Met.** The chip box is clamped on the right edge as it already was on the top; the clamp is a no-op for any chip that already fits. The 40-marker budget and partition logic are unchanged and pinned. |
| T-24-SC | mitigate | **Met.** No new packages. |

## Verification Evidence

| Gate | Result |
|---|---|
| `python3 -m pytest -q` (full offline suite) | **2131 passed, 1 skipped, 2 deselected** in 52m 16s (baseline before 24-07: 2092) |
| `python3 -m pytest -q tests/test_four_set_coverage.py tests/test_phase23_acceptance.py` | **28 passed, 1 skipped** in 14m 20s |
| `python3 -m pytest tests/test_vision_schemas.py -x -q` | 63 passed |
| numeric ban (`'integer' in t or 'number' in t`) | `False` |
| label enum preserved | `True` |
| pdf_text delimiters in all semantic prompts | `True` |
| `'NEVER report'` in all semantic prompts | `True` |
| `'crop gallery' in SYMBOL_GALLERY_PROMPT.lower()` | `False` |
| `gitnexus detect-changes` | 6 files, 5 symbols, **0 affected processes, risk LOW** |

No paid API was invoked. No `-m golden` run, no `accuracy_gate.sh`, no `vision_only_benchmark.py`,
no `.env` read. `git status --porcelain .planning/paid-run-evidence/` is empty.

## ⚠ Fixture Sequencing — LOUD, as the plan requires

**This plan changed prompt text and schema shape. Every replay fixture key in
`tests/replay_analyzer.py` is a SHA256 over `(model, pass_type, prompt, image_count)`.**

**Plan 24-09 MUST author its fixtures AFTER commit `7cbdf40`, never before.** A fixture authored
against the pre-24-07 prompt hashes to a key nothing will ever request, and the differential gate
would pass for having looked at nothing — the exact failure `test_phase23_acceptance.py` rule 3
forbids. This is 24-RESEARCH pitfall 6, and it is why 24-09 is last in the phase. Note also that
`image_count` is part of the key and Task 2 changed it on room-heavy sheets (Crow page 1: 1 → 5).

## Requirement Status

- **V4-DET-01** — the *prompt half* is delivered here (anchor on the chip, anchor in the hint,
  unanchored candidates never asked about, never named from shape). The *anchor primitive* came from
  24-01 and the *unnamed-geometry contract* from 24-04. Not ticked in `REQUIREMENTS.md`; the phase
  gate 24-10 is its closer.
- **V4-DET-03** — delivered in full by this plan (dependency-ordered schema, enum-only ID fields,
  omittable bounding-wall citation, zero numeric properties). Not ticked; 24-10 closes it.

`REQUIREMENTS.md` carries these as prose bullets with no checkboxes, consistent with how 24-01…24-06
left them, so nothing was mechanically marked.

## Next Phase Readiness

- **24-08 (ensemble wire-up)** is unblocked. It touches `_run_pass` call sites, not the schema or the
  prompts, so nothing here conflicts.
- **24-09 (determinism harness)** is unblocked *and now correctly sequenced* — its fixtures must be
  authored against the prompts as of `7cbdf40`. See the sequencing warning above.
- **24-10 (phase gate)** inherits two open items: the requirement ticks for V4-DET-01/03, and the
  in-tree synthetic-fixture regeneration logged in `deferred-items.md`.
- **Unmeasurable offline, by design.** The 0.03→0.65 figure is from published benchmarks on other
  datasets (assumption A3). Judge this plan on whether the anchor is present, correct and delimited
  — never on an accuracy percentage. The first honest measurement is a paid run, and it is not
  autonomously authorised.

## Self-Check: PASSED

- `src/bobbytailor/vision/overlay.py` FOUND · `src/bobbytailor/vision/schemas.py` FOUND ·
  `src/bobbytailor/vision/prompts.py` FOUND · `src/bobbytailor/pipeline/takeoff_pipeline.py` FOUND ·
  `tests/test_vision_schemas.py` FOUND
- `e7b648b` FOUND · `2b3e56a` FOUND · `7cbdf40` FOUND

---
*Phase: 24-binding-determinism-text-anchored-labeling*
*Completed: 2026-08-06 (interrupted after Task 2; closed out in a second session)*

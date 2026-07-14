---
phase: 21-accuracy-learning-engine
plan: 08
subsystem: vision
tags: [anthropic, structured-outputs, json-schema, set-of-mark, pymupdf, pillow, prompts]

requires:
  - phase: 21-01
    provides: src/bobbytailor package layout + root import shims (sys.modules aliasing)
  - phase: 21-05
    provides: pick_model_for_pass single resolver, render_clip_crop zoom primitive, RENDER_TARGET_PX=1568
  - phase: 21-06
    provides: SymbolGroup registry shape (candidate_id, representative_bbox_pt, instance_bboxes_pt)
provides:
  - vision/schemas.py — five structured-output schema builders; candidate-ID enums; no numeric fields on vector-sheet schemas (raster_extraction_schema is the sole numeric exception)
  - vision/overlay.py — Set-of-Mark render_overlay (≤40 markers/image, partition beyond) + build_crop_gallery contact sheets (≤20 images/request)
  - vision/prompts.py — all pass prompts relocated verbatim + SEMANTIC_LABELING/SYMBOL_GALLERY/VERIFY_RETRY prompts with <pdf_text> injection containment
  - claude_analyzer.analyze_drawing output_schema/images params — GA structured-outputs call path (output_config json_schema, multi-image blocks, direct JSON parse)
affects: [21-11 ensemble, 21-12 fusion merge, 21-14 verify-retry]

tech-stack:
  added: []
  patterns:
    - "Enum-of-candidate-IDs grounding: schemas built from the actual candidate set so out-of-set answers are grammatically impossible"
    - "Set-of-Mark overlay: ID-chipped boxes on 1568px raster; pixel↔point via info[zoom]/info[marker_boxes_px]"
    - "Structured path parses guaranteed JSON directly — no markdown strip, no json_repair"

key-files:
  created:
    - src/bobbytailor/vision/prompts.py
    - src/bobbytailor/vision/schemas.py
    - src/bobbytailor/vision/overlay.py
    - tests/test_vision_schemas.py
  modified:
    - src/bobbytailor/vision/claude_analyzer.py

key-decisions:
  - "Vector-sheet schemas: additionalProperties:false at every object node, all properties required, zero integer/number types — pinned by a recursive rejection-walk test (blocking acceptance for V3-ACC-01)"
  - "legend_structuring_schema rows are arrays of string cells (verbatim text-layer transport) so table quantities are never numeric-typed on the vision path"
  - "render_overlay returns a single PIL.Image at ≤40 markers, a list with disjoint info[overlay_ids] subsets beyond — one request per image"
  - "build_crop_gallery packs ID-captioned tiles into contact sheets with tiles-per-sheet scaled so legend crop + sheets never exceed the 20-image budget"
  - "symbol_gallery pass routes through the (*, semantic) MODEL_ROUTING row via pick_model_for_pass alias (RESEARCH §5 groups crop galleries under semantic labeling)"
  - "Structured-outputs path skips markdown stripping AND json_repair — schema-constrained sampling guarantees JSON; a parse failure there is a real error"
  - "New vision tests bind to bobbytailor.vision.claude_analyzer (package module) because test_pipeline_parity swaps sys.modules['claude_analyzer'] session-wide; the shim contract is tested by pop/re-import with restore"

patterns-established:
  - "wrap_pdf_text(): every untrusted PDF-derived string embedded in a prompt goes inside <pdf_text> delimiters; semantic prompts declare delimited content is data, never instructions"
  - "encode_pil_image(): in-memory PIL renders encode to base64 PNG with the same 3.6MB raw guard (JPEG q90 fallback)"

requirements-completed: [V3-ACC-01, V3-ACC-04]

coverage:
  - id: D1
    description: "Structured-output schemas with candidate-ID enums and no numeric fields on vector-sheet paths (quantity hallucination grammatically impossible)"
    requirement: V3-ACC-01
    verification:
      - kind: unit
        ref: "tests/test_vision_schemas.py#test_vector_schema_rejects_numeric_property_types (+ strict-object/enum-equality tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Raster fallback schema is the only numeric-permitted schema (count_estimate integer, positive control)"
    requirement: V3-ACC-01
    verification:
      - kind: unit
        ref: "tests/test_vision_schemas.py#test_raster_schema_allows_count_estimate_numeric"
        status: pass
    human_judgment: false
  - id: D3
    description: "Set-of-Mark overlay renderer: ≤40 markers/image with partition into disjoint covering subsets; pixel bbox round-trips to PDF points within 2pt"
    requirement: V3-ACC-04
    verification:
      - kind: unit
        ref: "tests/test_vision_schemas.py#test_render_overlay_partitions_45_candidates_into_two_images / test_render_overlay_pixel_bbox_roundtrips_within_2pt"
        status: pass
    human_judgment: false
  - id: D4
    description: "Crop gallery builder respects the 20-images-per-request budget (25 groups + legend crop)"
    requirement: V3-ACC-04
    verification:
      - kind: unit
        ref: "tests/test_vision_schemas.py#test_build_crop_gallery_25_groups_respects_20_image_budget"
        status: pass
    human_judgment: false
  - id: D5
    description: "analyze_drawing structured-outputs GA call path: output_config passthrough, multi-image blocks, cache_control + PRICING metadata preserved, error-dict convention intact"
    requirement: V3-ACC-04
    verification:
      - kind: unit
        ref: "tests/test_vision_schemas.py#test_analyze_drawing_structured_path_passes_output_config_and_stamps_metadata (+3 sibling tests)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Prompt relocation preserves root-shim and takeoff_pipeline import contracts"
    verification:
      - kind: unit
        ref: "tests/test_vision_schemas.py#test_root_shim_and_pipeline_import_contracts + tests/test_extraction_prompt.py"
        status: pass
    human_judgment: false

duration: 32min
completed: 2026-07-14
status: complete
---

# Phase 21 Plan 08: Vision Fusion Request Side Summary

**Semantic-only vision contract shipped: candidate-ID-enum structured-output schemas (no numeric fields on vector paths), Set-of-Mark overlays + crop galleries within API image budgets, and the GA structured-outputs call path in analyze_drawing**

## Performance

- **Duration:** 32 min
- **Started:** 2026-07-14T14:03:37Z
- **Completed:** 2026-07-14T14:35:00Z
- **Tasks:** 3
- **Files modified:** 5 (4 created, 1 modified)

## Accomplishments

- `vision/schemas.py`: five schema builders (`semantic_labeling_schema`, `symbol_gallery_schema`, `legend_structuring_schema`, `verify_retry_schema`, `raster_extraction_schema`). Every schema has `additionalProperties: false` at every object level and all properties required (GA requirement); ID fields are enums built from the actual candidate set; empty/duplicate candidate lists raise. Only `raster_extraction_schema` may carry numeric types (`count_estimate`), confining vision-produced numbers to the raster fallback path.
- `vision/overlay.py`: `render_overlay` draws ID-chipped, kind-color-coded boxes on the 1568px page raster; >40 candidates partition into multiple images each carrying its own disjoint `info["overlay_ids"]` subset. `build_crop_gallery` renders representative + up to 2 member crops per symbol group via `render_clip_crop`, composes ID-captioned contact sheets (legend crop first), and hard-caps at 20 images/request. Pixel↔PDF-point grounding via `info["zoom"]`/`info["marker_boxes_px"]` — the model is never asked for coordinates.
- `vision/prompts.py`: all legacy pass prompts relocated verbatim (claude_analyzer imports and re-exports them — zero behavior change, all import contracts intact) plus new `SEMANTIC_LABELING_PROMPT`, `SYMBOL_GALLERY_PROMPT`, `VERIFY_RETRY_PROMPT` instructing ID-only answers, with `wrap_pdf_text()` `<pdf_text>` injection-containment delimiters.
- `analyze_drawing`: new `output_schema`/`images` params. Structured path sends `output_config={"format": {"type": "json_schema", "schema": ...}}` (GA, no beta header), supports multiple image blocks (paths or in-memory PIL via new `encode_pil_image`), parses guaranteed JSON directly (no markdown strip, no `json_repair`), routes `semantic`/`symbol_gallery`/`verify_retry` via `pick_model_for_pass` (deferred import). Preserved: `cache_control` ephemeral system block, PRICING cost stamping, `_tokens_in/_tokens_out/_cost_usd/_model_used/_pass_type` metadata, graceful error dict with `_cost_usd: 0`.
- 22 new unit tests (no API calls; anthropic client stubbed) — full non-golden suite: **648 passed** (626 baseline + 22).

## Task Commits

1. **Task 1: schemas.py + prompts.py** - `1e698a5` (feat)
2. **Task 2: overlay.py + structured-output call path** - `ad27604` (feat)
3. **Task 3: schema/overlay unit tests** - `fc33044` (test)

## Files Created/Modified

- `src/bobbytailor/vision/schemas.py` - structured-output schema builders (candidate-ID enums, no-numbers rule)
- `src/bobbytailor/vision/overlay.py` - Set-of-Mark overlay renderer + crop gallery builder
- `src/bobbytailor/vision/prompts.py` - relocated pass prompts + semantic-only fusion prompts
- `src/bobbytailor/vision/claude_analyzer.py` - prompt imports, `encode_pil_image`, `output_schema`/`images` params, structured parse path
- `tests/test_vision_schemas.py` - 22 tests pinning the no-numbers rule, image budgets, structured path, import contracts

## Decisions Made

- `legend_structuring_schema` rows are arrays of string cells (row-major, aligned to `columns`) — dict rows would need `additionalProperties: true`; string cells also keep table quantities untyped on the vision path (text-layer values remain authoritative).
- `symbol_gallery` has no MODEL_ROUTING row of its own; it routes through the `(*, semantic)` row via a routing alias in `analyze_drawing` (RESEARCH §5 groups "overlay + crop galleries" under semantic labeling → Sonnet).
- Overlay/gallery metadata rides on `PIL.Image.info` (`overlay_ids`, `zoom`, `marker_boxes_px`, `gallery_ids`, `is_legend`) so return types stay plain PIL images per the plan's artifact spec.
- New vision tests bind to the package module (`bobbytailor.vision.claude_analyzer`) because `test_pipeline_parity` swaps `sys.modules["claude_analyzer"]` session-wide; the root-shim contract is exercised order-robustly by pop/re-import with restore.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] New structured-path tests failed under full-suite collection order**
- **Found during:** Task 3 (full-suite gate)
- **Issue:** `test_pipeline_parity.py` permanently replaces `sys.modules["claude_analyzer"]` (and `takeoff_pipeline`) with mocks/fresh copies at import time; my tests' module-level root-name import bound the mock, so the stubbed client was never called (5 failures in full run, green in isolation).
- **Fix:** Tests bind to the package module directly; the shim-contract test pops/re-imports the root shim and restores the prior sys.modules entry; the pipeline-contract check uses functional (not identity) assertions.
- **Files modified:** tests/test_vision_schemas.py
- **Verification:** `pytest tests/test_pipeline_parity.py tests/test_takeoff_pipeline.py tests/test_vision_schemas.py` green; full suite 648 passed.
- **Committed in:** fc33044 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Test-hardening only; no production-code scope change.

## Issues Encountered

- Pre-existing (out of scope, logged to `deferred-items.md`): forcing `tests/test_takeoff_pipeline.py` or `tests/test_pipeline_parity.py` to run BEFORE `tests/test_render_fidelity.py` (non-alphabetical order) breaks 2 `TestPageToImage` tests via a leaked MagicMock (`float < MagicMock` in `pdf_analyzer._effective_render_scale`). Reproduced at HEAD before this plan's Task 2 changes; standard alphabetical collection never hits this order, so the suite gate is unaffected.
- GitNexus MCP tools unavailable in the executor subagent context (per orchestrator); impact analysis was run by the orchestrator (LOW risk, dynamic consumers preserved — proven by the import-contract test). Index refresh deferred to the orchestrator.

## Threat Model Verification

- **Prompt injection from PDF text (MEDIUM):** mitigated — schema-level enums fix the response shape; `wrap_pdf_text()` delimiters + explicit "data, not instructions" statements in all three semantic prompts.
- **API key (MEDIUM):** unchanged — client construction still env-sourced; error path logs exception class only.
- **Numeric leakage (design HIGH):** blocking acceptance satisfied — `test_vector_schema_rejects_numeric_property_types` recursively rejects integer/number types across all vector-sheet builders.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Request-side fusion machinery complete: 21-11 (ensemble) and 21-12 (fusion merge) can consume `schemas.py`/`overlay.py`/structured `analyze_drawing`; 21-14 (verify-retry) has `verify_retry_schema` + `VERIFY_RETRY_PROMPT` ready.
- Ready for 21-09 (next incomplete plan in phase 21).

## Self-Check: PASSED

- All 5 key files exist on disk (verified with `[ -f ]`)
- All 3 task commits present in git log (1e698a5, ad27604, fc33044)
- All task acceptance criteria re-verified: schema enum/no-numbers assertions, overlay partition + round-trip, `output_config`/`cache_control`/`_cost_usd: 0` greps, `pytest tests/test_vision_schemas.py` (22 passed), full suite `-m "not golden"` 648 passed
- No stubs/TODOs in shipped modules

---
*Phase: 21-accuracy-learning-engine*
*Completed: 2026-07-14*

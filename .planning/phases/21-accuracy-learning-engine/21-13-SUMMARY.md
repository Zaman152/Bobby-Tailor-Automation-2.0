---
phase: 21-accuracy-learning-engine
plan: 13
subsystem: pipeline
tags: [deterministic-first, fusion, ensemble, budget-guard, provenance, run-settings, pytest]

# Dependency graph
requires:
  - phase: 21-07
    provides: solve_viewport_scale/select_main_plan/resolve_scale_v2 + segment_viewports (per-viewport RANSAC scale)
  - phase: 21-10
    provides: extract_walls/wall_lf_by_class + extract_rooms (Recipe B/C geometry)
  - phase: 21-11
    provides: BudgetGuard/BudgetExceeded/run_ensemble/vote/ensemble_settings (V3-ACC-03 + V3-PROD-02 guard)
  - phase: 21-12
    provides: fuse_sheet/merge_with_provenance/build_registry + ReplayAnalyzer harness
provides:
  - TakeoffPipeline deterministic-first production path — vector plan/schedule sheets measured by geometry/text; vision is semantic labeler only (V3-ACC-01 integrated)
  - RunSettings dataclass + from_env() (ENSEMBLE_N/API_BUDGET_PER_RUN_USD via ensemble_settings single reader; env boolean toggles) — parity foundation for 21-15
  - is_vector_sheet(page) RESEARCH §2 raster heuristic (<200 paths AND <100 words)
  - Raster fallback path — run_ensemble-wrapped raster_extraction_schema estimate, per-item voting, measurement_mode="raster", everything ≤ medium
  - One BudgetGuard per run threaded through EVERY vision call site; exhaustion flags remaining work "budget_exhausted" (never silent partial)
  - Reporter surfacing — takeoff.json measurement_mode/scale_confidence/provenance/budget/fusion_rejected; summary.txt SCALE CONFIDENCE + PROVENANCE BREAKDOWN sections
affects: [21-14 verify-retry, 21-15 parity, 21-16 learning retrieval, 21-17 accuracy gate, reporter, web reports]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deterministic-first routing: _DETERMINISTIC_SHEET_TYPES (plan types + schedule) with pdf page → vector/raster branch; everything else legacy vision passes"
    - "Budget charging convention: charge the completed call's _cost_usd; a refused charge discards the result — the ledger only holds paid-and-accepted work"
    - "Lazy overlay wrappers (_render_overlay/_build_crop_gallery) break the overlay→pdf_analyzer→takeoff_pipeline import cycle while staying patchable"
    - "py3.9 + PEP 563 + spec-loaded modules: dataclasses built over real type-object __annotations__ (string annotations need sys.modules[cls.__module__])"

key-files:
  created:
    - tests/test_pipeline_deterministic.py
  modified:
    - src/bobbytailor/pipeline/takeoff_pipeline.py
    - src/bobbytailor/pipeline/pdf_analyzer.py
    - src/bobbytailor/pipeline/reporter.py
    - tests/test_reporter_accuracy.py

key-decisions:
  - "Deterministic-first branch scope: floor_plan/civil_site/roof_plan + schedule; elevations/details/MEP keep legacy vision passes (wall pairing on elevations would produce bogus geometry-provenance LF — worse than vision)"
  - "Raster ensemble branch applies to plan types only; raster schedule sheets keep the legacy vision schedule pass (raster schema has no row structure)"
  - "Vector schedule sheet with zero find_tables results falls back to the legacy vision schedule pass (RESEARCH §3 handoff 4: vision reconciles layout when the table finder fails)"
  - "Deterministic select_main_plan is the measurement authority; the vision main_plan_region answer is a semantic cross-check kept as main_plan_region_vision on disagreement"
  - "Deterministic ScheduleTables attach as _deterministic_schedules metadata, NOT 'schedules' — rows are already fused into schedule_table-provenance components; attaching both would double-count through calculator"
  - "run_sheet standalone (scraper path) creates a per-sheet BudgetGuard when no run guard is threaded — no vision call site is ever unguarded; 21-15 threads the run-level guard"
  - "Raster votes: unanimous across ALL valid samples → medium (capped, never high — estimates), anything else → low + needs_review; full vote vectors persisted per item"
  - "page_text_enrichment skipped on vector/raster branches — fused output is complete and enrichment could inject provenance-less items"

patterns-established:
  - "measurement_mode ('vector'|'raster'|absent-legacy) on every routed sheet result — consumed by reporter and the 21-17 accuracy gate"
  - "scale_confidence: per-viewport ViewportScale.to_dict list with region_id/kind/is_main — the report/UI scale-trust surface"

requirements-completed: [V3-ACC-01, V3-ACC-03]

coverage:
  - id: D1
    description: "Deterministic-first vector orchestration: dimensions → viewports → RANSAC scale → main-plan → walls/rooms/symbols/tables → overlay/gallery semantic passes → fuse_sheet → merge_with_provenance; no vision quantity possible on a vector sheet"
    requirement: V3-ACC-01
    verification:
      - kind: integration
        ref: "tests/test_pipeline_deterministic.py#test_vector_sheet_no_vision_ensemble_quantities (Crow p0 end-to-end)"
        status: pass
      - kind: integration
        ref: "tests/test_pipeline_deterministic.py#test_vector_sheet_vision_saw_only_semantic_passes"
        status: pass
      - kind: integration
        ref: "tests/test_pipeline_deterministic.py#test_vector_sheet_scale_confidence_main_plan_fpi_40"
        status: pass
    human_judgment: false
  - id: D2
    description: "Raster fallback: run_ensemble-wrapped raster extraction, N invocations, per-item voting, all quantities ≤ medium and flagged unless unanimous, measurement_mode='raster'"
    requirement: V3-ACC-03
    verification:
      - kind: unit
        ref: "tests/test_pipeline_deterministic.py#test_raster_sheet_runs_ensemble_n_times_all_flagged"
        status: pass
      - kind: unit
        ref: "tests/test_pipeline_deterministic.py#test_raster_force_overrides_vector_detection"
        status: pass
    human_judgment: false
  - id: D3
    description: "One BudgetGuard per run charged at every vision call site; exhaustion mid-run flags remaining sheets/items 'budget_exhausted' and the run completes (never silent partial)"
    requirement: V3-ACC-03
    verification:
      - kind: integration
        ref: "tests/test_pipeline_deterministic.py#test_budget_exhaustion_mid_run_flags_remaining"
        status: pass
      - kind: unit
        ref: "tests/test_pipeline_deterministic.py#test_vector_sheet_budget_and_audit_metadata"
        status: pass
    human_judgment: false
  - id: D4
    description: "Reporter surfaces per-item provenance, per-viewport scale confidence, run-level budget block, fusion_rejected audit; SCALE CONFIDENCE + PROVENANCE BREAKDOWN summary sections; pre-21 reports render unchanged"
    requirement: V3-ACC-01
    verification:
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_takeoff_json_carries_measurement_mode_scale_confidence_provenance"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_summary_txt_has_scale_confidence_and_provenance_sections"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_pre21_report_renders_without_new_fields"
        status: pass
    human_judgment: false
  - id: D5
    description: "RunSettings dataclass shared by both entry points; from_env honors ENSEMBLE_N/API_BUDGET_PER_RUN_USD via ensemble_settings + boolean env flags"
    requirement: V3-ACC-03
    verification:
      - kind: unit
        ref: "tests/test_pipeline_deterministic.py#test_run_settings_from_env_honors_ensemble_n_and_budget"
        status: pass
      - kind: unit
        ref: "tests/test_pipeline_deterministic.py#test_run_settings_from_env_boolean_flags"
        status: pass
    human_judgment: false

# Metrics
duration: 40min
completed: 2026-07-14
status: complete
---

# Phase 21 Plan 13: Pipeline Integration Summary

**Deterministic-first TakeoffPipeline (V3-ACC-01/03 integrated): vector plan sheets now flow dimensions → viewports → RANSAC scale → walls/rooms/symbols/tables → ID-grounded semantic vision → fuse_sheet, raster sheets get ensemble-voted estimates, one BudgetGuard covers every vision call, and reports surface per-item provenance + per-viewport scale confidence — Crow p0 measures at 1"=40' HIGH confidence with 71 components and zero vision quantities, fully offline-tested (760 green).**

## Performance

- **Duration:** 40 min
- **Started:** 2026-07-14T16:58:40Z
- **Completed:** 2026-07-14T17:39:02Z
- **Tasks:** 3
- **Files modified:** 5 (1 created)

## Accomplishments

- **Deterministic-first vector branch** in `TakeoffPipeline.run_sheet`: for plan/schedule sheets with a source PDF page, the pipeline builds the deterministic bundle (schedules → viewports → dimension samples → per-viewport `solve_viewport_scale` with the printed cross-check chain → `select_main_plan` → `resolve_scale_v2` → walls/rooms/symbols/footprint), renders Set-of-Mark overlays and crop galleries, runs the semantic/gallery structured-output passes (candidate-ID enums — quantities grammatically impossible), then `fuse_sheet` → `merge_with_provenance`. QuantityVerifier flags on the fused result feed 21-14 verify-retry. Smoke truth on Crow p0: main plan R1 at 1"=40.0' HIGH (30 inliers, 89% share, printed ✓), 69 geometry + 2 text_layer components including the 136-instance column group, zero `vision_ensemble` quantities.
- **RunSettings** dataclass (deterministic flags, ensemble N, learning toggle, budget, verify-retry, raster_force) with `from_env()` built on the `ensemble_settings()` single reader (21-11 decision). `TakeoffPipeline(analyzer=None, settings=None)` defaults to `from_env()` so the scraper's module-level singleton keeps working unchanged; pdf_analyzer constructs explicitly from the same settings (parity foundation for 21-15).
- **Raster fallback path**: `is_vector_sheet` false (or `raster_force`) on a plan sheet → the extraction is wrapped in `run_ensemble` (N=`settings.ensemble_n`) with `raster_extraction_schema`, per-item voting over the sample vector, `measurement_mode="raster"`, unanimous → medium (never high), anything else low + `needs_review`, full vote vectors persisted.
- **Budget threading (threat model HIGH item)**: `run_project` creates one `BudgetGuard(settings.budget_usd)` per run; EVERY vision call site charges it — legacy count/measure/schedule/legend passes, the multi-region legend retry, tiled recount, semantic overlay, symbol gallery, and every raster ensemble sample. Refused charges discard the result; exhaustion flags remaining sheets/items `budget_exhausted` and the run continues to reporting.
- **Reporter surfacing**: takeoff.json gains per-sheet `measurement_mode`/`scale_confidence`/`main_plan_region`, per-item `provenance` on raw component rows (+ CSV column), a run-level `budget` block `{cap_usd, spent_usd, exhausted}`, and the aggregated `fusion_rejected` audit list; summary.txt gains SCALE CONFIDENCE and PROVENANCE BREAKDOWN sections (the geometry/text-derived share is the ≥97% accuracy-gate number) and a Budget line under API USAGE. All None-guarded — pre-21 reports render without KeyError (regression-pinned).
- **17 offline pipeline tests** (`tests/test_pipeline_deterministic.py`) + 3 reporter tests: Crow p0 end-to-end with canned schema-grounded analyzers, the pipeline-level provenance invariant, raster ensemble N-fan-out/vote rules, budget exhaustion mid-run, RunSettings env plumbing, `is_vector_sheet` threshold matrix.

## Task Commits

Each task was committed atomically:

1. **Task 1: RunSettings + deterministic-first orchestration** - `7ad2280` (feat)
2. **Task 2: Reporter surfacing — provenance, scale confidence, budget** - `3943a7d` (feat)
3. **Task 3: Pipeline-level replay tests** - `91e6490` (test)

## Files Created/Modified

- `src/bobbytailor/pipeline/takeoff_pipeline.py` - RunSettings, is_vector_sheet, vector/raster routing, deterministic bundle builder, semantic/gallery structured calls, budget threading (+~1,000 lines)
- `src/bobbytailor/pipeline/pdf_analyzer.py` - constructs the pipeline from shared `RunSettings.from_env()`
- `src/bobbytailor/pipeline/reporter.py` - provenance/scale-confidence/budget/fusion_rejected surfacing in takeoff.json + summary.txt sections
- `tests/test_pipeline_deterministic.py` - 17 offline layer-3 pipeline tests
- `tests/test_reporter_accuracy.py` - 3 new surfacing/regression tests

## Decisions Made

- Deterministic-first branch scope is plan types + schedule sheets; elevations/details/MEP keep the legacy vision passes — running the wall pairer on elevation linework would inject bogus geometry-provenance LF, which is worse than a flagged vision estimate.
- Deterministic `select_main_plan` is the measurement authority; the vision `main_plan_region` answer is retained only as a cross-check (`main_plan_region_vision` on disagreement).
- Deterministic ScheduleTables ride as `_deterministic_schedules` metadata rather than `schedules` — their rows already become `schedule_table`-provenance components in `fuse_sheet`, and attaching both would double-count through `_calculate_from_schedule`.
- Standalone `run_sheet` (scraper path) gets a per-sheet BudgetGuard when no run-level guard is threaded, so no vision call site is ever unguarded (21-15 threads the run-level guard through that path).
- Symbol gallery pass runs only when deterministic legend labels exist (schedule-row names); with none, symbol groups keep their exact deterministic counts flagged unlabeled (flag-don't-guess) rather than being matched against a fabricated label enum.
- Overlay renderers are lazy module-level wrappers (`_render_overlay` / `_build_crop_gallery`): `overlay.py` imports `pdf_analyzer` which imports `takeoff_pipeline`, so a direct module-level import would deadlock the shim import cycle.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan's Crow main-plan "fpi ≈ 20" acceptance was the stale research note**
- **Found during:** Task 3 (vector end-to-end test)
- **Issue:** The plan's test spec pinned Crow p0 main-plan fpi ≈ 20, but the hand-verified truth table (`tests/fixtures/crow_cass/scale_truth.json`) and the 21-07 STATE decision establish 1"=40' (1136' spans 2058pt on a 3024pt sheet — 20 fpi is geometrically impossible; the 1"=20' scale exists only on page-1 elevations).
- **Fix:** Test asserts fpi ≈ 40 (±2%) with the correction documented in the test module docstring.
- **Files modified:** tests/test_pipeline_deterministic.py
- **Verification:** `test_vector_sheet_scale_confidence_main_plan_fpi_40` passes; solved value 40.0 HIGH with printed agreement.
- **Committed in:** `91e6490`

**2. [Rule 3 - Blocking] Python 3.9 dataclass failure under spec-loaded modules**
- **Found during:** Task 1 (existing test suite gate)
- **Issue:** `tests/test_takeoff_pipeline.py` loads `takeoff_pipeline` via `importlib.util` WITHOUT registering it in `sys.modules`; with `from __future__ import annotations`, py3.9's dataclass machinery resolves string annotations via `sys.modules[cls.__module__]` → `AttributeError: 'NoneType' object has no attribute '__dict__'` at class-decoration time.
- **Fix:** `RunSettings` is defined with plain class attributes, an explicit `__annotations__` dict of real type objects, and the `dataclass()` decorator applied afterwards — string-annotation resolution never triggers; it remains a true dataclass (asdict/fields work).
- **Files modified:** src/bobbytailor/pipeline/takeoff_pipeline.py
- **Verification:** `tests/test_takeoff_pipeline.py` + `tests/test_pipeline_parity.py` 54 passed.
- **Committed in:** `7ad2280`

**3. [Rule 3 - Blocking] Circular import via overlay module**
- **Found during:** Task 1 (import design)
- **Issue:** `bobbytailor.vision.overlay` imports `bobbytailor.pipeline.pdf_analyzer` (render_clip_crop), which imports `takeoff_pipeline` — a module-level overlay import in takeoff_pipeline would raise "partially initialized module" on the first production import through the root shims.
- **Fix:** Lazy module-level wrapper functions `_render_overlay` / `_build_crop_gallery` (patchable in tests; sanctioned PATTERNS "lazy imports to break cycles").
- **Files modified:** src/bobbytailor/pipeline/takeoff_pipeline.py
- **Verification:** Full suite import-clean under every collection order; Crow smoke run renders overlays.
- **Committed in:** `7ad2280`

---

**Total deviations:** 3 auto-fixed (1 bug, 2 blocking)
**Impact on plan:** All fixes necessary for correctness (verified scale truth) and importability on the py3.9 deployment runtime. No scope creep — every plan artifact and acceptance criterion delivered.

## Issues Encountered

- Synthetic fixture PDFs (`tests/fixtures/synthetic/*.pdf`) regenerated as a known test side effect and were restored before every commit.

## Known Stubs

- `RunSettings.learning_enabled` and `RunSettings.verify_retry_enabled` are carried configuration (plan-specified fields) whose consumers land in 21-14 (verify-retry) and 21-16 (learning retrieval) — intentional forward plumbing, not unwired data paths. All quantities in this plan's output flow from deterministic inputs or flagged ensemble votes; no placeholder values or TODO markers.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- "Geometry proposes, vision disposes" is now the production data flow: `run_pdf_analysis` (and the scraper path when per-page PDF blobs exist) routes vector plan sheets through the deterministic engine automatically.
- 21-14 (verify-retry) has its hooks: `_verifier_flags` on fused results, `RunSettings.verify_retry_enabled`, `_structured_vision_call` + BudgetGuard for bounded arbitration crops.
- 21-15 (parity) has `RunSettings` shared construction and the standalone-run_sheet per-sheet-guard note to replace with run-level threading.
- 21-17 (accuracy gate) can read per-item `provenance` from takeoff.json raw_line_items and the PROVENANCE BREAKDOWN deterministic share.
- Full non-golden suite green: 760 passed (740 baseline + 20 new), zero API calls, `test_pipeline_parity.py` untouched.

## Self-Check: PASSED

- `src/bobbytailor/pipeline/takeoff_pipeline.py` — contains `class RunSettings`, `def is_vector_sheet(`, `BudgetGuard`, and all eight vector-flow calls (extract_dimension_samples, segment_viewports, solve_viewport_scale, extract_walls, extract_rooms, cluster_symbols, extract_schedules, fuse_sheet)
- `src/bobbytailor/pipeline/reporter.py` — contains `SCALE CONFIDENCE` and `PROVENANCE BREAKDOWN` literals
- `tests/test_pipeline_deterministic.py` — FOUND, 17 tests passing (≥6 required)
- Commit `7ad2280` — FOUND
- Commit `3943a7d` — FOUND
- Commit `91e6490` — FOUND
- `python3 -m pytest tests/test_pipeline_deterministic.py -q` — 17 passed
- `python3 -m pytest -q -m "not golden"` — 760 passed, 2 deselected

---
*Phase: 21-accuracy-learning-engine*
*Completed: 2026-07-14*

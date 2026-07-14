---
phase: 21-accuracy-learning-engine
plan: 16
subsystem: learning
tags: [sqlite, learning-store, retrieval, prompt-injection, anti-amplification, aggregation, scale-prior]

requires:
  - phase: 21-04
    provides: learning store read APIs (get_vocabulary/get_assumptions/get_manifest/get_corrections) + specificity precedence
  - phase: 21-07
    provides: resolve_scale_v2 learned_prior parameter (already ranked last)
  - phase: 21-09
    provides: capture endpoints writing corrections + distill (the data this plan retrieves)
  - phase: 21-14
    provides: verify-retry pipeline state this plan's flags coexist with
provides:
  - learning/retrieval.py — LearnedContext bundle (vocabulary/assumptions/expected_items/quantity_corrections) + load_learned_context with repeat-run project_type inference
  - render_prompt_hint — expected-items + naming-conventions block in <pdf_text> delimiters, 2000-char capped, cold-start silent
  - aggregator.normalize_item_name learned-vocabulary lookup BEFORE ITEM_NAME_MAP (static map = cold-start floor, order untouched)
  - calculator wall_height_source threading — derived wall areas stamped assumption_source (manifest|learned|default)
  - pipeline learned scale-prior feed at the resolve_scale_v2 call site (scale_fpi:<sheet> then scale_fpi:*)
  - apply_learned_quantity_flags — RESEARCH §6 anti-amplification guardrail (re_verify flags, never substitution; geometry/text_layer HIGH untouchable)
  - entry-point parity — scraper (scrape + analyze-only paths) and pdf_analyzer both load learning at run start and thread it to reports
affects: [21-17, 21-18, verify-work, accuracy-gate]

tech-stack:
  added: []
  patterns:
    - "Two-stage run retrieval: load_learning(project_key) at run start (type inferred from prior corrections), refreshed once after _detect_project_type — never per-sheet DB churn"
    - "Learning is best-effort everywhere: retrieval/hint/flag failures log and leave the run learning-free (21-09 convention)"
    - "Naming precedence in aggregation: companion legend > manifest > learned > static ITEM_NAME_MAP"

key-files:
  created:
    - src/bobbytailor/learning/retrieval.py
    - tests/test_learning_retrieval.py
  modified:
    - src/bobbytailor/pipeline/takeoff_pipeline.py
    - src/bobbytailor/pipeline/aggregator.py
    - src/bobbytailor/pipeline/calculator.py
    - src/bobbytailor/pipeline/pdf_analyzer.py
    - src/bobbytailor/pipeline/reporter.py
    - src/bobbytailor/scrape/scraper.py

key-decisions:
  - "Two-stage retrieval: project_type inferred from the project's most recent prior correction (any scope) at run start, then refreshed with the detected type before calculator/aggregation — repeat runs get type-level vocabulary in prompts with zero manifests"
  - "apply_learned_quantity_flags lives in retrieval.py and runs inside run_sheet on every exit path (vector, raster, legacy) so BOTH entry points inherit the guardrail without duplication"
  - "identical_inputs=True substitution path (§6 re-run exception) is API-complete but dormant — production never asserts input identity; geometry/text_layer HIGH stays protected even there"
  - "Aggregated rows whose NAME came from vocabulary carry source='learned' (naming provenance only); quantity provenance is never altered by aggregation"
  - "Hint cap drops whole lines, never slices strings — a truncated </pdf_text> delimiter would break injection containment"
  - "Scraper wall-height parity: _resolve_wall_height(manifest, learned) now threads manifest AND learned heights on the StackCT path (apply_estimation_tables previously ran with the bare 9.0 default there)"

patterns-established:
  - "Learned assumption read shape: get_assumption(key) -> {value, weight, specificity} with specificity in {project_key, project_type, global}"
  - "assumption_source stamping: any derived quantity embedding an assumption names its source — assumptions are never silent"

requirements-completed: [V3-LEARN-02, V3-LEARN-03, V3-LEARN-04]

coverage:
  - id: D1
    description: "LearnedContext bundle retrieved by (project_key, project_type) with cold-start silence and repeat-run project_type inference"
    requirement: V3-LEARN-03
    verification:
      - kind: unit
        ref: "tests/test_learning_retrieval.py#test_context_cold_start_is_silent"
        status: pass
      - kind: unit
        ref: "tests/test_learning_retrieval.py#test_context_infers_project_type_on_repeat_run"
        status: pass
    human_judgment: false
  - id: D2
    description: "Learned vocabulary supersedes ITEM_NAME_MAP lookups with the static floor and its ordering intact"
    requirement: V3-LEARN-02
    verification:
      - kind: unit
        ref: "tests/test_learning_retrieval.py#test_vocabulary_application_in_aggregation"
        status: pass
      - kind: unit
        ref: "tests/test_learning_retrieval.py#test_learned_lookup_never_reorders_static_map"
        status: pass
    human_judgment: false
  - id: D3
    description: "Anti-amplification guardrail: geometry/text_layer HIGH quantities survive contradicting learned values unchanged (unit + canned pipeline run)"
    requirement: V3-LEARN-04
    verification:
      - kind: unit
        ref: "tests/test_learning_retrieval.py#test_anti_amplification_high_geometry_quantity_unchanged"
        status: pass
      - kind: integration
        ref: "tests/test_learning_retrieval.py#test_anti_amplification_in_canned_pipeline_run"
        status: pass
    human_judgment: false
  - id: D4
    description: "Learned scale prior fires only when the solver returned none; learned wall height only without a manifest source, always flagged"
    requirement: V3-LEARN-04
    verification:
      - kind: unit
        ref: "tests/test_learning_retrieval.py#test_learned_scale_prior_used_only_at_low_confidence"
        status: pass
      - kind: unit
        ref: "tests/test_learning_retrieval.py#test_learned_wall_height_applied_when_no_deterministic_source"
        status: pass
    human_judgment: false
  - id: D5
    description: "Repeat run of a verified project applies its vocabulary and hints automatically with zero manifest files (roadmap success criterion 4)"
    requirement: V3-LEARN-03
    verification:
      - kind: integration
        ref: "tests/test_learning_retrieval.py#test_repeat_run_applies_learned_vocabulary_and_hints"
        status: pass
    human_judgment: false
  - id: D6
    description: "Prompt-injection containment: hostile learned strings render inside <pdf_text> delimiters, hint hard-capped at 2000 chars"
    requirement: V3-LEARN-04
    verification:
      - kind: unit
        ref: "tests/test_learning_retrieval.py#test_hint_injection_safety_delimited_and_capped"
        status: pass
    human_judgment: false

duration: 38min
completed: 2026-07-14
status: complete
---

# Phase 21 Plan 16: Learning Retrieval & Injection Summary

**Closed the learning loop: LearnedContext retrieved once per run and injected at prompts/aggregation/calculator with the RESEARCH §6 anti-amplification guardrail proven — geometry/text_layer HIGH quantities are structurally unpoisonable, and a repeat run picks up its corrections with zero manifest files.**

## Performance

- **Duration:** 38 min
- **Started:** 2026-07-14T18:55:15Z
- **Completed:** 2026-07-14T19:33:11Z
- **Tasks:** 3
- **Files modified:** 8 (2 created, 6 modified)

## Accomplishments

- `learning/retrieval.py`: `LearnedContext` + `load_learned_context(project_key, project_type)` — one query bundle via 21-04 store read APIs only (grep-verified: no sqlite3 import). Repeat runs infer their `project_type` from the project's most recent prior correction, so type-level vocabulary/expected items reach the prompts at run start.
- Three injection seams live in both entry points (StackCT scrape + analyze-only + PDF upload):
  1. **Prompts** — `render_prompt_hint()` joins the count/measure `user_hint` slot; hostile strings stay inside `<pdf_text>` delimiters; 2000-char cap drops lines, never slices delimiters; cold start renders None (behavior identical to pre-learning).
  2. **Aggregation** — `normalize_item_name(..., learned=)` consults learned vocabulary before the ITEM_NAME_MAP regex loop; 20-05/20-09 ordering decisions proven undisturbed; learned-named rows marked `source: "learned"`.
  3. **Calculator/scale** — `_resolve_wall_height` (manifest > learned > 9 ft default) with `assumption_source` stamped on derived wall areas; `resolve_scale_v2(..., learned_prior=...)` fed from `scale_fpi:<sheet>`/`scale_fpi:*` assumptions (21-07 already ranks it last; scale_solver.py untouched).
- Anti-amplification guardrail (V3-LEARN-04 safety half): `apply_learned_quantity_flags` attaches `re_verify` flags for previously corrected items on every `run_sheet` exit path — never substitutes; geometry/text_layer HIGH protected even under the §6 identical-input exception (which is API-complete but dormant in production).
- 17 new layer-4 tests including the BLOCKING quantity-equality-before/after assertion and the repeat-run integration test (roadmap success criterion 4 at test level).

## Task Commits

1. **Task 1: retrieval.py — LearnedContext + renderers** - `e403b50` (feat)
2. **Task 2: Three injection seams + guardrail** - `ee52a52` (feat)
3. **Task 3: Retrieval + guardrail + repeat-run tests** - `6cea924` (test)
4. **Must-have pattern fix (aggregator comment)** - `d11792a` (docs)

## Files Created/Modified

- `src/bobbytailor/learning/retrieval.py` — LearnedContext bundle, load_learned_context, apply_learned_quantity_flags (435 lines)
- `tests/test_learning_retrieval.py` — 17 layer-4 tests (context, vocabulary, guardrail, scale prior, wall height, repeat run, injection safety)
- `src/bobbytailor/pipeline/takeoff_pipeline.py` — load_learning/two-stage retrieval, hint join, scale-prior feed, per-sheet guardrail flags, `_resolve_wall_height`, `_learned_scale_prior`
- `src/bobbytailor/pipeline/aggregator.py` — learned lookup before ITEM_NAME_MAP; learned= threading; source="learned" marking
- `src/bobbytailor/pipeline/calculator.py` — wall_height_source threading; assumption_source stamping on derived wall areas
- `src/bobbytailor/pipeline/pdf_analyzer.py` — project_key into run_project; learned into generate_report
- `src/bobbytailor/pipeline/reporter.py` — learned= passthrough to aggregate_takeoff
- `src/bobbytailor/scrape/scraper.py` — run-start + post-detection load_learning on both paths; learned wall height + report threading (parity)

## Decisions Made

- **Two-stage retrieval** — project_type is unknown at run start (the detector needs extracted sheets), so stage 1 infers it from the project's latest prior correction (any scope) and stage 2 refreshes with the detected type before calculator/aggregation. Retrieval stays run-level (2 queries/run max), never per-sheet.
- **Guardrail placement in run_sheet** — `apply_learned_quantity_flags` runs on every run_sheet exit (vector/raster/legacy), so the scraper's per-sheet call pattern inherits it identically to run_project without duplication.
- **Naming precedence** — companion legend > manifest > learned > static map: explicit user inputs for THIS run outrank accumulated learning; the static map is never deleted or reordered.
- **Dormant substitution path** — `identical_inputs=True` implements the §6 re-run exception for API completeness, but no production caller asserts input identity today; geometry/text_layer HIGH is excluded even there (the must_have "NEVER" is absolute).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Entry-point wiring beyond the plan's files_modified list**
- **Found during:** Task 2
- **Issue:** The plan's `files_modified` lists only retrieval/pipeline/aggregator/calculator/tests, but aggregation happens in `reporter.generate_report` and the StackCT entry point (`scraper.py`) never calls `run_project` — without wiring them, V3-LEARN-03 ("corrections retrieved and injected on new runs") would only work for half of one entry point, violating the LOCKED entry-point-parity context decision.
- **Fix:** `reporter.generate_report(learned=)` passthrough to `aggregate_takeoff`; `pdf_analyzer` passes `project_key` + `learned`; `scraper` loads learning at run start and after type detection on both the scrape and analyze-only paths, and threads learned wall height + report context.
- **Files modified:** src/bobbytailor/pipeline/reporter.py, src/bobbytailor/pipeline/pdf_analyzer.py, src/bobbytailor/scrape/scraper.py
- **Verification:** tests/test_scraper_* + tests/test_reporter_accuracy.py + full suite green
- **Committed in:** ee52a52 (Task 2 commit)

**2. [Rule 1 - Bug] project_type inference limited to quantity corrections**
- **Found during:** Task 3
- **Issue:** Initial implementation inferred a repeat run's project_type only from scope='item' corrections; a project verified solely via renames/scale fixes would never recover its type at run start.
- **Fix:** `load_learned_context` scans recent corrections of ALL scopes for inference; quantity flags still filter scope='item' client-side.
- **Files modified:** src/bobbytailor/learning/retrieval.py
- **Verification:** test_context_infers_project_type_on_repeat_run + full suite
- **Committed in:** 6cea924 (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 bug)
**Impact on plan:** Both required for the plan's own success criteria (V3-LEARN-03 end-to-end + LOCKED parity). No scope creep beyond closing the seams the plan describes.

## Issues Encountered

- **Pre-existing test-order pollution (out of scope, logged):** forced non-alphabetical orders `test_pipeline_parity.py → test_learning_capture.py` (9 fixture errors) and `→ test_confidence_flagging.py` (3 failures) reproduce at the pre-21-16 commit `ea60f2e` (verified via a scratch worktree, since removed). Cause: module-level `sys.modules` stomps in the parity test. Canonical alphabetical collection never hits these orders — full suite green. Logged in `deferred-items.md` for a test-hygiene pass.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Learning loop is closed: capture (21-09) → distill (21-04) → retrieval + injection (this plan) — repeat runs demonstrably apply corrections (roadmap success criterion 4).
- 21-17/21-18 (accuracy gate / UAT) can rely on `re_verify` flags, `assumption_source`, and `source: "learned"` markers in reports.
- Full non-golden suite: **806 passed** (789 baseline + 17 new).

## Self-Check: PASSED

- Created files exist on disk (retrieval.py, test_learning_retrieval.py)
- All 4 task commits present in git log (e403b50, ee52a52, 6cea924, d11792a)
- Acceptance re-run: tests/test_learning_retrieval.py + tests/test_aggregator.py → 26 passed
- Full non-golden suite → 806 passed (baseline 789 + 17 new)

---
*Phase: 21-accuracy-learning-engine*
*Completed: 2026-07-14*

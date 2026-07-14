---
phase: 21-accuracy-learning-engine
plan: 12
subsystem: vision
tags: [fusion, provenance, candidate-id, set-of-mark, record-replay, pytest]

# Dependency graph
requires:
  - phase: 21-06
    provides: SymbolGroup.candidate_id + instance_bboxes_pt (deterministic EA counts); ScheduleTable rows
  - phase: 21-08
    provides: candidate-ID enum schemas + render_overlay/build_crop_gallery (the answers fuse_sheet consumes)
  - phase: 21-10
    provides: WallSegment thickness classes (WALL-TCn) + RoomPolygon candidate IDs + wall_lf_by_class
provides:
  - PROVENANCE_RANK enum (geometry > text_layer > schedule_table > learned > vision_ensemble) on every component
  - merge_with_provenance — provenance-ranked dedup with a hard vision-cannot-overwrite-deterministic guard + fusion_rejected audit list
  - fuse_sheet + build_registry — vision ID→label answers applied to deterministic candidates; quantities always deterministic
  - ReplayAnalyzer record/replay harness (tests/replay_analyzer.py) — offline fusion testing via TakeoffPipeline(analyzer=...)
  - tests/fixtures/replay/ fixture directory (VALIDATION Wave 0 record/replay requirement)
affects: [21-13 pipeline integration, 21-14 verify-retry, 21-15 parity, 21-17 accuracy gate, aggregator, reporter]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Provenance rank replaces count-pass-wins: merge collisions resolved by PROVENANCE_RANK, then confidence, then first-seen"
    - "Hard guard on provenance STRINGS (not rank arithmetic): vision_ensemble can never displace deterministic quantity/unit"
    - "fusion_rejected audit list: rejected quantity claims and out-of-registry IDs are recorded, never silently dropped"
    - "Record/replay fixtures keyed by SHA256(model, pass_type, prompt text, image_count)"

key-files:
  created:
    - src/bobbytailor/vision/fusion.py
    - tests/replay_analyzer.py
    - tests/test_fusion.py
    - tests/fixtures/replay/.gitkeep
  modified: []

key-decisions:
  - "Hard no-overwrite guard checks provenance strings directly, independent of rank arithmetic — a future PROVENANCE_RANK edit cannot silently weaken the invariant"
  - "fuse_sheet quantities are exclusively deterministic: symbol group count, wall class LF, room polygon SF, schedule cells, printed footprint dims"
  - "Room vision labels apply ONLY to label_source=='none' rooms; override attempts on text-bound labels audited as label_override_blocked"
  - "Rooms with no scale bound (fpp<=0) emit quantity=None + needs_review (flag-don't-guess), never a guessed number"
  - "ReplayAnalyzer lazy-import results validated as real strings so sys.modules MagicMock stubs (parity tests) degrade to the deterministic 'unrouted' fallback"
  - "Record mode gated by REPLAY_RECORD=1 env (or explicit record=True) — never active in CI (fixture-poisoning threat)"

patterns-established:
  - "Provenance enum on every component dict: consumed by aggregator/reporter in 21-13"
  - "build_registry(bundle) is the canonical candidate-ID → {bbox_pt, kind} constructor for grounding validation"

requirements-completed: [V3-ACC-01]

coverage:
  - id: D1
    description: "Provenance-ranked merge (merge_with_provenance): higher rank wins, equal rank → confidence → first-seen; missing provenance defaults to vision_ensemble; hard guard blocks vision from overwriting/filling deterministic quantities; CMU 17-vs-2204 regression pinned"
    requirement: V3-ACC-01
    verification:
      - kind: unit
        ref: "tests/test_fusion.py#test_merge_precedence_matrix (10 pair params, both orders)"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_cmu_17_vs_2204_regression"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_vision_cannot_fill_null_deterministic_quantity"
        status: pass
    human_judgment: false
  - id: D2
    description: "fuse_sheet ID-grounded label application: symbol/wall/room/schedule/footprint assembly with deterministic quantities only; out-of-registry IDs (SYM-999) dropped + flagged; ID-grounding round-trip through render_overlay"
    requirement: V3-ACC-01
    verification:
      - kind: unit
        ref: "tests/test_fusion.py#test_fuse_symbol_quantity_equals_group_count_exactly"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_fuse_out_of_registry_id_rejected"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_id_grounding_round_trip_through_overlay"
        status: pass
    human_judgment: false
  - id: D3
    description: "ReplayAnalyzer record/replay harness: SHA256-keyed fixtures, KeyError on unknown prompts, REPLAY_RECORD=1 gate, TakeoffPipeline(analyzer=...) injectable"
    requirement: V3-ACC-01
    verification:
      - kind: unit
        ref: "tests/test_fusion.py#test_replay_analyzer_record_then_replay_round_trip"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_replay_analyzer_injectable_into_takeoff_pipeline"
        status: pass
    human_judgment: false

# Metrics
duration: 27min
completed: 2026-07-14
status: complete
---

# Phase 21 Plan 12: Vision + Geometry Fusion Layer Summary

**Provenance-ranked fusion core (V3-ACC-01): vision labels bind to deterministic candidate IDs via a registry-validated fuse_sheet, merge precedence follows geometry > text_layer > schedule_table > learned > vision_ensemble with a hard code-level no-overwrite guard, and the whole layer is pinned offline by 34 tests plus a SHA256-keyed record/replay analyzer harness.**

## Performance

- **Duration:** 27 min
- **Started:** 2026-07-14T16:26:15Z
- **Completed:** 2026-07-14T16:53:30Z
- **Tasks:** 3
- **Files modified:** 4 (all new)

## Accomplishments

- `PROVENANCE_RANK` + `merge_with_provenance` (src/bobbytailor/vision/fusion.py): merge_passes successor with normalized-name dedup where the higher provenance rank wins; equal rank → higher confidence → first-seen; components missing provenance default to `vision_ensemble`. The structural guard is enforced on provenance strings (not rank arithmetic) so a `vision_ensemble` row can never overwrite — or even null-fill — a deterministic quantity/unit; every discarded claim lands in the `fusion_rejected` audit list. `merge_passes` in claude_analyzer stays untouched (backward compat until 21-13 switches the pipeline).
- `fuse_sheet` + `build_registry`: vision ID→label answers applied to deterministic candidates. Symbol groups get legend labels with quantity pinned to the exact deterministic group count (EA); wall thickness classes get material labels with LF from geometry; rooms take vision labels only when `label_source=='none'` (SF always from the polygon; no scale → `None` + flagged, never guessed); schedule rows become `schedule_table`-provenance components; printed footprint dims become `text_layer` components. Any answer referencing an ID outside the registry is dropped and flagged `unknown_candidate_id`. Output mirrors the analyze_drawing shape (components + underscore metadata).
- `ReplayAnalyzer` (tests/replay_analyzer.py): analyze_drawing-signature callable keyed by SHA256 of (model, pass_type, prompt text, image count); replay mode raises `KeyError` on unknown prompts (determinism), record mode is gated by `REPLAY_RECORD=1` and wraps the real analyzer once. Injectable via `TakeoffPipeline(analyzer=ReplayAnalyzer(...))` — the VALIDATION Wave 0 record/replay requirement is operational.
- 34 offline layer-3 tests (tests/test_fusion.py): full precedence matrix across all 5 provenance ranks in both merge orders, the historical CMU 17-vs-2,204 SF regression, the null-fill guard, symbol/wall/room/schedule/footprint assembly, SYM-999 rejection, ID-grounding round-trip through `render_overlay` (marker px ↔ registry bbox_pt exact within 1px), and the replay harness round-trip. Zero API calls anywhere.

## Task Commits

Each task was committed atomically:

1. **Task 1: PROVENANCE_RANK + merge_with_provenance** - `fbd4a27` (feat)
2. **Task 2: fuse_sheet — ID-grounded label application** - `bc60229` (feat)
3. **Task 3: ReplayAnalyzer harness + layer-3 tests** - `879151a` (test)

## Files Created/Modified

- `src/bobbytailor/vision/fusion.py` - Fusion core: PROVENANCE_RANK, merge_with_provenance, fuse_sheet, build_registry, fusion_rejected auditing (795 lines)
- `tests/replay_analyzer.py` - Record/replay analyzer harness (SHA256-keyed fixtures, REPLAY_RECORD gate)
- `tests/test_fusion.py` - 34 offline layer-3 tests (precedence matrix, CMU regression, grounding round-trip, replay harness)
- `tests/fixtures/replay/.gitkeep` - Fixture directory for recorded structured-output responses

## Decisions Made

- Hard no-overwrite guard checks provenance strings directly (independent of rank arithmetic) so a rank-table edit can never silently weaken V3-ACC-01; violation of the absorb-step invariant raises AssertionError.
- `fusion_rejected` records three classes of audit events: `vision_quantity_blocked` (guard firing), `lower_provenance_quantity_conflict` (disagreement between deterministic tiers), `unknown_candidate_id` / `label_override_blocked` (grounding violations). Agreeing duplicates absorb silently.
- Losing components donate extra semantic fields (notes, better name casing) to the winner without ever touching quantity/unit — quantity/unit invariance is asserted post-absorption.
- `fuse_sheet` registry param is optional (built via `build_registry` when omitted) — 21-13 can pass a prebuilt registry shared with the overlay renderer.
- Schedule rows group by name column (ITEM/DESCRIPTION/TYPE/NAME, case-insensitive); explicit QTY cells parsed verbatim, otherwise one row = one installed instance (door-schedule semantics).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ReplayAnalyzer key derivation poisoned by sys.modules mock stubs**
- **Found during:** Task 3 (full-suite gate)
- **Issue:** `tests/test_pipeline_parity.py` registers `claude_analyzer`/`sheet_pass_matrix` MagicMock stubs via `sys.modules.setdefault`; ReplayAnalyzer's lazy imports then returned MagicMock objects, and `json.dumps` in the SHA256 key derivation raised TypeError (3 tests failed only under full-suite collection order).
- **Fix:** Validate every lazy-import result as a real non-empty `str`; non-string results degrade to the deterministic `"unrouted"` model / fallback prompt builder.
- **Files modified:** tests/replay_analyzer.py
- **Verification:** `pytest tests/test_pipeline_parity.py tests/test_fusion.py -q` → 51 passed; full suite 740 passed.
- **Committed in:** `879151a` (part of Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Fix necessary for test determinism under any collection order. No scope creep.

## Issues Encountered

None beyond the auto-fixed deviation above. Synthetic fixture PDFs (`tests/fixtures/synthetic/*.pdf`) regenerated as a known test side effect and were restored before committing.

## Known Stubs

None — no placeholder values, no TODO markers, no unwired data paths. All quantities flow from deterministic inputs; unverifiable values are emitted as `None` + `needs_review` by design (flag-don't-guess).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Fusion protocol complete at module level: provenance enum on every item; vision structurally cannot supply quantities where geometry/text can (V3-ACC-01).
- 21-13 (pipeline integration) can now: import `fuse_sheet`/`merge_with_provenance`/`build_registry`, supersede `merge_passes` at the pipeline level, and write pipeline-level replay tests against `tests/fixtures/replay/` via `TakeoffPipeline(analyzer=ReplayAnalyzer(...))`.
- Full non-golden suite green: 740 passed (706 baseline + 34 new), zero API calls.

## Self-Check: PASSED

- `src/bobbytailor/vision/fusion.py` — FOUND (exports PROVENANCE_RANK, fuse_sheet, merge_with_provenance; 795 lines ≥ 150 min_lines)
- `tests/replay_analyzer.py` — FOUND (contains `class ReplayAnalyzer` and `REPLAY_RECORD`)
- `tests/test_fusion.py` — FOUND (34 tests, all passing)
- `tests/fixtures/replay/.gitkeep` — FOUND
- Commit `fbd4a27` — FOUND
- Commit `bc60229` — FOUND
- Commit `879151a` — FOUND
- `python3 -m pytest tests/test_fusion.py -q` — 34 passed
- `python3 -m pytest tests/ -q -m "not golden"` — 740 passed, 2 deselected

---
*Phase: 21-accuracy-learning-engine*
*Completed: 2026-07-14*

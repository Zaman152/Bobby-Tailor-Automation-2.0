---
phase: 21-accuracy-learning-engine
plan: 14
subsystem: pipeline
tags: [verify-retry, arbitration, budget-guard, structured-outputs, render_clip_crop, opus-routing]

# Dependency graph
requires:
  - phase: 21-13
    provides: deterministic-first TakeoffPipeline (RunSettings.verify_retry_enabled, per-run BudgetGuard threading, _verifier_flags on fused results)
  - phase: 21-12
    provides: fusion candidate registry (candidate_id → bbox_pt/kind) and provenance-ranked merge
  - phase: 21-11
    provides: BudgetGuard/BudgetExceeded charge conventions
  - phase: 21-08
    provides: verify_retry_schema (choice-enum grounding), VERIFY_RETRY_PROMPT
  - phase: 21-05
    provides: render_clip_crop zoom primitive; ('*', 'verify_retry') → CLAUDE_MODEL_DENSE routing row
provides:
  - vision/verify_retry.py — retry_flagged_items targeted-crop arbitration engine (bounded ≤2 attempts/item, budget-charged, choice-grounded)
  - TakeoffPipeline._verify_retry_pass — post-fusion retry queue (QuantityVerifier out-of-band flags + ensemble-disagreement components) with resolution merge-back
  - Flag fields retry_history / resolution ('relabeled'|'confirmed'|'unresolved') + run-wide _verify_retry audit list
  - ENABLE_VERIFY_RETRY env stub removed — gate is RunSettings.verify_retry_enabled
affects: [21-15 entry-point parity, 21-16 accuracy gate, reporter/review UI]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Verify-retry engine follows the ensemble.py injection pattern: all API access via the analyze_call callable; render_clip_crop imported deferred (pdf_analyzer→takeoff_pipeline circular avoidance)"
    - "Choice-set selection by flag anchor kind: symbol_group + legend labels → relabel question; everything else → yes/no/unclear confirm question"

key-files:
  created:
    - src/bobbytailor/vision/verify_retry.py
    - tests/test_verify_retry.py
  modified:
    - src/bobbytailor/pipeline/takeoff_pipeline.py

key-decisions:
  - "Symbol-anchored out-of-band flags get plausible legend labels as choices (relabel path): on vector sheets the deterministic count is exact, so the label is the suspect, never the number"
  - "Deny ('no') is a definite answer — single attempt, flag kept unresolved; only 'unclear' consumes the second attempt, which widens the crop pad (0.25 → 0.75 of the bbox long edge)"
  - "Refused BudgetGuard charge discards the completed answer (ledger holds paid-and-accepted work only, 21-13 convention); remaining flags returned untouched and stay flagged"
  - "Merge-back: relabeled renames the component (quantity/unit untouched) and clears needs_review; confirmed downgrades the flag to a note (reason appended); unresolved keeps the flag — retry_history mandatory on every touched item"
  - "Retry pass wired on the vector flow only: raster components carry no candidate registry anchor, so they would skip with zero calls anyway; they remain flagged needs_review as before"

patterns-established:
  - "Verify-retry queue predicate: _ENSEMBLE_DISAGREEMENT_MARKERS ('ensemble', 'no_majority', 'disagree') in review_reason identifies vote-flagged components"

requirements-completed: [V3-ACC-05]

coverage:
  - id: D1
    description: "Targeted-crop verify-retry engine: registry bbox lookup, high-DPI render_clip_crop question crops, verify_retry_schema choice-grounded answers, ≤2 attempts/item, every call budget-charged, flags never suppressed"
    requirement: V3-ACC-05
    verification:
      - kind: unit
        ref: "tests/test_verify_retry.py#TestRetryEngine (8 tests: confirmed/relabel/unclear-bound/deny/no-anchor/budget-exhausted/refused-charge/grounding)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Pipeline wiring: QuantityVerifier flags + ensemble-disagreement components enter the retry queue when settings.verify_retry_enabled; resolutions merged back (relabel/confirm/unresolved); ENABLE_VERIFY_RETRY env stub removed from source"
    requirement: V3-ACC-05
    verification:
      - kind: unit
        ref: "tests/test_verify_retry.py#TestPipelineWiring (5 tests) + test_legacy_env_stub_gone_from_source"
        status: pass
      - kind: integration
        ref: "python3 -m pytest -q -m 'not golden' — 774 passed (760 baseline + 14 new), test_confidence_flagging + test_pipeline_parity untouched and green"
        status: pass
    human_judgment: false

# Metrics
duration: 14min
completed: 2026-07-14
status: complete
---

# Phase 21 Plan 14: Targeted-Crop Verify-Retry Loop Summary

**Real verify-retry arbitration replaces the ENABLE_VERIFY_RETRY logging stub: out-of-band quantities and ensemble disagreements get bounded (≤2), budget-charged, choice-grounded crop questions to the dense model — relabeling semantics or confirming flags, never suppressing them (V3-ACC-05)**

## Performance

- **Duration:** 14 min
- **Started:** 2026-07-14T17:50:16Z
- **Completed:** 2026-07-14T18:04:37Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `vision/verify_retry.py` (375 lines): `retry_flagged_items` locates each flag's geometry anchor via the fusion candidate registry, renders a high-detail `render_clip_crop` around it (1568px long edge; second attempt widens the context pad), and asks one narrow question through `verify_retry_schema` — the choice enum makes free text and numbers grammatically impossible
- Arbitration semantics: label answers relabel (name only — deterministic quantity/unit are untouched on vector sheets, no quantity-mutation path exists), "yes" confirms (flag → note), "no" denies definitively, "unclear" retries once with a wider crop then leaves the flag unresolved
- Cost controls per the threat model: hard ≤2 attempts/item cap, every completed call's `_cost_usd` charged to the run BudgetGuard, refused charges discard the answer, exhausted budget skips the pass entirely with all flags kept
- Pipeline wiring: post-fusion `_verify_retry_pass` builds the queue from QuantityVerifier out-of-band flags (symbol-anchored ones get legend-label choice sets) plus ensemble-disagreement components (`needs_review` from a vote), calls the module-level patchable `retry_flagged_items` with the run guard, and merges resolutions back with mandatory `retry_history` on every touched item
- `"verify_retry"` pass_type routes to CLAUDE_MODEL_DENSE via the existing `('*', 'verify_retry')` MODEL_ROUTING row inside `analyze_drawing` (no routing logic duplicated in the engine)
- ENABLE_VERIFY_RETRY env stub deleted from `QuantityVerifier` — the gate is `RunSettings.verify_retry_enabled`; a source-scan test keeps the literal from reappearing under src/

## Task Commits

Each task was committed atomically:

1. **Task 1: verify_retry.py engine** - `3d16663` (feat) — engine + 8 offline unit tests
2. **Task 2: Pipeline wiring + stub removal + tests** - `3c53b69` (feat) — queue/merge-back wiring, stub removal, 6 more tests

## Files Created/Modified

- `src/bobbytailor/vision/verify_retry.py` - Targeted-crop arbitration engine (`retry_flagged_items`, question builders, crop rendering with deferred pdf_analyzer import)
- `src/bobbytailor/pipeline/takeoff_pipeline.py` - `_verify_retry_pass` queue + merge-back; module-level patchable `retry_flagged_items` import; `_ENSEMBLE_DISAGREEMENT_MARKERS`; ENABLE_VERIFY_RETRY stub removed; legend labels hoisted for reuse
- `tests/test_verify_retry.py` - 14 offline tests (8 engine, 5 pipeline wiring, 1 source hygiene) — stubbed analyzers, real fitz crop path, zero API calls

## Decisions Made

- Symbol-anchored out-of-band flags carry the sheet's legend labels as their choice set: an impossible quantity on a deterministically-counted symbol group means the LABEL is wrong (e.g. mislabeled CMU), so the retry offers a relabel rather than a pointless quantity dispute
- "no" (deny) stops after one attempt — re-asking a definite answer only burns budget; the flag stays unresolved for human review
- The retry pass is wired on the vector flow only: raster-ensemble components have no registry anchors (they would all skip with zero calls) and are already flagged `needs_review`; the engine itself is path-agnostic for future callers
- The engine catches `BudgetExceeded` internally and returns remaining flags untouched (never propagates) — run continuity is the pipeline's invariant

## Deviations from Plan

None - plan executed exactly as written.

(Note: the CLAUDE.md GitNexus impact-analysis mandate was satisfied by the orchestrator before dispatch — MCP tools are unavailable in the executor context; constraints honored: constructor backward compatibility kept, `merge_passes` re-export untouched, `tests/test_pipeline_parity.py` untouched and green, injection pattern followed, retries charged through the 21-13 BudgetGuard and routed via the 21-05 `verify_retry` MODEL_ROUTING row.)

## Issues Encountered

- Synthetic fixture PDFs (`tests/fixtures/synthetic/*.pdf`) regenerated as a full-suite side effect — restored via `git checkout` before committing (known benign behavior, per executor instructions)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Verify-retry loop is live end-to-end on the vector path; flags now arrive at reports with `retry_history`/`resolution` audit fields — reporter/review UI can surface them
- 21-15 (entry-point parity) can thread the run-level BudgetGuard through the scraper path knowing every vector-sheet vision call site, including retries, charges it
- Full non-golden suite: 774 passed (760 baseline + 14 new)

## Self-Check: PASSED

- [x] `src/bobbytailor/vision/verify_retry.py` exists (375 lines ≥ 80 min)
- [x] `tests/test_verify_retry.py` exists (14 tests ≥ 6)
- [x] Commits `3d16663`, `3c53b69` in git log
- [x] `grep -rn "ENABLE_VERIFY_RETRY" src/ tests/` → no matches
- [x] `python3 -m pytest tests/test_verify_retry.py tests/test_confidence_flagging.py -q` → 21 passed
- [x] `python3 -m pytest -q -m "not golden"` → 774 passed

---
*Phase: 21-accuracy-learning-engine*
*Completed: 2026-07-14*

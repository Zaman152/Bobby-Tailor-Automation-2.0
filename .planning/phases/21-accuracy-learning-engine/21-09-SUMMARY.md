---
phase: 21-accuracy-learning-engine
plan: 09
subsystem: api
tags: [flask, sqlite, learning-store, verification, capture]

# Dependency graph
requires:
  - phase: 21-02
    provides: verify.py blueprint (scale/verify/measurements/calibrate routes split from app.py)
  - phase: 21-04
    provides: learning store (record_correction) + distill job (corrections log → distilled tables)
provides:
  - verify/verify-batch/scale/measurements endpoints insert learning_corrections + trigger distill in the same request
  - _capture_learning best-effort helper (never raises; per-run JSON write is never rolled back)
  - Plausibility warnings on out-of-band corrected quantities via QuantityVerifier._RULES (additive learning_warning response field)
  - Diff-based measurement capture (repeated saves record nothing new)
  - Session-level LEARNING_DB_PATH test isolation in conftest
affects: [21-16 retrieval plan, learning, verify UI]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Best-effort same-request capture: JSON write is source of truth; store INSERT is additive and failure-isolated"
    - "Scope mapping documented in verify.py module docstring (item/unit/missed_item/scale/wall_height)"
    - "Plausibility rules imported from QuantityVerifier._RULES, never copied"

key-files:
  created:
    - tests/test_learning_capture.py
  modified:
    - src/bobbytailor/web/blueprints/verify.py
    - tests/conftest.py

key-decisions:
  - "_capture_learning never raises: store/distill failure logs 'learning capture failed' and returns None — response stays 200 without learning_warning"
  - "verify scope mapping: prior summary row missing → missed_item; unit-only change → unit; else item (confirmation pins current value)"
  - "measurements: wall_area teaches wall_height assumption; count/length/area teach item quantities; capture is diff-based vs previously persisted list"
  - "project_key = normalized project_name from takeoff.json (lowercase, non-alnum runs → '-'), falling back to the run folder name for scale-only runs"
  - "conftest pins LEARNING_DB_PATH to a session tmp DB so endpoint tests never write real output/learning.db"

patterns-established:
  - "Learning capture surface: capture AFTER the per-run JSON persistence line, before/around _rebuild_summary; endpoint parity is inviolable"
  - "Un-verifications and clears are NOT corrections — only verified human overrides are captured"

requirements-completed: [V3-LEARN-01]

coverage:
  - id: D1
    description: "All four capture endpoints (verify, verify-batch, scale, measurements) insert learning_corrections and trigger distill in the same request"
    requirement: "V3-LEARN-01"
    verification:
      - kind: integration
        ref: "tests/test_learning_capture.py#test_verify_item_correction_captured,test_scale_override_captured,test_verify_batch_captures_one_row_per_entry,test_measurements_capture_wall_height_and_item"
        status: pass
    human_judgment: false
  - id: D2
    description: "Implausible corrections (QuantityVerifier out-of-band) persist but return learning_warning in the response"
    requirement: "V3-LEARN-01"
    verification:
      - kind: integration
        ref: "tests/test_learning_capture.py#test_implausible_quantity_warns_but_persists"
        status: pass
    human_judgment: false
  - id: D3
    description: "Endpoint responses/error shapes unchanged for existing UI consumers; store failure never breaks the endpoint"
    requirement: "V3-LEARN-01"
    verification:
      - kind: integration
        ref: "tests/test_learning_capture.py#test_store_failure_does_not_break_endpoint"
        status: pass
      - kind: integration
        ref: "tests/test_blueprint_parity.py + tests/test_scale_module.py (unchanged, 54 passing)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Captured corrections survive run-folder deletion (capture surface no longer dies with the run folder)"
    requirement: "V3-LEARN-01"
    verification:
      - kind: integration
        ref: "tests/test_learning_capture.py#test_capture_survives_run_folder_deletion"
        status: pass
    human_judgment: false

# Metrics
duration: 9min
completed: 2026-07-14
status: complete
---

# Phase 21 Plan 09: Learning Capture Surface Summary

**Human verifications through verify/verify-batch/scale/measurements now write learning_corrections rows + trigger distill in the same request, with QuantityVerifier-backed plausibility warnings — additive to the per-run JSON writes, zero endpoint parity changes**

## Performance

- **Duration:** 9 min
- **Started:** 2026-07-14T14:43:46Z
- **Completed:** 2026-07-14T14:53:40Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `_capture_learning()` in verify.py: resolves project_key (normalized project_name from takeoff.json, run-folder fallback) + project_type + sheet_type, calls `record_correction()` then incremental `distill()` — wrapped so a learning failure logs and returns None without touching the 200 response or the already-written run JSON
- All four capture endpoints wired AFTER their existing JSON persistence lines: `/verify` (item/unit/missed_item), `/verify-batch` (per-entry, missed_item for unknown items), `/scale` (per-overridden-sheet with old fpi/source/confidence in context), `/measurements` (wall_area → wall_height assumption, count/length/area → item; diff-based so re-saves record nothing)
- Plausibility gate reuses `QuantityVerifier._RULES` (imported, not copied): out-of-band corrected quantities persist (human is authoritative) but the response carries `learning_warning` ("corrected value outside plausible range for EA — double-check")
- 9-test capture suite proving round-trip, warning-but-persist, failure isolation, run-folder-deletion survival, dedupe, and in-request distill (assumptions + manifests retrievable immediately)
- Full non-golden suite: **657 passed** (648 baseline + 9 new), blueprint parity and scale endpoint tests untouched and green

## Task Commits

Each task was committed atomically:

1. **Task 1: _capture_learning helper + wire all four endpoints** - `fb17e79` (feat)
2. **Task 2: Capture tests — endpoint → learning_corrections round-trip** - `0eb4162` (test)

## Files Created/Modified

- `src/bobbytailor/web/blueprints/verify.py` - Scope-mapping docstring; `_normalize_project_key`, `_project_identity`, `_plausibility_warning`, `_capture_learning`, `_current_summary_row`, `_capture_item_override`, `_measurement_key`, `_capture_measurement_corrections`; four endpoints wired with additive `learning_warning`
- `tests/test_learning_capture.py` - 9 endpoint→store capture tests (authenticated client + tmp run folder + tmp learning DB)
- `tests/conftest.py` - Session-level `LEARNING_DB_PATH` tmp-DB isolation (endpoint tests must never write real output/learning.db)

## Decisions Made

- Capture only *verified* overrides; clears and explicit un-verifications are not corrections
- Measurements capture diffs against the previously persisted list (id, else item+sheet+measure_type key) — the POST replaces the whole list every save, so diffing prevents feedback-amplification via repeated identical captures (RESEARCH Pitfall 8 hygiene)
- `learning_warning` added to responses only when non-None (strict additive parity)
- Scale corrections record `{"fpi": value}` with old resolve method/confidence in context; fpi has no plausibility rule, so scale never warns

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Session-level learning-DB isolation for the test suite**
- **Found during:** Task 1 (endpoint wiring)
- **Issue:** `LEARNING_DB_PATH` is resolved at store import time from `OUTPUT_DIR`; existing endpoint tests (test_scale_module POSTs) would now trigger capture and write rows into the developer's real `output/learning.db` — test pollution of production learning data
- **Fix:** conftest.py sets `LEARNING_DB_PATH` env (setdefault) to a `tempfile.mkdtemp` session DB before any bobbytailor.learning import
- **Files modified:** tests/conftest.py
- **Verification:** test_scale_module + full suite green; no rows written to repo output/
- **Committed in:** fb17e79 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Essential test-isolation hygiene; no scope creep.

## Issues Encountered

- First test-client fixture draft resolved `get_admin()` before `create_app()` — the admin singleton is populated by `init_admin()` inside the factory, so `current_user` was None (500). Fixed by building the app before patching `flask_login.utils._get_user`.
- `tests/fixtures/synthetic/*.pdf` regenerated as a test-run side effect; restored via `git checkout --` before committing (per known suite behavior).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- V3-LEARN-01 capture half complete: every human verification persists to the learning store and distills immediately; retrieval/injection (LearnedContext) lands in 21-16
- `learning_warning` response field ready for UI consumption (re-check prompt)
- Ready for the next Wave 3+ plan

## Self-Check: PASSED

- FOUND: src/bobbytailor/web/blueprints/verify.py
- FOUND: tests/test_learning_capture.py
- FOUND: tests/conftest.py
- FOUND commit: fb17e79 (Task 1)
- FOUND commit: 0eb4162 (Task 2)
- `python3 -m pytest tests/ -q -m "not golden"` → 657 passed, 2 deselected

---
*Phase: 21-accuracy-learning-engine*
*Completed: 2026-07-14*

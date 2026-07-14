---
phase: 21-accuracy-learning-engine
plan: 04
subsystem: database
tags: [sqlite, learning-store, distillation, parameterized-sql, python39]

# Dependency graph
requires:
  - phase: 21-01
    provides: src/bobbytailor/ package skeleton (learning/ final home) + stores/ patterns
provides:
  - Durable learning store (output/learning.db) — learning_corrections append-only log + learning_vocabulary/assumptions/manifests distilled tables per 21-RESEARCH.md §6
  - record_correction/get_vocabulary/get_assumptions/get_manifest/get_corrections/init_learning_schema APIs (100% parameterized SQL)
  - distill(full_rebuild) — idempotent log→distilled rebuild with +1 confirm / ×0.5 contradiction / ×0.9 staleness decay policy
  - Layer-4 test suite (13 tests) incl. SQL-injection probe
affects: [21-09 endpoint capture, 21-16 retrieval/injection, 21-13 pipeline integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "learning store: lazy double-checked schema init keyed by DB path (re-inits when tests monkeypatch LEARNING_DB_PATH)"
    - "distill purity: replay log in id order, last_seen from correction created_at, decay at run boundaries — incremental == full_rebuild"
    - "manual SELECT→UPDATE/INSERT upsert where NULL-able key columns defeat SQLite unique indexes; ON CONFLICT where keys are NOT NULL"

key-files:
  created:
    - src/bobbytailor/learning/__init__.py
    - src/bobbytailor/learning/store.py
    - src/bobbytailor/learning/distill.py
    - tests/test_learning_store.py
  modified: []

key-decisions:
  - "Dedicated learning.db (not stackct.db) — isolates migration risk per RESEARCH §6; LEARNING_DB_PATH env override, store owns its env read (config.py untouched, disjoint from wave-mate 21-05)"
  - "learning_vocabulary UNIQUE widened to (project_type, raw_pattern, canonical_name, unit) — §6 conflict/decay requires decayed old + new mappings to coexist for one raw_pattern; the §6 2-column UNIQUE makes that state unrepresentable"
  - "Distilled state is a pure function of the append-only log: strict id-order replay, last_seen = correction created_at (never wall-clock), staleness decay triggers at new-verified-run boundaries — any watermark batching reproduces full_rebuild exactly"
  - "Assumptions distilled at BOTH exact (project_key) and type (project_key NULL) levels so learning transfers to new projects of the same type; get_assumptions precedence keeps exact rows winning at home"
  - "Vocabulary upserts are manual SELECT→UPDATE/INSERT: SQLite unique indexes treat NULL project_type (global) rows as always-distinct, so ON CONFLICT would silently skip global weight increments"

patterns-established:
  - "Only learning/store.py + learning/distill.py touch learning_* tables; endpoints must call the store API, never raw SQL"
  - "Correction scopes are module constants (SCOPE_ITEM/SCALE/WALL_HEIGHT/NAME/MISSED_ITEM/UNIT); record_correction rejects unknown scopes"

requirements-completed: [V3-LEARN-01, V3-LEARN-02]

coverage:
  - id: D1
    description: "Four learning_* SQLite tables (corrections append-only log + vocabulary/assumptions/manifests) with schema per 21-RESEARCH.md §6, lazy version-keyed init"
    requirement: V3-LEARN-01
    verification:
      - kind: unit
        ref: "tests/test_learning_store.py#test_round_trip_item_correction"
        status: pass
      - kind: other
        ref: "sqlite3 output/learning.db '.schema learning_corrections' — columns verbatim vs RESEARCH §6"
        status: pass
    human_judgment: false
  - id: D2
    description: "Corrections survive run-folder deletion and are retrievable by (project_type, sheet_type, scope, item_pattern)"
    requirement: V3-LEARN-01
    verification:
      - kind: unit
        ref: "tests/test_learning_store.py#test_correction_survives_run_folder_deletion"
        status: pass
    human_judgment: false
  - id: D3
    description: "distill() idempotent rebuild — second pass processes 0; full_rebuild reproduces identical vocabulary/assumption/manifest rows"
    requirement: V3-LEARN-02
    verification:
      - kind: unit
        ref: "tests/test_learning_store.py#test_distill_idempotent_and_full_rebuild_identical"
        status: pass
    human_judgment: false
  - id: D4
    description: "Conflict/decay policy — contradicting correction decays old value ×0.5, new value wins retrieval; confirming correction +1 weight; specificity exact > type > global"
    requirement: V3-LEARN-02
    verification:
      - kind: unit
        ref: "tests/test_learning_store.py#test_vocabulary_conflict_decay"
        status: pass
      - kind: unit
        ref: "tests/test_learning_store.py#test_assumption_specificity_precedence"
        status: pass
    human_judgment: false
  - id: D5
    description: "SQL-injection hardening — 100% parameterized queries; hostile item_pattern round-trips literally, table survives"
    requirement: V3-LEARN-01
    verification:
      - kind: unit
        ref: "tests/test_learning_store.py#test_sql_injection_probe_round_trips_literally"
        status: pass
      - kind: other
        ref: "rg 'execute\\(f\"|execute\\(.*%s|execute\\(.*\" \\+ ' src/bobbytailor/learning/ — no matches"
        status: pass
    human_judgment: false

# Metrics
duration: 15min
completed: 2026-07-14
status: complete
---

# Phase 21 Plan 04: Durable Learning Store & Distillation Summary

**SQLite learning store (dedicated learning.db, 4 tables per RESEARCH §6) with parameterized CRUD + idempotent distill job implementing the +1/×0.5/×0.9 conflict-decay policy as a pure function of the append-only corrections log**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-14T11:59:59Z
- **Completed:** 2026-07-14T12:15:12Z
- **Tasks:** 3
- **Files modified:** 4 (all created)

## Accomplishments

- `learning/store.py`: `learning_corrections` (append-only, `ix_corr_lookup` index) + `learning_vocabulary`/`learning_assumptions`/`learning_manifests` distilled tables + `learning_metadata` version key; `record_correction()` (json.dumps values, 2000-char cap, UTC ISO, lastrowid) and read APIs with weight ordering and exact>type>global specificity dedup
- `learning/distill.py`: `distill(full_rebuild=False) -> dict` replays the log strictly in id order — name/unit→vocabulary, scale/wall_height→assumptions (RESEARCH key naming `wall_height_ft`, `scale_fpi:<pattern>`), item/missed_item→manifests as pure distinct-run aggregates via ON CONFLICT; `last_distilled_id` watermark; full_rebuild wipes and replays for the auditable-rebuild guarantee
- 13 layer-4 tests green; full non-golden suite 549 passed (536 baseline + 13 new)

## Task Commits

Each task was committed atomically:

1. **Task 1: store.py — schema, init, record_correction** - `745524f` (feat)
2. **Task 2: distill.py — log → distilled tables with conflict/decay** - `0649d61` (feat)
3. **Task 3: Layer-4 test suite** - `6058bff` (test)

## Files Created/Modified

- `src/bobbytailor/learning/__init__.py` - Package docstring for the learning subsystem
- `src/bobbytailor/learning/store.py` - Schema (RESEARCH §6), connection/lock/init, record_correction, get_vocabulary/get_assumptions/get_manifest/get_corrections
- `src/bobbytailor/learning/distill.py` - Idempotent distillation with conflict/decay and staleness policy
- `tests/test_learning_store.py` - 13 layer-4 tests: round-trip, run-folder independence, idempotency, decay, precedence, injection probe, hardening

## Decisions Made

- **Dedicated `learning.db`** rather than extending `stackct.db` — RESEARCH §6 allows either; isolation avoids coupling learning-schema migrations to the v2 project-cache schema. `LEARNING_DB_PATH` env override read by the store itself (config.py untouched; 21-05 owns the .env.example documentation).
- **Vocabulary UNIQUE widened** to `(project_type, raw_pattern, canonical_name, unit)` — see Deviations.
- **Purity contract for distill**: `last_seen` always comes from the correction's `created_at` and staleness decay fires at new-verified-run boundaries (first occurrence of a run_id per project_type in id order), never per distill pass — this makes incremental passes byte-identical to `full_rebuild=True` under any watermark batching.
- **Two-level assumption distillation** (exact project_key row + project_type row) so a wall-height correction on one project benefits future projects of the same type; retrieval precedence still lets the exact row win on its home project.
- **Manual upserts for vocabulary/assumptions** (SELECT→UPDATE/INSERT under the module write lock) because SQLite unique indexes treat NULL key columns as distinct, which would break ON CONFLICT weight increments for global (NULL project_type) rows; manifests use genuine `ON CONFLICT(project_type, item_name)` upsert (both columns NOT NULL).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] RESEARCH §6 vocabulary UNIQUE constraint contradicts its own conflict/decay policy**
- **Found during:** Task 1 (schema design) / Task 2 acceptance criteria
- **Issue:** §6 SQL declares `UNIQUE(project_type, raw_pattern)` but the §6 policy and the plan's acceptance criterion ("after A(X→Y) then B(X→Z): the Y row has weight 0.5 and Z wins") require the decayed old mapping and the new mapping to COEXIST for one raw_pattern — unrepresentable under the 2-column constraint.
- **Fix:** Widened to `UNIQUE(project_type, raw_pattern, canonical_name, unit)`; column definitions unchanged. Max-weight retrieval arbitrates between coexisting mappings exactly as §6 specifies.
- **Files modified:** src/bobbytailor/learning/store.py
- **Verification:** `test_vocabulary_conflict_decay` asserts both rows exist with weights 1.0/0.5 and Z tops retrieval
- **Committed in:** 745524f (Task 1 commit)

**2. [Rule 2 - Missing Critical] last_seen from correction timestamp, not wall clock**
- **Found during:** Task 2 (idempotency design)
- **Issue:** RESEARCH sketch sets `last_seen = now` on upsert; wall-clock timestamps make full_rebuild produce different rows than incremental passes, breaking the plan's must-have truth "distill is idempotent / distilled state is a pure function of the log".
- **Fix:** All `last_seen` values come from the source correction's `created_at`.
- **Files modified:** src/bobbytailor/learning/distill.py
- **Verification:** `test_distill_idempotent_and_full_rebuild_identical` compares full row dumps across incremental and rebuild passes
- **Committed in:** 0649d61 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical)
**Impact on plan:** Both fixes were required to satisfy the plan's own acceptance criteria and must-have truths. No scope creep; schema columns remain verbatim per RESEARCH §6.

## Issues Encountered

None — one test-helper fix during Task 3 (sorting row dumps containing SQL NULL needed `key=repr`), resolved before commit.

## Authentication Gates

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Learning store + distill ready for 21-09 (verify/scale endpoint capture → `record_correction`) and 21-16 (retrieval/LearnedContext injection, ITEM_NAME_MAP integration, anti-amplification guardrail)
- Wave 2 remainder: 21-05 next (edits config.py/.env.example — disjoint from this plan as required)
- Full non-golden suite: 549 passed

## Self-Check: PASSED

- All 4 created files exist on disk
- Task commits 745524f, 0649d61, 6058bff present in git log
- `python3 -m pytest tests/test_learning_store.py -q` → 13 passed
- `python3 -m pytest tests/ -q -m "not golden"` → 549 passed
- `sqlite3 output/learning.db ".schema learning_corrections"` matches RESEARCH §6 columns verbatim

---
*Phase: 21-accuracy-learning-engine*
*Completed: 2026-07-14*

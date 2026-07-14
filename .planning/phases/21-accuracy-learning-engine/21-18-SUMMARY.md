---
phase: 21-accuracy-learning-engine
plan: 18
subsystem: infra
tags: [packaging, import-migration, shim-deletion, src-layout, docs, uat, deployment]

# Dependency graph
requires:
  - phase: 21-01
    provides: src/bobbytailor package tree + the 33 root import shims this plan deletes
  - phase: 21-02
    provides: create_app factory (template/static anchored to repo root) that lets the app.py shim die
  - phase: 21-17
    provides: accuracy_gate.sh + benchmark thresholds the UAT script invokes
provides:
  - Shim-free package: every import in src/, tests/, scripts/, main.py uses absolute bobbytailor.* paths
  - Root app.py reduced to a 5-line gunicorn entry (from bobbytailor.web.app import create_app; app = create_app())
  - Test-order pollution fix (scoped spec-load mocks + conftest pre-registration)
  - README with package layout, plans-only contract, learning loop, accuracy gate
  - docs/DEPLOYMENT.md (env table, restart-on-deploy, error recovery, learning.db backup)
  - .planning/phases/21-accuracy-learning-engine/21-UAT.md (9-section live-testing sign-off script)
affects: [verify-work, milestone-completion, live-testing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Absolute package imports everywhere; lazy in-function imports keep hiding known cycles (geometry_takeoff↔scale_recalc, takeoff_pipeline→pdf_analyzer) but now via package paths"
    - "Spec-load test isolation: temporarily alias the real package key in sys.modules to a mock, exec the spec load, restore the key — never permanent session-wide substitution"
    - "self-module reference via sys.modules[__name__] so analyzer default stays patchable under both package import and spec-load"

key-files:
  created:
    - docs/DEPLOYMENT.md
    - .planning/phases/21-accuracy-learning-engine/21-UAT.md
  modified:
    - app.py (28-line shim → 5-line create_app entry)
    - main.py
    - src/bobbytailor/** (25 modules — import migration)
    - tests/** (44 files — imports, patch targets, sys.modules keys, factory-based app usage)
    - scripts/* (6 files)
    - tests/conftest.py (sys.path fallback removed; stub-target pre-registration added)
    - README.md
  deleted:
    - 33 root import shims (accuracy_config.py … takeoff_pipeline.py)

key-decisions:
  - "Migration-first ordering enforced: internals → tests → scripts all green on 833 tests BEFORE any shim was deleted"
  - "Batches 1-3 landed as one atomic commit: with src on package paths, the parity file's flat sys.modules stubs poison later flat-importing tests (14 failures), so src and tests are mechanically inseparable"
  - "Test-order pollution class FIXED (declared in scope): scoped temp-alias mocks + conftest pre-imports; all three historically-failing forced orders now pass"
  - "TakeoffPipeline analyzer default resolves via sys.modules[__name__] (not self-import by name) so patching works under spec-loading"
  - "21-UAT.md states Crow main-plan scale = 1\"=40' per the 21-07 geometric proof, overriding the plan's stale 1\"=20' example"

patterns-established:
  - "No root Python files except app.py + main.py entry points"
  - "Companion/manifest inputs documented as devtools/benchmark-only (--takeoff-pdf), never production"

requirements-completed: [V3-PROD-02, V3-STRUCT-01]

coverage:
  - id: D1
    description: "All internal/test/script imports migrated to absolute bobbytailor package paths; 33 root shims deleted; conftest sys.path fallback removed; app boots shim-free"
    requirement: V3-STRUCT-01
    verification:
      - kind: unit
        ref: "python3 -m pytest tests/ -q -m 'not golden' → 833 passed, 2 deselected (exit 0, shim-free)"
        status: pass
      - kind: other
        ref: "exhaustive grep: zero imports of any of the 34 legacy flat names (module-level or in-function) in src/ tests/ scripts/ main.py app.py"
        status: pass
      - kind: integration
        ref: "python3 -c 'from bobbytailor.web.app import create_app; create_app()' + test_client GET /login → 200; import app → gunicorn app:app Flask object"
        status: pass
      - kind: other
        ref: "python3 scripts/vision_only_benchmark.py --help → exit 0"
        status: pass
    human_judgment: false
  - id: D2
    description: "README documents the src/bobbytailor layout, plans-only contract, learning loop, accuracy gate; docs/DEPLOYMENT.md covers env vars, restart-on-deploy, error recovery, learning.db backup"
    requirement: V3-PROD-02
    verification:
      - kind: other
        ref: "anchor greps: README contains src/bobbytailor + --takeoff-pdf; DEPLOYMENT.md contains LEARNING_DB_PATH + API_BUDGET_PER_RUN_USD; all code fences balanced"
        status: pass
    human_judgment: false
  - id: D3
    description: "Live-testing readiness signed off by executing 21-UAT.md end-to-end (upload run, flagged review, correction persistence, repeat-run application, StackCT parity, accuracy gate) and pushing the milestone to GitHub"
    requirement: V3-PROD-02
    verification: []
    human_judgment: true
    rationale: "Blocking human checkpoint (Task 3): the UAT spends real API credits, requires demo-grade UX judgment, and the GitHub push is a locked user process decision"

# Metrics
duration: 40min
completed: 2026-07-14
status: complete
---

# Phase 21 Plan 18: Shim Deletion, Import Migration & Live-Testing Readiness Summary

**All 33 root import shims deleted after a proven-green migration of every import in src/, tests/, scripts/ and main.py to absolute bobbytailor package paths (833 tests, zero legacy imports by exhaustive grep), plus README/DEPLOYMENT docs and a 9-section 21-UAT.md live-testing sign-off script — with the long-standing test-order pollution class fixed as sanctioned in-scope work.**

## Performance

- **Duration:** ~40 min (excluding two 5-min background suite runs overlapped with work)
- **Started:** 2026-07-14T20:02:28Z
- **Completed:** 2026-07-14T20:42:00Z
- **Tasks:** 2 of 3 (Task 3 is the blocking human-verify UAT checkpoint)
- **Files modified:** 113 (75 migration + 35 deletion/entry + 3 docs)

## Accomplishments

- **Migration-before-deletion executed exactly as mandated:** (1) src internals → (2) tests (incl. ~190 `mock.patch` target strings and every `sys.modules` stub key) → (3) scripts + main.py, suite green at 833; (4) only then the 33 shims deleted, suite green again at 833, app boot + `/login` 200 + `gunicorn app:app` entry verified.
- **Grep-proof of zero legacy imports:** the plan's two audit greps AND an exhaustive any-indentation grep over all 34 flat module names return nothing across `src/ tests/ scripts/ main.py app.py`.
- **Lazy in-function imports preserved in-function** with package-path targets (geometry_takeoff↔scale_recalc cycle, takeoff_pipeline→pdf_analyzer `_effective_render_scale`) — no hoisting, no new module-level cycles.
- **Root `app.py` is a 5-line create_app entry** serving both `gunicorn app:app` and `python3 app.py` dev use; template/static resolution verified via create_app (repo-root anchoring landed in 21-02, so the shim's repointing died safely).
- **Test-order pollution class RESOLVED** (deferred-items 21-08/21-16, declared in scope by the orchestrator): parity/takeoff-pipeline mocks now bind only inside their spec loads (temp-alias + restore) and conftest pre-imports every stub-targeted real module. All three historically-failing forced orders now pass (`parity→learning_capture` 35 passed, `parity→confidence_flagging` 33 passed, `takeoff_pipeline→render_fidelity` 53 passed).
- **Docs shipped:** README (package tree, `pip install -e .` quickstart, plans-only contract with `--takeoff-pdf`, learning-loop overview, accuracy-gate usage, v3 env vars, `python -m bobbytailor.web.seed_admin`); `docs/DEPLOYMENT.md` (entry points, full env table — names/sources only, restart-required-on-deploy per RESEARCH Pitfall 9, per-sheet degradation, `budget_exhausted` semantics, raster fallback, reviewed-items workflow, `learning.db` copy-backup, post-deploy smoke).
- **21-UAT.md:** 9 numbered sections mapping the 7 roadmap success criteria + both 21-VALIDATION manual-only rows, with exact commands/URLs and expected observations, explicitly folding in the pending 21-17 live gate run; sign-off checklist ends with the locked GitHub-push step.

## Task Commits

1. **Task 1 (batches 1–3): import migration** - `dc71d0e` (refactor) — 75 files, suite 833 green
2. **Task 1 (batch 4): shim deletion + 5-line app.py + conftest fallback removal** - `8c349dd` (refactor) — 35 files, suite 833 green shim-free
3. **Task 2: README + docs/DEPLOYMENT.md + 21-UAT.md** - `6930bb5` (docs)

## Files Created/Modified

- `src/bobbytailor/**` (25 modules) — flat sibling imports → absolute package paths; `takeoff_pipeline` self-reference via `sys.modules[__name__]`
- `tests/**` (44 files) — imports, patch strings, sys.modules keys migrated; `test_job_history_api`/`test_scale_module` moved to `create_app()`; `test_vision_schemas` shim-contract test rewritten as package-contract test; parity source-level assertions strengthened to catch package-path `analyze_drawing` imports
- `tests/conftest.py` — sys.path shim fallback removed; stub-target pre-registration list added
- 33 root shims deleted; `app.py` → 5-line entry; `main.py`, `scripts/*` migrated
- `README.md`, `docs/DEPLOYMENT.md`, `.planning/phases/21-accuracy-learning-engine/21-UAT.md`

## Decisions Made

- Batches 1–3 form one atomic commit: with src on package paths, importing scraper no longer registers flat aliases as a side effect, so the parity file's flat `sys.modules.setdefault(..., MagicMock())` stubs win and poison later flat-importing tests (14 failures observed at the batch-1-only intermediate state). src and tests are mechanically inseparable; the deletion still has its own green commit boundary.
- The spec-load `_load()` helpers keep registering under flat names ("takeoff_pipeline", …) — those are now isolated spec names that collide with nothing, which is exactly the isolation the tests want.
- 21-UAT.md documents Crow main-plan scale as **1"=40'** (21-07 proof: printed scale + 1136'×350' overall dims; 1136 ft cannot fit a 3024-pt sheet at 20 fpi), correcting the plan's stale 1"=20' example.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Batch-1-only intermediate state cannot be green**
- **Found during:** Task 1 batch 1 suite run
- **Issue:** 14 failures (test_plan_sets, test_sheet_preview, test_stackct_store): once src stopped importing flat names, the shims' sys.modules aliasing side effect vanished, so parity's flat MagicMock setdefault stubs started winning under canonical collection order
- **Fix:** migrated tests in the same commit (plan's batch structure preserved as execution order with suite runs between; commit boundary merged for atomicity)
- **Files modified:** tests/** (batch 2)
- **Verification:** suite 833 green post-batch-3 and post-batch-4
- **Committed in:** dc71d0e

**2. [Rule 1 - Bug] Mechanical rewrite produced invalid app imports**
- **Found during:** Task 1 batch 2 review
- **Issue:** `from app import app` → `from bobbytailor.web.app import app` is invalid (factory module has no module-level `app`); same for `import app as app_module`
- **Fix:** `create_app()` usage in test_job_history_api.py (module-level singleton) and test_scale_module.py (lazy module singleton)
- **Files modified:** tests/test_job_history_api.py, tests/test_scale_module.py
- **Verification:** both endpoint suites pass in the 833
- **Committed in:** dc71d0e

**3. [Rule 1 - Bug] takeoff_pipeline self-import would break patchability under spec-loading**
- **Found during:** Task 1 batch 1 (read_first analysis)
- **Issue:** `import takeoff_pipeline as _self_module` migrated literally would import the real package module even when the code is executing as a spec-loaded copy, so test patches on the executing module's `analyze_drawing` would be ignored
- **Fix:** `_self_module = sys.modules[__name__]` (resolves to the executing module under both load modes)
- **Files modified:** src/bobbytailor/pipeline/takeoff_pipeline.py
- **Verification:** test_takeoff_pipeline + parity suites green
- **Committed in:** dc71d0e

**4. [Sanctioned in-scope] Test-order pollution fix**
- **Found during:** Task 1 batch 2 (the batch-1 failures were this exact class surfacing)
- **Issue:** permanent session-wide `sys.modules` substitution in parity/test_takeoff_pipeline leaked mocks into later-collected modules (deferred-items 21-08/21-16)
- **Fix:** scoped temp-alias + restore around spec loads; conftest pre-registers all stub-targeted real package modules; test_vision_schemas shim-workaround test rewritten as a package-contract test
- **Files modified:** tests/test_pipeline_parity.py, tests/test_takeoff_pipeline.py, tests/test_sheet_pass_matrix.py, tests/conftest.py, tests/test_vision_schemas.py
- **Verification:** all three historically-failing forced orders pass; deferred-items.md updated to RESOLVED
- **Committed in:** dc71d0e

**5. [Rule 1 - Bug] Plan's UAT example contradicted the 21-07 ground truth**
- **Found during:** Task 2 (UAT authoring)
- **Issue:** plan example expected Crow scale `HIGH 1"=20'`; 21-07 proved main-plan truth is 1"=40' (geometrically impossible otherwise)
- **Fix:** UAT documents 1"=40' with the reasoning inline
- **Files modified:** 21-UAT.md
- **Verification:** consistent with STATE.md 21-07 decision
- **Committed in:** 6930bb5

---

**Total deviations:** 5 (2 blocking, 3 bugs/corrections; item 4 explicitly declared in scope by the orchestrator)
**Impact on plan:** No scope creep beyond the sanctioned pollution fix. All deviations were required for the migration to be correct; behavior changes are confined to test infrastructure and import paths.

## Issues Encountered

- The batch-4 commit initially captured only the 33 deletions (a silent `git add` failure left app.py/conftest.py unstaged); caught immediately by inspecting the commit stat and fixed with an amend before any further work — final commit `8c349dd` is atomic and green.
- Synthetic fixture PDFs (`tests/fixtures/synthetic/*.pdf`) regenerate as a suite side effect; restored before every commit per the execution notes.

## User Setup Required

None — no new external service configuration. (Deployment operators should note the new `pip install -e .` install step and the `python -m bobbytailor.web.seed_admin` seeding path, both documented in README/DEPLOYMENT.)

## Next Phase Readiness

- **PENDING — Task 3 blocking human checkpoint:** execute `.planning/phases/21-accuracy-learning-engine/21-UAT.md` end-to-end (includes the deferred 21-17 live gate run, spends API credits), verify docs against reality, and push to GitHub `Zaman152/Bobby-Tailor-Automation-2.0` per the locked process decision. The phase is code-complete but NOT live-signed-off until then.
- V3-STRUCT-01 fully closed: package-native imports everywhere, shims gone, suite green, app boots via blueprints.
- Remaining known deferred item: `web/settings.py` `VALID_MODELS` still lists only legacy slugs (21-05 deferred item; routing unaffected).

## Self-Check: PASSED

- `docs/DEPLOYMENT.md` — FOUND; `.planning/phases/21-accuracy-learning-engine/21-UAT.md` — FOUND; `app.py` 5 lines with create_app — FOUND; 33 shims absent at root — VERIFIED
- Commits `dc71d0e`, `8c349dd`, `6930bb5` — FOUND in git log
- Acceptance criteria re-run: audit greps empty ✓; `pytest -m "not golden"` 833 passed exit 0 ✓; README anchors (`src/bobbytailor`, `--takeoff-pdf`) ✓; DEPLOYMENT anchors (`LEARNING_DB_PATH`, `API_BUDGET_PER_RUN_USD`) ✓; 21-UAT.md has 9 ≥ 7 numbered sections ✓

---
*Phase: 21-accuracy-learning-engine*
*Completed: 2026-07-14 (code complete; UAT sign-off pending)*

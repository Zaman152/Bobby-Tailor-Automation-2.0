---
phase: 21-accuracy-learning-engine
plan: 02
subsystem: api
tags: [flask, blueprints, app-factory, csrf, jobs-runtime]

requires:
  - phase: 21-01
    provides: src/bobbytailor/ package layout and root import shims
provides:
  - create_app() Flask factory with CSRF, login, limiter, and blueprint registration
  - Seven domain blueprints owning all 40 HTTP route handlers
  - jobs_runtime.py isolating in-memory job state and background thread launchers
  - test_blueprint_parity.py proving URL/auth/CSRF equivalence
affects:
  - 21-09 (verify.py learning-store capture rewire)
  - future gunicorn factory deployment

tech-stack:
  added: []
  patterns:
    - "Flask app factory (create_app) with blueprint registration, no module-level app in package"
    - "jobs_runtime owns jobs dict + thread targets with primitive-only payloads"
    - "Blueprint endpoints use auth.login / projects.index naming; templates updated for logout"

key-files:
  created:
    - src/bobbytailor/web/jobs_runtime.py
    - src/bobbytailor/web/blueprints/__init__.py
    - src/bobbytailor/web/blueprints/auth.py
    - src/bobbytailor/web/blueprints/projects.py
    - src/bobbytailor/web/blueprints/runs.py
    - src/bobbytailor/web/blueprints/reports.py
    - src/bobbytailor/web/blueprints/verify.py
    - src/bobbytailor/web/blueprints/settings.py
    - src/bobbytailor/web/blueprints/jobs.py
    - tests/test_blueprint_parity.py
  modified:
    - src/bobbytailor/web/app.py
    - app.py
    - templates/index.html
    - templates/settings.html
    - tests/test_scale_module.py

key-decisions:
  - "Blueprint endpoints prefixed (auth.login, projects.index); PUBLIC_ENDPOINTS and login_view updated accordingly"
  - "create_app sets template_folder/static_folder to repo root (parents[3] from web package)"
  - "Blueprints read OUTPUT_DIR via import config at runtime so tests can patch config.OUTPUT_DIR"
  - "verify.py owns scale/measurements/verify/calibrate; reports.py owns list/preview/sheet-image"

patterns-established:
  - "Pure redistribution split — route bodies moved verbatim, no logic edits"
  - "Parity gate: 40 url_map rules, unauthenticated API GET → 401/302, CSRF on POST /logout"

duration: 8 min
completed: 2026-07-14
---

# Phase 21 Plan 02: Flask App Factory + Blueprints Summary

**Monolithic 1,817-line app.py split into create_app() factory, 7 blueprints, and jobs_runtime.py with parity tests proving identical URLs, auth, and CSRF behavior.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-07-13T20:04:00Z
- **Completed:** 2026-07-13T20:12:00Z
- **Tasks:** 3/3
- **Files modified:** 15

## Accomplishments

- Extracted `jobs_runtime.py` with `jobs`/`uploads`/`object_manifests` dicts and StackCT/PDF thread helpers (primitive payloads only)
- Rewrote `src/bobbytailor/web/app.py` as `create_app()` factory registering auth, projects, runs, reports, verify, settings, and jobs blueprints
- Moved all 40 route handlers into blueprints without URL or logic changes; verify.py is a clean seam for plan 21-09
- Added `test_blueprint_parity.py` covering URL inventory, auth guard, and CSRF logout rules

## Task Commits

1. **Task 1: create_app() factory + jobs_runtime extraction** - `1e5e990` (feat)
2. **Task 2: Move route groups into 7 blueprints** - `346ca87` (feat)
3. **Task 3: Route/auth/CSRF parity gate + full suite** - `052e33f` (test)

**Plan metadata:** pending (docs commit)

## Files Created/Modified

- `src/bobbytailor/web/jobs_runtime.py` — in-memory job state + background thread targets
- `src/bobbytailor/web/app.py` — create_app() factory (no @app.route)
- `src/bobbytailor/web/blueprints/*.py` — seven blueprint modules with all routes
- `app.py` — root shim: `app = create_app()` for gunicorn
- `tests/test_blueprint_parity.py` — URL/auth/CSRF parity gate
- `templates/index.html`, `templates/settings.html` — `url_for('auth.logout')`

## Decisions Made

- Blueprint endpoint names are prefixed (`auth.login`, `projects.index`); templates and `login_manager.login_view` updated to match
- Factory sets template/static folders to repo root so `create_app().test_client()` works without the root shim
- Scale endpoint tests patch `config.OUTPUT_DIR` instead of `app.OUTPUT_DIR` after blueprint split

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed missing _load_scale_calibration and misplaced sheet-image route**
- **Found during:** Task 2 (blueprint generation)
- **Issue:** Automated split placed `_load_scale_calibration` in reports.py and `serve_sheet_image` in verify.py; scale GET failed at import/runtime
- **Fix:** Moved helper to verify.py; moved sheet-image route to reports.py per plan assignment
- **Files modified:** `blueprints/verify.py`, `blueprints/reports.py`
- **Verification:** scale module tests pass
- **Committed in:** `346ca87`

**2. [Rule 3 - Blocking] create_app() missing template_folder caused /login 500**
- **Found during:** Task 1 verification
- **Issue:** Factory Flask() resolved templates relative to src/bobbytailor/web/
- **Fix:** Set template_folder/static_folder to repo root in create_app()
- **Committed in:** `1e5e990`

**3. [Rule 1 - Bug] test_scale_module OUTPUT_DIR patch ineffective after split**
- **Found during:** Task 3 full suite
- **Issue:** Blueprints use `config.OUTPUT_DIR`; test patched `app.OUTPUT_DIR`
- **Fix:** Changed patch target to `config.OUTPUT_DIR`
- **Committed in:** `052e33f`

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 blocking)
**Impact on plan:** Required for correct boot and test parity. No scope creep.

## Issues Encountered

None blocking. Full suite (`pytest -m "not golden"`) green at 544 passed after blueprint split.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- verify.py is isolated and ready for learning-store capture rewire (21-09)
- create_app() factory ready for gunicorn `app:app` via root shim
- Proceed to 21-03-PLAN.md (or next unexecuted plan in wave 2)

---
*Phase: 21-accuracy-learning-engine*
*Completed: 2026-07-14*

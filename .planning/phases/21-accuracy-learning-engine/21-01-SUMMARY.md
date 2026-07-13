---
phase: 21-accuracy-learning-engine
plan: 01
subsystem: infra
tags: [packaging, src-layout, setuptools, pyproject, import-shims, git-mv]

# Dependency graph
requires:
  - phase: 20-pipeline-parity
    provides: flat-module pipeline (TakeoffPipeline, parity tests) that this plan relocates intact
provides:
  - src/bobbytailor/ package tree (pipeline/, vision/, deterministic/, scrape/, stores/, devtools/, web/)
  - 34 moved modules as 100% git renames (history preserved via git log --follow)
  - pyproject.toml src-layout editable install (pip install -e .)
  - 34 root import shims keeping every legacy flat import path working
  - conftest.py sys.path fallback for uninstalled checkouts
affects: [all Phase 21 plans (21-02 .. 21-18), test import migration, shim removal plan]

# Tech tracking
tech-stack:
  added: [setuptools>=64 build backend (PEP 660 editable)]
  patterns:
    - "Shim aliasing: root shim star-re-exports then sets sys.modules[__name__] to the real package module so both import paths share one module object (monkeypatch-safe)"
    - "New Phase 21 modules go directly into their final package homes under src/bobbytailor/"

key-files:
  created:
    - pyproject.toml
    - src/bobbytailor/__init__.py (+ 7 subpackage __init__.py)
    - 34 root shim .py files (original filenames)
  modified:
    - requirements.txt (pymupdf>=1.26)
    - src/bobbytailor/config.py (.env resolution)
    - src/bobbytailor/web/settings.py (.env resolution)
    - src/bobbytailor/web/seed_admin.py (.env resolution)
    - tests/conftest.py (path fallback)
    - tests/test_pipeline_parity.py, tests/test_takeoff_pipeline.py, tests/test_sheet_pass_matrix.py (source-path loaders now read src/)

key-decisions:
  - "Shims alias sys.modules[__name__] to the real package module instead of plain star re-export — required so 100+ mock.patch('scraper.*')-style test patches hit the function globals of the real module"
  - "requires-python kept at >=3.9 (not >=3.10 as drafted) because the deployment/test runtime is macOS system Python 3.9.6"
  - "app shim repoints Flask template_folder/static_folder to repo root (Flask resolves them relative to the module location, now src/bobbytailor/web/)"
  - "settings.py and seed_admin.py got the same .env repo-root fix as config.py (same bug class, Rule 1)"

patterns-established:
  - "Transitional shim: `from bobbytailor.X.Y import *` + `sys.modules[__name__] = <real module>`; shims deleted in a closing plan after test import migration"
  - "Internal imports inside moved modules stay flat (resolve through shims) until the dedicated import-migration plan"

# Metrics
duration: 55min
completed: 2026-07-13
---

# Phase 21 Plan 01: Package Restructure Summary

**34 flat root modules relocated to src/bobbytailor/ as pure git renames, with sys.modules-aliasing root shims, PEP 660 editable install, and the full 505-test deterministic suite green.**

## Performance

- **Duration:** 55 min
- **Started:** 2026-07-13T18:58:31Z
- **Completed:** 2026-07-13T19:53:47Z
- **Tasks:** 3
- **Files modified:** 85 (34 renames, 34 shims, pyproject, requirements, conftest, 3 test loaders, 3 env-path fixes, 8 __init__.py)

## Accomplishments

- `src/bobbytailor/` package exists with subpackages pipeline/, vision/, deterministic/, scrape/, stores/, devtools/, web/ — every subsequent Phase 21 plan can create modules in their final homes
- Move commit is 100% renames (`git diff -M100%` verified, `git log --follow` preserves history on spot-checked modules)
- Every legacy root import path (`import geometry_takeoff`, `from scraper import ...`, `import app`) still works through shims
- `pip install -e .` succeeds; `python -c "import bobbytailor"` succeeds
- Full deterministic suite: **505 passed, 0 failed** (same count as pre-move baseline; plan's "348" figure was stale)
- `scripts/vision_only_benchmark.py --help` prints usage; Flask `/login` returns 200 through the shim

## Task Commits

Each task was committed atomically:

1. **Task 1: pyproject.toml + package skeleton + git mv all root modules** - `af3a32d` (refactor)
2. **Task 2: Root import shims + conftest fallback** - `2bfad0b` (feat)
3. **Task 2 (env fix): repo-root .env resolution from relocated modules** - `d793413` (fix)

Task 3 was verification-only (no file changes, no commit).

## Files Created/Modified

- `pyproject.toml` - src-layout package definition, setuptools backend, deps mirror requirements.txt, pymupdf>=1.26
- `src/bobbytailor/**` - 34 moved modules + 8 `__init__.py`
- 34 root shims (e.g. `geometry_takeoff.py`) - star re-export + sys.modules alias + generated private-name re-exports
- `tests/conftest.py` - repo-root + src/ sys.path fallback when package not installed
- `tests/test_pipeline_parity.py`, `tests/test_takeoff_pipeline.py`, `tests/test_sheet_pass_matrix.py` - path-based `_load()` helpers now read real sources from `src/bobbytailor/`
- `src/bobbytailor/config.py` - `.env` at `parents[2]` (repo root) with cwd fallback

## Decisions Made

- **Shim design upgraded from plan spec:** plain `import *` shims would have broken ~130 `mock.patch("scraper.X")` / `patch("pdf_analyzer.X")` test call-sites, because patching a shim's attribute does not touch the real module's globals. Each shim therefore also executes `sys.modules[__name__] = <real module>`, making both import paths one module object. The plan-mandated star-import line is retained (satisfies the artifact grep) and private-name re-exports were generated from actual test/script imports.
- **`requires-python = ">=3.9"`** instead of the drafted `>=3.10`: the runtime that executes the 505-test suite is macOS system Python 3.9.6; a 3.10 floor would have made the editable install impossible on the actual environment.
- **Flask template/static repointing lives in the `app.py` shim** (not the moved module) per Task 3's "fix breakage by adjusting shims only" rule.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pip 21.2.4 cannot do PEP 660 editable installs**
- **Found during:** Task 1 (editable install verification)
- **Issue:** system pip 21.2.4 rejects `pip install -e .` for pyproject-only projects
- **Fix:** upgraded user-site pip to 26.0.1 (`python3 -m pip install --user --upgrade pip`), then editable install succeeded
- **Files modified:** none (environment only)
- **Verification:** `pip install --user -e .` exit 0; `import bobbytailor` works
- **Committed in:** n/a (no repo change)

**2. [Rule 3 - Blocking] Path-based module loaders in three test files read root shims instead of real sources**
- **Found during:** Task 2 (suite run — collection error: `module 'claude_analyzer' has no attribute '_merge_schedule_lists'`)
- **Issue:** `test_pipeline_parity.py`, `test_takeoff_pipeline.py`, `test_sheet_pass_matrix.py` load modules by root file path (`parent.parent / "{name}.py"`) and do source-level string assertions on `scraper.py`/`pdf_analyzer.py`; after the move those root files are thin shims
- **Fix:** pointed the `_load()` helpers and source-read assertions at `src/bobbytailor/...` real files; stubbing/mocking semantics unchanged
- **Files modified:** tests/test_pipeline_parity.py, tests/test_takeoff_pipeline.py, tests/test_sheet_pass_matrix.py
- **Verification:** full suite 505 passed
- **Committed in:** 2bfad0b (Task 2 commit)

**3. [Rule 3 - Blocking] Flask templates/static unresolvable after move**
- **Found during:** Task 2/3 (Flask boot smoke design)
- **Issue:** `Flask(__name__)` resolves templates relative to the defining module — now `src/bobbytailor/web/`, while `templates/` and `static/` live at repo root; `/login` would raise TemplateNotFound
- **Fix:** `app.py` shim sets `app.template_folder`/`app.static_folder` to repo-root paths (shim-only fix; moved module untouched)
- **Files modified:** app.py (shim)
- **Verification:** `app.app.test_client().get('/login')` returns 200
- **Committed in:** 2bfad0b (Task 2 commit)

**4. [Rule 1 - Bug] settings.py and seed_admin.py .env paths broken by move**
- **Found during:** Task 2 (reading moved web modules)
- **Issue:** both compute `ENV_PATH = Path(__file__).parent / ".env"` — post-move that points at `src/bobbytailor/web/.env`, so the settings UI would read/write the wrong .env and admin seeding would write outside the repo root; identical bug class to the config.py fix the plan already sanctioned
- **Fix:** `parents[3]` (repo root from src/bobbytailor/web/), settings.py with cwd fallback
- **Files modified:** src/bobbytailor/web/settings.py, src/bobbytailor/web/seed_admin.py
- **Verification:** `bobbytailor.web.settings.ENV_PATH` resolves to repo-root .env
- **Committed in:** d793413 (env-fix commit, isolated from the move commit per threat model)

---

**Total deviations:** 4 auto-fixed (1 bug, 3 blocking)
**Impact on plan:** All fixes were required for the move to be invisible to tests/scripts/web app. No scope creep; moved-module content untouched except the sanctioned .env-resolution fixes.

## Issues Encountered

- Plan's "348 tests" figure was stale — the deterministic suite is currently 505 tests (pre-move baseline run confirmed 505 passed). Acceptance criterion "or the current green count if it moved" applied.

## User Setup Required

None - no external service configuration required. (Note: user-site pip was upgraded 21.2.4 → 26.0.1 to support PEP 660 editable installs.)

## Next Phase Readiness

- Package tree ready: Phase 21 plans create `deterministic/`, `learning/`, `vision/`, `web/blueprints/` modules directly in final homes
- Root shims carry all legacy imports; internal imports inside moved modules remain flat (resolve through shims) until the import-migration plan
- GitNexus index is now stale relative to the new layout (symbols indexed at old root paths) — re-run `npx gitnexus analyze` before relying on impact analysis in later plans

---
*Phase: 21-accuracy-learning-engine*
*Completed: 2026-07-13*

---
phase: 22-production-restructure-cleanup
plan: 03
subsystem: infra
tags: [flask, packaging, setuptools, docs, restructure]

requires:
  - phase: 22-02
    provides: DELETE/ARCHIVE buckets cleared; scripts/archive relocation established the git-mv pattern
provides:
  - "docs/archive/{Master,Masterv2}.md — legacy planning docs archived out of the repo root"
  - "docs/design/bobby-tailor/ — design contract relocated under docs/"
  - "src/bobbytailor/web/{templates,static}/ — web assets now live inside the package"
  - "create_app reduced to bare Flask(__name__); the parents[3] repo-root reach-up is gone"
  - "[tool.setuptools.package-data] so a built wheel ships the moved web assets"
affects: [22-04, deployment, packaging, frontend]

tech-stack:
  added: []
  patterns:
    - "Flask default asset resolution: templates/ and static/ sit next to the module, resolved via app.root_path"
    - "Wheel data declared via [tool.setuptools.package-data] (recursive ** globs, setuptools>=64)"

key-files:
  created:
    - docs/archive/Master.md
    - docs/archive/Masterv2.md
    - docs/design/bobby-tailor/MASTER.md
    - src/bobbytailor/web/templates/index.html
    - src/bobbytailor/web/static/style.css
  modified:
    - src/bobbytailor/web/app.py
    - pyproject.toml
    - src/bobbytailor/web/static/style.css
    - src/bobbytailor/web/static/app.js
    - tests/test_extraction_prompt.py

key-decisions:
  - "Comment refs repointed at docs/design/bobby-tailor/MASTER.md (live design contract) with the archived docs/archive/Master.md section numbers kept as a legacy pointer — both paths stay resolvable"
  - "pathlib.Path import removed from web/app.py once parents[3] was its only consumer"
  - "settings.py:16 / seed_admin.py:31 parents[3] left untouched — they resolve .env, a different purpose"

patterns-established:
  - "Package-local web assets: no repo-root reach-up from inside src/"

requirements-completed: [RESTRUCTURE-SPEC-S4, RESTRUCTURE-SPEC-S5]

coverage:
  - id: D1
    description: "Master.md and Masterv2.md archived to docs/archive/ with history preserved (git mv, 100% rename similarity)"
    requirement: RESTRUCTURE-SPEC-S4
    verification:
      - kind: other
        ref: "test -f docs/archive/Master.md && test -f docs/archive/Masterv2.md && test ! -e Master.md && test ! -e Masterv2.md"
        status: pass
      - kind: other
        ref: "git show --stat a99c55a (rename Master.md => docs/archive/Master.md 100%)"
        status: pass
    human_judgment: false
  - id: D2
    description: "design-system/ moved to docs/design/; comment/docstring refs repointed with zero dangling old paths in code dirs"
    requirement: RESTRUCTURE-SPEC-S4
    verification:
      - kind: other
        ref: "grep -rn 'design-system/' --include='*.py' --include='*.js' --include='*.css' --include='*.html' src static templates scripts -> no matches"
        status: pass
      - kind: other
        ref: "grep -c 'docs/design/bobby-tailor/MASTER.md' style.css -> 2, app.js -> 1"
        status: pass
      - kind: unit
        ref: "tests/test_extraction_prompt.py (2 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "templates/ and static/ relocated into src/bobbytailor/web/; repo-root dirs gone"
    requirement: RESTRUCTURE-SPEC-S5
    verification:
      - kind: other
        ref: "test -f src/bobbytailor/web/templates/index.html && test -f src/bobbytailor/web/static/style.css && find templates static -maxdepth 0 (fails)"
        status: pass
    human_judgment: false
  - id: D4
    description: "create_app is bare Flask(__name__) — parents[3] reach-up and both folder args deleted; Flask resolves assets from app.root_path"
    requirement: RESTRUCTURE-SPEC-S5
    verification:
      - kind: integration
        ref: "tests/test_blueprint_parity.py (23 passed — exercises create_app + the 40-route EXPECTED_PATHS set)"
        status: pass
      - kind: other
        ref: "grep 'parents[3]' src/bobbytailor/web/app.py -> no match; grep -c 'Flask(__name__)' -> 1"
        status: pass
    human_judgment: false
  - id: D5
    description: "login -> dashboard -> reports -> settings click-through works and every static asset returns 200 via url_for('static', ...), from the repo root AND from an unrelated cwd"
    requirement: RESTRUCTURE-SPEC-S5
    verification:
      - kind: e2e
        ref: "scratchpad/web_smoke.py via Flask test_client: GET /login 200 (login.html rendered), all 12 static files 200, GET / 200, GET /settings 200, GET /api/reports 200 — run twice (repo root + /tmp cwd)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Built wheel will include the moved web assets via [tool.setuptools.package-data]"
    verification:
      - kind: other
        ref: "toml parse -> {'bobbytailor': ['web/templates/*.html', 'web/static/**/*']}; grep -c 'package-data' pyproject.toml -> 1"
        status: pass
    human_judgment: true
    rationale: "Declaration and parse are verified, but no wheel was actually built this plan (deploys are editable installs). A real `python -m build` + wheel-content check is the only proof the glob ships the files."
  - id: D7
    description: "Offline suite stays green after each of the two commits"
    verification:
      - kind: integration
        ref: "python3 -m pytest -q -> 1132 passed, 2 deselected (run after Task 1 and again after Task 2)"
        status: pass
    human_judgment: false

duration: 21min
completed: 2026-08-03
status: complete
---

# Phase 22 Plan 03: Legacy Docs Archive + Web Asset Move Summary

**`templates/` and `static/` now live inside `src/bobbytailor/web/` with `create_app` reduced to bare `Flask(__name__)` — the `parents[3]` repo-root reach-up is deleted and the package is self-contained; Master/Masterv2/design-system archived under `docs/`.**

## Performance

- **Duration:** 21 min
- **Started:** 2026-08-02T23:00:23Z
- **Completed:** 2026-08-02T23:21:17Z
- **Tasks:** 2
- **Files moved/modified:** 20 renamed, 5 modified

## Accomplishments

- **Step 4 — legacy docs archived.** `Master.md` (67 KB) and `Masterv2.md` (110 KB) moved to `docs/archive/`; `design-system/` moved to `docs/design/` (MASTER.md + pages/reports.md + pages/projects.md). All five moves are 100%-similarity `git mv` renames — full history and blame preserved. The three code-side references were repointed; the repo root is now free of legacy planning docs.
- **Step 5 — the one structural move with real payoff.** `templates/` (3 HTML) and `static/` (12 JS/CSS) relocated into `src/bobbytailor/web/`. `create_app` went from a 6-line `Flask(...)` construction with a `parents[3]` reach-up to a one-line `Flask(__name__)`: `app.root_path` was *already* `src/bobbytailor/web/`, so the move aligns the folders with Flask's default resolution instead of fighting it. The now-orphaned `pathlib.Path` import came out with it.
- **Wheel packaging fixed as a freebie (R10).** `[tool.setuptools.package-data]` declares `web/templates/*.html` + `web/static/**/*`, closing the latent break where a built wheel would have shipped an assetless package.
- **Proved cwd-independence.** The click-through smoke (login → dashboard → reports → settings, plus a 200-check on every one of the 12 static assets through `url_for('static', ...)`) passes identically from the repo root and from an unrelated `/tmp` cwd — the previous behavior depended on the process being rooted at the repo.

## Task Commits

1. **Task 1: Step 4 — archive Master/Masterv2 + move design-system** — `a99c55a` (docs)
2. **Task 2: Step 5 — relocate templates/static into the package, drop the root hack** — `5199e28` (refactor)

## Files Created/Modified

**Moved (git mv, history preserved):**
- `Master.md` → `docs/archive/Master.md`
- `Masterv2.md` → `docs/archive/Masterv2.md`
- `design-system/bobby-tailor/{MASTER.md, pages/reports.md, pages/projects.md}` → `docs/design/bobby-tailor/…`
- `templates/{index,login,settings}.html` → `src/bobbytailor/web/templates/`
- `static/{app.js, style.css, settings.js, ui-motion.js, ui-polish.css, js/**}` → `src/bobbytailor/web/static/` (12 files)

**Modified:**
- `src/bobbytailor/web/app.py` — `create_app` is now `app = Flask(__name__)`; `repo_root = Path(__file__).resolve().parents[3]`, `template_folder=`, `static_folder=` and the `pathlib.Path` import all deleted
- `pyproject.toml` — new `[tool.setuptools.package-data]` block
- `src/bobbytailor/web/static/style.css` (lines 5–6), `src/bobbytailor/web/static/app.js` (line 5) — comment refs repointed at `docs/design/bobby-tailor/MASTER.md`
- `tests/test_extraction_prompt.py` (line 1 docstring) — repointed at `docs/archive/Masterv2.md`

## Decisions Made

1. **Comment refs point at the live design contract, with the archived section numbers kept.** The plan/spec mandate repointing `Tokens/Layout: Master.md §8.x` at `docs/design/bobby-tailor/MASTER.md`. But `§8.1/§8.2` are sections of the *archived* `Master.md`, not of the design-system file. Rather than drop a true pointer, both are kept: `Tokens: docs/design/bobby-tailor/MASTER.md (Color Palette / Typography / Spacing)` and `Layout: … (Page Pattern); legacy: docs/archive/Master.md §8.2`. Both paths resolve; nothing dangles.
2. **`pathlib.Path` import removed from `web/app.py`.** After the `parents[3]` deletion it had no other consumer in the file (grep-verified) — the plan explicitly permits this.
3. **`§8.x` section pointers left alone.** `index.html:164,210,279,295` and `app.js:133,360,568,861,1287` cite `Master §8.3`-style *section numbers*, not file paths (RESTRUCTURE-SPEC M5 predicted this) — zero edits needed.
4. **`.planning/` refs left as-is** — historical records, per RESTRUCTURE-SPEC §4.2 "in place, no move".

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] `gitnexus impact` required a `--repo` selector**

- **Found during:** Task 2 (pre-edit impact analysis mandated by CLAUDE.md)
- **Issue:** The MCP `gitnexus_*` tools are not reachable in this runtime (same as 22-02 deviation 4). The CLI fallback `gitnexus impact create_app --direction upstream` failed with `Multiple repositories indexed. Specify which one with the "repo" parameter.`
- **Fix:** Re-ran with `--repo Bobby-Tailor-Automation-2.0`.
- **Result reported before the edit:** `risk: LOW`, `impactedCount: 0`, 0 direct callers / 0 affected processes / 0 affected modules — `create_app` is an entrypoint factory invoked by `app.py` and instantiated dynamically in tests, so it has no indexed upstream callers. Not CRITICAL → proceeded per the plan's gate.
- **Files modified:** none (tooling invocation only)

**2. [Rule 2 — Missing critical] Comment string in `pyproject.toml` broke a literal acceptance grep**

- **Found during:** Task 2
- **Issue:** The explanatory comment above the new block contained the word `package-data`, so `grep -c 'package-data' pyproject.toml` returned `2` where the acceptance criterion demands exactly `1`.
- **Fix:** Reworded the comment to "declare them below" so only the `[tool.setuptools.package-data]` header matches.
- **Verification:** `grep -c 'package-data' pyproject.toml` → `1`
- **Committed in:** `5199e28`

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 acceptance-criterion correctness)
**Impact on plan:** None on scope. Both were mechanical; no behavior change beyond the planned one.

## Issues Encountered

1. **GitNexus index is stale** (`last indexed: 92c48cc`) and this plan's 20 renames make it staler. This is *by design* — the reindex is Step 8, owned by 22-04. The `create_app` impact result above is still trustworthy: nothing in 22-01/22-02 touched the web factory's call graph. `gitnexus detect-changes` was run after both commits and reports `No changes detected` (expected — the working tree is clean and the index predates the commits).
2. **Playwright `EPIPE` noise after the smoke script exits.** `create_app` kicks off a background StackCT project sync that spawns the Playwright driver; when the short-lived Python process exits, the node driver logs an unhandled `EPIPE`. It happens *after* `SMOKE OK` prints and is unrelated to this change (pre-existing shutdown-ordering artifact of the background prefetch thread).
3. **Known synthetic-fixture churn.** `tests/fixtures/synthetic/{dimensions,floorplan,symbols}_synthetic.pdf` are regenerated byte-size-identically by every suite run (PDF metadata timestamps). They were *not* included in either commit; the three files were restored with a targeted `git checkout --` so the tree ends clean.
4. **CWD-relative `output/`/`uploads/` confirmed unchanged.** Running the smoke from `/tmp` created `output/` and `uploads/` *there* — `create_app`'s literal `os.makedirs("output/screenshots")` / `os.makedirs("uploads")` at `app.py:64-66` are still CWD-anchored. Deliberately untouched (RESTRUCTURE-SPEC §7 item 11, deferred). Templates and static are now cwd-independent; the data dirs are not, and that gap is now the *only* remaining root-anchoring in the web layer.

## Verification

| Check | Result |
|---|---|
| `docs/archive/{Master,Masterv2}.md`, `docs/design/bobby-tailor/MASTER.md` exist | PASS |
| `Master.md`, `Masterv2.md`, `design-system/` gone from repo root | PASS |
| `grep -c 'docs/design/bobby-tailor/MASTER.md'` — style.css / app.js | 2 / 1 (both ≥1) |
| `grep -rn "design-system/" … src static templates scripts` | no matches |
| `src/bobbytailor/web/templates/index.html`, `…/static/style.css` exist | PASS |
| `find templates static -maxdepth 0` (repo root) | fails — dirs gone |
| `grep 'parents\[3\]' src/bobbytailor/web/app.py` | no match |
| `grep -c 'Flask(__name__)' src/bobbytailor/web/app.py` | 1 |
| `template_folder=` / `static_folder=` args in create_app | none |
| `settings.py:16` / `seed_admin.py:31` `parents[3]` | intact (untouched) |
| `grep -c 'package-data' pyproject.toml` | 1 |
| test_client: `GET /login` / `GET /static/style.css` | 200 / 200 |
| All 12 static assets via `url_for('static', …)` | 200 each |
| Click-through `/login` → `/` → `/settings` → `/api/reports` | 200 each, templates render |
| Same click-through from an unrelated `/tmp` cwd | identical PASS |
| `app.root_path` | `…/src/bobbytailor/web` (routes: 40) |
| `pytest -q tests/test_blueprint_parity.py` | 23 passed |
| `pytest -q` after Task 1 | **1132 passed, 2 deselected** (478 s) |
| `pytest -q` after Task 2 | **1132 passed, 2 deselected** (485 s) |
| Paid API commands run | none (golden deselected by default since 22-01) |

## Self-Check: PASSED

- All `key-files.created` verified present on disk.
- Both commits verified in `git log`: `a99c55a`, `5199e28`.
- All acceptance criteria from both tasks re-run above; all pass.

## User Setup Required

None.

## Next Phase Readiness

Ready for **22-04** (wave 4): Steps 6–8 — README/DEPLOYMENT/`.env.example` truth fixes, dead JS removal, GitNexus reindex + final suite.

Two notes 22-04 must carry:

1. **Dead-JS paths shifted.** The Step 7 targets are now `src/bobbytailor/web/static/js/ui/{drawer,modal,toast,focus-trap,icons}.js` and `src/bobbytailor/web/static/js/data-grid.js`; `index.html` is at `src/bobbytailor/web/templates/index.html`. RESEARCH Pitfall 3 still stands verbatim — delete only the tags at lines 13–14; **line 15 (`reports-workspace.js`) is LIVE**.
2. **Step 6 doc path updates now have real targets.** README/DEPLOYMENT mentions of `templates/`, `static/`, and `design-system/` are stale as of this plan and need the new paths.

The GitNexus reindex at Step 8 is now genuinely required — 20 file renames landed this plan.

---
*Phase: 22-production-restructure-cleanup*
*Completed: 2026-08-03*

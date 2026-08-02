# Phase 22: Production Restructure & Cleanup - Context

**Gathered:** 2026-08-02
**Status:** Ready for planning
**Source:** PRD Express Path (.planning/codebase/RESTRUCTURE-SPEC.md)

<domain>
## Phase Boundary

This phase makes the repo a professionally structured production app WITHOUT changing behavior:
moves + deletions + doc fixes + test-isolation fixes only. It executes
`.planning/codebase/RESTRUCTURE-SPEC.md` (synthesized 2026-08-02 from the six mapper audits in
`.planning/codebase/`: ARCHITECTURE, TEST-AUDIT, CLEANUP-MANIFEST, FRONTEND, CONCERNS, DOCS-AUDIT).
All behavior changes (config unification, god-module split, scraper parity gap, generalization
fixes, frontend refactor) are explicitly OUT of this phase — they are enumerated in
RESTRUCTURE-SPEC §7 and become the production-hardening phases.

</domain>

<decisions>
## Implementation Decisions

### Order & safety (locked)
- Step order of RESTRUCTURE-SPEC §5 is LOCKED: safety rails FIRST (Step 1), then DELETE (2),
  ARCHIVE (3), docs archive (4), web-asset move (5), doc truth fixes (6), dead JS (7), reindex (8).
- Every step ends: `python3 -m pytest -q -m "not golden"` green → gitnexus detect_changes → one commit.
- NEVER run `pytest -m golden`, `scripts/accuracy_gate.sh`, `scripts/vision_only_benchmark.py`,
  or `scripts/golden_convergence.py` — paid API credits; user-authorized only.
- Python 3.9 runtime — no >3.9 syntax anywhere.
- No pytest process may be running when Step 2 (DELETE) executes.

### Safety rails (locked — Step 1, the mandatory first commit)
- `pytest.ini` gains `addopts = -m "not golden"` (opt IN to paid tests with `-m golden`).
- `tests/conftest.py`: session-scoped OUTPUT_DIR/SCREENSHOTS_DIR isolation to a session tmpdir,
  pinned BEFORE first bobbytailor import (mirrors existing LEARNING_DB_PATH pattern at conftest.py:38-41).
- Bare-MagicMock config stubs in `tests/test_takeoff_pipeline.py:27-32`,
  `tests/test_sheet_pass_matrix.py:27-40` get explicit tmp-path strings on every dir attribute;
  `tests/test_pipeline_parity.py:57-63` gets explicit OUTPUT_DIR too. Keep the stubs (hermetic
  solo runs), make attributes explicit — do NOT delete the stubs.
- `tests/test_blueprint_parity.py` upload dir → tmp if feasible without app code change; else
  defer to Step 5 with an explicit note.
- Verification for Step 1: suite green AND zero new entries under real `output/` during the run
  AND no `MagicMock/` dir reappears; run the 3 stub files SOLO as well as the full suite (R5).

### Cleanup buckets (locked)
- DELETE bucket = RESTRUCTURE-SPEC §4.1 verbatim (~1.13 GB). Untracked junk via rm -rf;
  git-tracked junk (`scripts/_diag_chelsea.json`, `scripts/network_capture.py`) via `git rm`.
- Screenshot deletions are scripted with an EXPLICIT KEEP-LIST (never negated globs).
- ARCHIVE bucket = §4.2: single zip `output/_archive/stackct-era-20260802.zip`; verify with
  `unzip -t` BEFORE removing originals. `git mv` for tracked legacy (M3–M8).
- MUST-SURVIVE contract = §4.3 verbatim, treated as an executor checklist: learning.db(+wal/shm),
  stackct.db, the 16 report-referenced VisionOnly run dirs AND their paired screenshots dirs
  (pairing table in §4.3), one-of-a-kind project runs (Chelsea, Moxy full-name, latest Crow),
  scraper reuse caches (`Crow_-_Cass_White_Road_20260630_234238`, `…-Plans_20260715_191703`).
- Sacred, never touched: uploads/, human_inputs/, reports/, tests/ fixtures (incl. ground-truth
  take-off PDFs and replay/), .planning/, docs/PIPELINE-GROUND-TRUTH.md, .env.
- Add `MagicMock/` and `output/_archive/` to .gitignore.
- Post-delete verification: `sqlite3 output/learning.db ".tables"` intact; web Reports list
  renders and sheet images load for 2–3 kept runs.

### Moves (locked)
- M1/M2: `templates/` and `static/` → `src/bobbytailor/web/{templates,static}` via `git mv`;
  delete `parents[3]` + both folder args in `src/bobbytailor/web/app.py:32-37`. Do NOT touch
  `web/settings.py:16` / `seed_admin.py:31` parents[3] (.env lookup, different purpose).
  Run gitnexus impact on create_app before the edit. Add `[tool.setuptools.package-data]` for
  web templates/static in the same commit (R10 freebie).
- M3/M4: Master.md + Masterv2.md → `docs/archive/` via git mv; update comment refs
  static/style.css:5-6, static/app.js:5, tests/test_extraction_prompt.py:1 docstring.
- M5: design-system/ → docs/design/ via git mv.
- M6–M8: audit_plan_sets.py, discover_plan_sets.py, diagnose_fixture.py → scripts/archive/
  via git mv; fix their `Path(__file__)` ROOT parent count (one level deeper).
- REJECTED moves (do not do): any `src/bobbytailor/*.py` module move, takeoff_pipeline split,
  devtools/object_manifest re-home, tests/fixtures moves.

### Dead JS (locked scope, separate commit)
- Delete `js/ui/{drawer,modal,toast,focus-trap,icons}.js` + `js/data-grid.js` (~21 KB), their
  two script tags (index.html:13-14) and orphaned `#ui-modal-root`/`#ui-toast-root` divs
  (index.html:20-21). User's revamp mandate covers this; grep-verify zero references again at
  execution time (files changed at `92c48cc`) before deleting; keep as its own commit for easy revert.

### Docs truth fixes (locked)
- README: remove nonexistent `GET /api/jobs/<job_id>` (real: /api/jobs/active, /api/jobs/history,
  /api/jobs/history/<job_id>); CLAUDE_MODEL_SCHEDULES default = falls back to CLAUDE_MODEL
  (config.py:25); CLAUDE_MODEL_CLASSIFY default = hardcoded claude-haiku-4-5 (config.py:40,
  also DEPLOYMENT.md:60); Python "3.10+" → 3.9; flag ~$0.05/run cost claim as pre-Phase-21.
- .env.example: append TAKEOFF_ACCURACY_MODE, COUNT_TILING, COUNT_TILING_GRID,
  DETERMINISTIC_ENABLED, LEARNING_ENABLED, VERIFY_RETRY_ENABLED, RASTER_FORCE, MAX_PREVIEW_ROWS
  + ADMIN_SEED_* pointer comment.
- Update path mentions of templates/static/design-system in README/DEPLOYMENT.

### Claude's Discretion
- Exact keep-list script implementation for Step 2 (language, location under scratch — must not
  land in repo unless it earns a place under scripts/).
- Commit message wording (follow the spec's suggested messages).
- Whether Step 1d (blueprint-parity uploads isolation) lands in Step 1 or defers to Step 5.
- Minor doc wording in README fixes.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The authoritative spec (read FIRST, in full)
- `.planning/codebase/RESTRUCTURE-SPEC.md` — every bucket list, pairing table, step, risk (R1–R12)

### Evidence base (read the sections cited by the spec when executing the related step)
- `.planning/codebase/CLEANUP-MANIFEST.md` — §a.4 must-survive pairing table (Step 2/3)
- `.planning/codebase/TEST-AUDIT.md` — §c MagicMock mechanism, §d output/-writing tests (Step 1)
- `.planning/codebase/FRONTEND.md` — §b dead assets, §d root-path quirk (Steps 5/7)
- `.planning/codebase/DOCS-AUDIT.md` — README wrong claims + .env.example drift (Step 6)
- `.planning/codebase/ARCHITECTURE.md` — deferred-refactor rationale (what NOT to touch)
- `.planning/codebase/CONCERNS.md` — deferred findings feeding later hardening phases

### Live files the steps touch
- `pytest.ini`, `tests/conftest.py`, `tests/test_takeoff_pipeline.py`,
  `tests/test_sheet_pass_matrix.py`, `tests/test_pipeline_parity.py`, `tests/test_blueprint_parity.py`
- `src/bobbytailor/web/app.py` (create_app factory)
- `README.md`, `docs/DEPLOYMENT.md`, `.env.example`, `.gitignore`, `pyproject.toml`

</canonical_refs>

<specifics>
## Specific Ideas

- The suite baseline is 1132 passed / 2 deselected (validated 2026-08-02, 7m45s) — that count is
  the green bar for every step.
- Step 2's deletions must be generated as an explicit manifest file (list of absolute paths) in
  the session scratchpad, reviewed against §4.3 pairing before execution — no ad-hoc globs.
- Work happens on the current branch (`accuracy/flag-dont-guess-coincidental-detections`, clean
  at `92c48cc` + planning docs); no branch switching mid-phase (R11: no other session is active).

</specifics>

<deferred>
## Deferred Ideas

RESTRUCTURE-SPEC §7 items 1–13 (behavior changes, code refactors, generalization work) —
carried forward as input to the production-hardening phase planning that follows this phase.

</deferred>

---

*Phase: 22-production-restructure-cleanup*
*Context gathered: 2026-08-02 via PRD Express Path*

---
phase: 22-production-restructure-cleanup
plan: 01
subsystem: testing
tags: [pytest, test-isolation, safety-rails, conftest, magicmock]
requires: []
provides:
  - "pytest.ini addopts excluding paid golden tests by default (opt-in via -m golden)"
  - "conftest session OUTPUT_DIR/SCREENSHOTS_DIR isolation to a bt-test-output- tmpdir (config attr-patch)"
  - "hardened MagicMock config stubs with explicit tmp-path dir attrs (no MagicMock/ regrowth)"
affects:
  - "22-02 DELETE step (suite can no longer regrow output/ junk)"
  - "22-04 doc truth fixes (README testing note landed early, one sentence)"
tech-stack:
  added: []
  patterns:
    - "config module-attribute patch in conftest (env pins lose to load_dotenv(override=True))"
    - "explicit string dir attrs on bare MagicMock config stubs for solo-run hermeticity"
key-files:
  created: []
  modified:
    - pytest.ini
    - tests/conftest.py
    - tests/test_takeoff_pipeline.py
    - tests/test_sheet_pass_matrix.py
    - tests/test_pipeline_parity.py
    - README.md
key-decisions:
  - "Step 1d (blueprint-parity uploads isolation) DEFERRED — needs an UPLOADS_DIR override in create_app, a behavior change out of scope; finally-blocks self-clean (RESEARCH Open Q1; goes to SPEC §7 CWD-relative anchoring)"
  - "conftest config import wrapped in try/except matching _ensure_real — config crash-fails on missing env vars in bare CI environments"
duration: 17min
completed: 2026-08-02
status: complete
---

# Phase 22 Plan 01: Safety Rails (Paid-Test Exclusion + Output Isolation) Summary

**One-liner:** Bare `pytest` now deselects the two paid golden E2E tests via `pytest.ini` addopts, and the whole test session writes to a `bt-test-output-` tmpdir instead of real `output/` via a conftest config attr-patch — closing both holes before the ~1.13 GB cleanup steps.

## What Was Done

### Task 1: Step 0 — Preconditions and baseline (no commit)
- Confirmed no pytest process running, branch `accuracy/flag-dont-guess-coincidental-detections`, in-flight tree state preserved (nothing reverted).
- `python3 -m pytest --collect-only -q -m "not golden"` → `1132/1134 tests collected (2 deselected)` — the golden marker expression deselects exactly the two paid tests.
- Full offline suite green bar established (see Task 3 verification: 1132 passed / 2 deselected, 471s).
- No paid command (`-m golden`, accuracy_gate.sh, vision_only_benchmark.py, golden_convergence.py) was ever run.

### Task 2: Step 1a/1b — pytest.ini addopts + conftest isolation
- `pytest.ini`: added `addopts = -m "not golden"` under `[pytest]`; existing `markers` block untouched. Bare `pytest --collect-only -q` (no `-m`) now shows `2 deselected`.
- `tests/conftest.py`: new isolation block after the ENSEMBLE env pins and BEFORE the `_ensure_real` pre-import loop — `tempfile.mkdtemp(prefix="bt-test-output-")`, then `config.OUTPUT_DIR = <tmp>` and `config.SCREENSHOTS_DIR = <tmp>/screenshots` as **module-attribute patches** (RESEARCH Pitfall 1: an env `setdefault` is silently defeated by `config.py:10 load_dotenv(override=True)` because `.env` defines OUTPUT_DIR; SCREENSHOTS_DIR is derived, not env-driven, so it MUST be attr-patched). Placement guarantees `reporter.py:16` captures the tmp value by-value at its pre-import; `pdf_analyzer` imports lazily after conftest.
- RED/GREEN evidence (task was `tdd="true"`): before the edit, the verify assertion failed with `AssertionError: ./output`; after, it prints `isolated: /var/folders/.../bt-test-output-9x87d3w3`. Per the plan's locked one-commit-per-step rule, RED/GREEN were verified inline rather than committed separately (plan `<done>`: "Staged, not yet committed").
- README: one sentence added under "Run all tests" noting the golden opt-in.

### Task 3: Step 1c/1d — stub hardening, 1d deferral, verify, commit
- `tests/test_takeoff_pipeline.py` `_CONFIG_MOCK`: `OUTPUT_DIR = "/tmp/bt-tp-out"`, `SCREENSHOTS_DIR = "/tmp/bt-tp-out/screenshots"`.
- `tests/test_sheet_pass_matrix.py` `_CONFIG_MOCK`: `OUTPUT_DIR = "/tmp/bt-spm-out"`, `SCREENSHOTS_DIR = "/tmp/bt-spm-out/screenshots"`.
- `tests/test_pipeline_parity.py` `_CONFIG`: added `OUTPUT_DIR = "/tmp/test_screens_out"` (SCREENSHOTS_DIR was already a string). Stubs KEPT — only attrs added.
- Step 1d DEFERRED (no edit to `tests/test_blueprint_parity.py` — byte-unchanged, confirmed via `git diff --name-only`): pointing its upload dir at tmp requires `create_app` to read an UPLOADS_DIR override — a behavior change out of scope for this no-behavior-change phase. Its finally-blocks already self-clean; carried to RESTRUCTURE-SPEC §7 CWD-relative anchoring. Recorded in the commit message body.
- **Commit:** `10cd7be` — `test: exclude paid golden marker by default + isolate OUTPUT_DIR/SCREENSHOTS_DIR from real output/` (9 files, +43/-0).

## Verification Results

| Check | Result |
|-------|--------|
| Bare `python3 -m pytest --collect-only -q` | `1132/1134 tests collected (2 deselected)` ✓ |
| Full offline suite `python3 -m pytest -q -m "not golden"` | **1132 passed, 2 deselected**, exit 0, 471.62s ✓ |
| `ls output/ \| wc -l` before/after full suite | 455 == 455; entry SET identical to pre-run snapshot ✓ |
| 3 stub files together (170 tests) + each individually solo | all green; `test ! -d MagicMock` after every run ✓ |
| conftest isolation import | `config.OUTPUT_DIR` = `/var/.../bt-test-output-*`; `SCREENSHOTS_DIR` ends `screenshots` ✓ |
| `test_blueprint_parity.py` byte-unchanged | ✓ (1d deferred) |
| Change scope | exactly the 6 intended files + 3 regenerated synthetic fixture PDFs ✓ |

Note on the MagicMock regrowth check: a pre-existing 0-byte `MagicMock/` junk dir (a §4.1 DELETE-bucket item for plan 22-02) was temporarily moved aside so `test ! -d MagicMock` was meaningful, then restored byte-exact after verification so 22-02's DELETE manifest stays accurate.

## Deviations from Plan

### Auto-fixed / adjusted

**1. [Rule 2 - Robustness] conftest config import wrapped in try/except**
- **Found during:** Task 2
- **Issue:** The plan's literal `import bobbytailor.config as _config` would crash the whole test session in env-less CI (config.py:140 `validate_required_env()` raises on missing vars) — the exact case the adjacent `_ensure_real` loop deliberately swallows.
- **Fix:** Wrapped the isolation import in `try/except Exception` matching the file's graceful-degradation pattern; the hardened parity stubs fill the gap when config is unavailable.
- **Files modified:** tests/conftest.py
- **Commit:** 10cd7be

**2. [Rule 3 - Blocking] Pre-change full-baseline output lost; post-change run used as the green bar**
- **Found during:** Task 1→3 transition
- **Issue:** The background baseline run's captured output was empty (runner limitation). Re-running the pre-change baseline would have required reverting the Step 1 edits.
- **Fix:** The collect-only baseline (`2 deselected`) was captured pre-change; the full-suite green bar (1132 passed / 2 deselected) was established on the post-change tree — which is the state every later step must preserve. The pre-change baseline was independently validated same-day per 22-CONTEXT (1132 passed / 2 deselected, 7m45s).

**3. [Tooling] `gitnexus_detect_changes()` unavailable — scope verified via git**
- **Found during:** Task 3
- **Issue:** GitNexus detect-changes/impact are MCP-only tools not exposed to this executor agent; the CLI has no equivalent subcommand.
- **Fix:** Commit scope verified with `git status`/`git diff --stat`: exactly the 6 intended files (+ the 3 known-churn synthetic fixture PDFs), zero deletions, no production symbols touched. GitNexus index remains stale (last indexed `92c48cc`) — reindex is the phase's locked Step 8 (plan 22-04).

**4. [Scope note] Synthetic fixture PDFs included in the commit**
- The offline suite regenerates `tests/fixtures/synthetic/*.pdf` (PDF-timestamp byte churn, content-identical). Included in the task commit per orchestrator instruction — they are tracked files and leaving them dirty would pollute later steps' `detect_changes` scope.

## Known Stubs

None introduced. The three `_CONFIG_MOCK`/`_CONFIG` MagicMock stubs are pre-existing intentional solo-run hermeticity fixtures (kept per locked decision); this plan only added explicit string dir attributes to them.

## Threat Flags

None — no new security surface. T-22-01 (paid-API budget denial) and T-22-02 (real-output tampering) both mitigated as planned.

## Next Phase Readiness

- The suite can no longer spend paid credits by accident nor regrow `output/` junk — plan 22-02 (DELETE ~1.13 GB) is now safe to execute.
- `MagicMock/` still exists on disk (restored intentionally) — it is 22-02's DELETE-bucket item.
- GitNexus reindex deliberately deferred to Step 8 (plan 22-04).

## Self-Check: PASSED

- pytest.ini contains `addopts = -m "not golden"` — FOUND
- tests/conftest.py isolation block — FOUND
- Explicit dir attrs in all 3 stub files — FOUND
- README golden opt-in note — FOUND
- Commit 10cd7be — FOUND in git log

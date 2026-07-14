---
phase: 21-accuracy-learning-engine
reviewed: 2026-07-15T00:00:00Z
depth: standard
files_reviewed: 45
files_reviewed_list:
  - scripts/accuracy_gate.sh
  - scripts/vision_only_benchmark.py
  - src/bobbytailor/__init__.py
  - src/bobbytailor/config.py
  - src/bobbytailor/deterministic/dimensions.py
  - src/bobbytailor/deterministic/plan_deterministic_legends.py
  - src/bobbytailor/deterministic/rooms.py
  - src/bobbytailor/deterministic/scale_solver.py
  - src/bobbytailor/deterministic/symbols.py
  - src/bobbytailor/deterministic/tables.py
  - src/bobbytailor/deterministic/viewports.py
  - src/bobbytailor/deterministic/walls.py
  - src/bobbytailor/devtools/companion_takeoff.py
  - src/bobbytailor/learning/__init__.py
  - src/bobbytailor/learning/distill.py
  - src/bobbytailor/learning/retrieval.py
  - src/bobbytailor/learning/store.py
  - src/bobbytailor/pipeline/aggregator.py
  - src/bobbytailor/pipeline/calculator.py
  - src/bobbytailor/pipeline/pdf_analyzer.py
  - src/bobbytailor/pipeline/reporter.py
  - src/bobbytailor/pipeline/sheet_pass_matrix.py
  - src/bobbytailor/pipeline/takeoff_pipeline.py
  - src/bobbytailor/scrape/capture_manifest.py
  - src/bobbytailor/scrape/scraper.py
  - src/bobbytailor/vision/claude_analyzer.py
  - src/bobbytailor/vision/ensemble.py
  - src/bobbytailor/vision/fusion.py
  - src/bobbytailor/vision/overlay.py
  - src/bobbytailor/vision/prompts.py
  - src/bobbytailor/vision/schemas.py
  - src/bobbytailor/vision/verify_retry.py
  - src/bobbytailor/web/app.py
  - src/bobbytailor/web/blueprints/__init__.py
  - src/bobbytailor/web/blueprints/auth.py
  - src/bobbytailor/web/blueprints/jobs.py
  - src/bobbytailor/web/blueprints/projects.py
  - src/bobbytailor/web/blueprints/reports.py
  - src/bobbytailor/web/blueprints/runs.py
  - src/bobbytailor/web/blueprints/settings.py
  - src/bobbytailor/web/blueprints/verify.py
  - src/bobbytailor/web/jobs_runtime.py
  - src/bobbytailor/web/seed_admin.py
  - src/bobbytailor/web/settings.py
  - tests/replay_analyzer.py
findings:
  critical: 2
  warning: 8
  info: 6
  total: 16
status: issues_found
---

# Phase 21: Code Review Report

**Reviewed:** 2026-07-15
**Depth:** standard
**Files Reviewed:** 45
**Status:** issues_found

## Summary

Reviewed the Phase 21 accuracy/learning engine at standard depth: the new SQLite learning store (`learning/`), the deterministic-first pipeline (`takeoff_pipeline`, `deterministic/*`, `vision/*`), the benchmark gate scripts, and the Flask blueprint split (`web/*`). The deterministic geometry, fusion, ensemble/budget-guard, and verify-retry modules are carefully built — parameterized SQL throughout the learning store, structural no-overwrite guards in fusion, resource caps against hostile PDFs, and honest flag-don't-guess conventions. Python 3.9 compatibility checked: no 3.10+ syntax found (PEP 585 generics used are 3.9-safe; `from __future__ import annotations` present where needed; all files parse).

Two Critical defects were found: a hardcoded admin password committed in `seed_admin.py`, and a missing `job_store` import in the newly extracted `jobs_runtime.py` that makes job-history persistence silently fail (NameError swallowed by a broad except) on every single job. Warnings cover a learning-guardrail retrieval window that silently degrades as the corrections log grows, JSON-corrupting payload truncation in the store, an unreachable legacy download route created by a duplicate Flask URL rule, upload hardening gaps, the missing run-level budget cap on the StackCT path, cross-run state bleed through the shared pipeline singleton, a broken `--rescore` path in the benchmark, and a plans-only contract mismatch around manifest auto-discovery.

## Critical Issues

### CR-01: Hardcoded admin credentials committed in seed_admin.py

**File:** `src/bobbytailor/web/seed_admin.py:20-21`
**Issue:** The admin seeding script hardcodes the production admin credentials in source:

```python
ADMIN_EMAIL: str = "admin@bobbytailor.com"
ADMIN_PASSWORD: str = "BobbyTheAdmin@1"
```

The module docstring claims "The plaintext password is never logged, printed, or persisted", but the plaintext password IS persisted — in the repository itself. Anyone with read access to the repo (or its history) knows the deployed admin password; the `del ADMIN_PASSWORD` on line 31 is security theater. Running the script seeds a publicly known password onto the VPS.
**Fix:** Read the password interactively (never echoed) and require the email as input; rotate the exposed credential on any deployment that ran this script:

```python
import getpass
ADMIN_EMAIL = input("Admin email: ").strip()
_password = getpass.getpass("Admin password: ")
_hash = _bcrypt.generate_password_hash(_password, rounds=12).decode("utf-8")
del _password
```

### CR-02: `job_store` never imported in jobs_runtime.py — job history persistence silently broken

**File:** `src/bobbytailor/web/jobs_runtime.py:57`
**Issue:** `_persist_job_history` calls `job_store.save_job_run(...)`, but `job_store` is never imported anywhere in this module (imports are `asyncio, logging, os, threading, uuid, datetime, Path, Optional`). Every call raises `NameError`, which is swallowed by the enclosing `except Exception: logger.exception(...)` — so **no StackCT or PDF job run is ever persisted to job history**, on success, error, or cancellation. `/api/jobs/history` returns only pre-regression rows. This is a regression introduced by the 21-02 extraction of `jobs_runtime.py` out of `app.py` (verified: the file is new in this diff range and contains no import; `bobbytailor.stores.job_store.save_job_run` exists). Silent data loss — the broad except converts a hard bug into a per-job log line nobody reads.
**Fix:**

```python
# jobs_runtime.py — module imports
from bobbytailor.stores import job_store
```

Also consider narrowing the except in `_persist_job_history` so a `NameError`/`ImportError` class of failure cannot masquerade as a transient persistence error (e.g., catch `Exception` but re-raise `NameError`), and add a test that asserts `save_job_run` is invoked after a job finishes.

## Warnings

### WR-01: Learning guardrail and project-type inference silently degrade past 500 corrections

**File:** `src/bobbytailor/learning/retrieval.py:53, 273-301` (and `src/bobbytailor/learning/store.py:289-296`)
**Issue:** `load_learned_context` fetches `store.get_corrections(limit=_CORRECTIONS_SCAN_LIMIT)` — the 500 most recent corrections **across all projects** — then filters in Python for `project_key` matches to (a) infer `project_type` for repeat runs and (b) build `quantity_corrections` that drive the V3-LEARN-04 `re_verify` anti-amplification flags. Once the global log exceeds 500 rows (a handful of busy verify-batch sessions), corrections for less-recently-touched projects fall out of the window: repeat runs of those projects silently lose their type-level vocabulary/manifest retrieval AND their re_verify guardrail flags. Nothing is logged; accuracy behavior changes based on unrelated projects' activity. `store.get_corrections` supports filters for scope/run_id/etc. but has no `project_key` filter, forcing this global scan.
**Fix:** Add `project_key` to `get_corrections`' filterable columns (it is an indexed-adjacent column; extend `ix_corr_lookup` or add an index on `project_key`), then query `store.get_corrections(project_key=project_key, limit=500)` for both inference and quantity flags.

### WR-02: MAX_VALUE_LEN truncation corrupts stored JSON, then distill installs the corrupted fragment as learned data

**File:** `src/bobbytailor/learning/store.py:208-214` (with `distill.py:135-141, 209-235, 355`)
**Issue:** `_serialize` truncates the JSON **after** encoding: `_truncate(json.dumps(value))`. A payload over 2000 chars is stored as invalid JSON cut mid-token. `_deserialize`/`_parse_json` then "fall back to raw text" — meaning distillation treats the 2000-char JSON fragment as a scalar: for scope `name` it becomes the `canonical_name` inserted into `learning_vocabulary` (later rendered into prompt hints and used to rename aggregation buckets via `lookup_name`), and for assumptions the raw fragment is stored as `value`. The payload-stuffing "defense" thus converts an oversized hostile payload into silently corrupted learned vocabulary instead of rejecting it — exactly the kind of quiet takeoff-name corruption the threat model warns about.
**Fix:** Reject rather than mangle: in `record_correction`, raise `ValueError` when `len(json.dumps(value)) > MAX_VALUE_LEN` (the verify endpoints already swallow capture errors gracefully), or truncate individual string fields before `json.dumps` so the stored value remains valid JSON. Additionally, `_distill_vocabulary`/`_vocab_mapping` should length-cap and sanity-check `canonical_name` (e.g., reject values > 100 chars) before inserting.

### WR-03: Duplicate Flask route makes the legacy report download endpoint unreachable

**File:** `src/bobbytailor/web/blueprints/reports.py:159-161 and 285-291`
**Issue:** `get_report` is registered at `GET /api/reports/<run_folder>` and `download_report_legacy` at `GET /api/reports/<filename>` — structurally identical URL rules. Werkzeug matches the first-registered rule (`get_report`), so `download_report_legacy` can never match: requests for legacy flat-output files (e.g. `/api/reports/takeoff_20250101.json`) hit `get_report`, fail the `is_dir()` check, and 404. The legacy endpoint is dead code that also misleadingly appears to lack the traversal checks its sibling routes have.
**Fix:** Either delete `download_report_legacy` (if legacy flat outputs are gone) or move it to a distinct rule such as `/api/reports/legacy/<filename>` with the same `".." / "/"` sanitization used in `download_run_file`.

### WR-04: Uploads use the raw client filename and no request size cap

**File:** `src/bobbytailor/web/blueprints/runs.py:110, 264` and `src/bobbytailor/web/app.py:43-50`
**Issue:** `upload_pdf` and `run_pdf` build the save path as `os.path.join("uploads", f"{upload_id}_{f.filename}")` with the browser-supplied filename unsanitized. Full traversal is incidentally blocked by the uuid prefix gluing to the first path segment, but a filename containing `/` (or `\` on Windows) points the save into a non-existent subdirectory (500 error), and control characters/absurd names land on disk verbatim. Separately, `create_app` never sets `MAX_CONTENT_LENGTH`, so upload size is unbounded — a multi-GB POST is read to disk/memory before any validation runs (resource-exhaustion risk on an internet-facing admin app). Also `run_pdf` (line 260) calls `f.filename.endswith(".pdf")` without the None-guard and `.lower()` that `upload_pdf` has.
**Fix:** Use `werkzeug.utils.secure_filename(f.filename)` when composing `save_path`; add `MAX_CONTENT_LENGTH` (e.g. `500 * 1024 * 1024`) to `app.config`; mirror `upload_pdf`'s `if not f.filename or not f.filename.lower().endswith(".pdf")` check in `run_pdf`.

### WR-05: StackCT path has no run-level API budget cap — the "hard per-run cap" is per-sheet there

**File:** `src/bobbytailor/scrape/scraper.py:497-499, 823-826, 1229-1231` and `src/bobbytailor/pipeline/takeoff_pipeline.py:838`
**Issue:** V3-PROD-02 specifies one hard per-run spend cap (`API_BUDGET_PER_RUN_USD`). The scraper calls `_pipeline.run_sheet(...)` directly per sheet without passing `budget`, and `self._run_budget` is only set inside `run_project` (the PDF-upload path). `run_sheet` therefore falls back to `BudgetGuard(self._settings.budget_usd)` **freshly per sheet** — a 50-sheet StackCT job can legally spend 50× the configured per-run cap. The code comment at takeoff_pipeline.py:718-720 acknowledges the gap ("21-15 parity will thread the run-level guard there too") but the phase shipped without it, so the cost-runaway mitigation is absent on one of two production entry points.
**Fix:** In `run_project_scrape` and `run_analyze_from_manifest`, create one `BudgetGuard(_pipeline.settings.budget_usd)` per run and pass it to every `run_sheet(..., budget=run_guard)` call (including the linked-sheet pass); surface its final `_budget_state` on the report like `run_project` does.

### WR-06: Shared mutable pipeline singleton + unbounded concurrent job threads → cross-run learning/manifest bleed

**File:** `src/bobbytailor/scrape/scraper.py:44, 553-557, 786-787, 958` with `src/bobbytailor/web/blueprints/runs.py:88-96, 176-182` and `src/bobbytailor/web/jobs_runtime.py:27`
**Issue:** `runs.py` spawns a daemon thread per `/api/run/...` request with no single-active-job guard, while the scraper module keeps one shared `_pipeline = TakeoffPipeline(...)` whose per-run state (`_manifest`, `_learned_context` via `load_learning`, `settings`, `_schedules_cache`) is mutated at run start and mid-run (`load_learning(project_name, _project_type)` at line 958). If two jobs overlap (trivially possible from the UI or curl), job B's `load_learning` swaps job A's LearnedContext mid-run — A's remaining sheets get B's learned prompt hints, scale priors, wall-height assumptions, and re_verify flags, silently altering takeoff output for the wrong project. Note also that `jobs_runtime.job_lock` (line 27) is defined but never acquired anywhere — the concurrency protection it advertises does not exist.
**Fix:** Either construct a fresh `TakeoffPipeline` per run in `run_project_scrape`/`run_analyze_from_manifest` (the object is cheap; the singleton comment "stateless; safe to reuse across jobs" is no longer true), or reject a second concurrent job at the endpoint (`409` when any job status == "running"), or both. Remove or actually use `job_lock`.

### WR-07: Benchmark `--rescore` of a --report-json artifact silently scores an empty summary

**File:** `scripts/vision_only_benchmark.py:715-721, 856-870`
**Issue:** `_load_rescore` detects a previously written `--report-json` artifact (`"score" in data and "takeoff_summary" not in data`) and does `data = data.get("result") or data`, per its comment "re-use its embedded result". But `main()` never writes a `result` key into the report JSON (keys are name/thresholds/meta/score/gates/...), so the fallback keeps the report dict, `_summary_of` finds no `takeoff_summary`, and scoring proceeds against an **empty summary** — every golden row scores MISSING and the tool prints confidently wrong 0% numbers instead of erroring. A rescore against the wrong artifact type should fail loudly, not fabricate a zero score.
**Fix:** Either embed the pipeline result in the report JSON (`"result": result`) so the documented path works, or make `_load_rescore` raise/exit-2 with "this is a gate report artifact — pass takeoff_result.json instead" when no `takeoff_summary`/list payload is found.

### WR-08: Plans-only contract says "manifest never auto-discovered," but resolve_project_manifest auto-discovers by project name

**File:** `src/bobbytailor/pipeline/pdf_analyzer.py:259-265, 342-350` with `src/bobbytailor/devtools/object_manifest.py:351-368, 314-333`
**Issue:** `run_pdf_analysis`'s LOCKED contract states "the plans PDF is the ONLY pipeline input. No sibling companion take-off or manifest file is ever auto-discovered … a manifest is an optional, explicitly provided dev input (manifest_path)". But `resolve_project_manifest(project_name, explicit_path=manifest_path)` falls through to `discover_manifest_path()` when no explicit path is given — slug-matching files in the `manifests/` dir(s), including a `default` fallback file that matches **every** project. A stale or default manifest silently joins any production PDF run (locking names, injecting expected-item hints, forcing needs_review rows), and the benchmark's decoy tripwire only covers companion take-off PDFs, not manifests — so this leak path is untested by the isolation assertion.
**Fix:** In the PDF path, pass an explicit opt-in: `resolve_project_manifest(project_name, explicit_path=manifest_path, search_dirs=[])` (or add `allow_discovery=False`) so discovery only runs where documented (StackCT path), or update the LOCKED docstring if manifests-dir discovery is actually intended and add a decoy-manifest assertion to `vision_only_benchmark.run_vision`.

## Info

### IN-01: Dead code in jobs_runtime — unused imports and never-used lock

**File:** `src/bobbytailor/web/jobs_runtime.py:8, 11, 27`
**Issue:** `os` and `uuid` are imported but unused; `job_lock` is defined and never acquired (see WR-06).
**Fix:** Remove the unused imports; remove or use `job_lock`.

### IN-02: Settings validation rejects the Phase-21 model lineup

**File:** `src/bobbytailor/web/settings.py:24, 26-37`
**Issue:** `VALID_MODELS` still lists only `claude-haiku-4-5 / claude-sonnet-4-6 / claude-opus-4-7`; the July-2026 slugs config now defaults to (`claude-sonnet-5`, `claude-opus-4-8`, `claude-fable-5`) cannot be saved via the Settings UI, and the new `CLAUDE_MODEL_SEMANTIC/DENSE/ESCALATION/CLASSIFY` envs are absent from `ALLOWED_FIELDS`.
**Fix:** Sync `VALID_MODELS`/`ALLOWED_FIELDS` with `config.py`'s current lineup (or derive `VALID_MODELS` from `claude_analyzer.PRICING` keys).

### IN-03: run_pdf filename check crashes on missing filename and rejects ".PDF"

**File:** `src/bobbytailor/web/blueprints/runs.py:260`
**Issue:** `if not f.filename.endswith(".pdf")` raises `AttributeError` (→ generic 500) when `filename` is None and is case-sensitive, unlike `upload_pdf` (line 106). Also `Response` is imported at module top (line 10) but only the local re-import inside `object_manifest_template` is used.
**Fix:** `if not f.filename or not f.filename.lower().endswith(".pdf")`; drop the redundant import.

### IN-04: app factory hardcodes "output/screenshots" instead of SCREENSHOTS_DIR

**File:** `src/bobbytailor/web/app.py:64-66`
**Issue:** `os.makedirs(OUTPUT_DIR)` respects the env override, but the next line creates literal `output/screenshots`, creating a stray directory (and not the real one) when `OUTPUT_DIR` differs from `./output`. Downstream `mkdir(parents=True)` calls mask this, but the created path is wrong.
**Fix:** `os.makedirs(SCREENSHOTS_DIR, exist_ok=True)` using the config constant.

### IN-05: accuracy_gate.sh leaves temp dirs behind; leakage tripwires use bare `assert`

**File:** `scripts/accuracy_gate.sh:67` and `scripts/vision_only_benchmark.py:653-672, 687-693`
**Issue:** The gate exports `LEARNING_DB_PATH="$(mktemp -d)/gate_learning.db"` and never removes the directory (accumulates per gate run). In the benchmark, the ground-truth-leakage assertions (`_assert_no_ground_truth_leakage`, decoy discoverability) are bare `assert` statements — running under `python3 -O` strips them, silently disabling the isolation tripwire.
**Fix:** `trap 'rm -rf "$TMP_LEARNING_DIR"' EXIT` in the shell script; replace the asserts with explicit `raise AssertionError(...)`/`sys.exit` checks.

### IN-06: Learning scope 'name' is defined but unreachable

**File:** `src/bobbytailor/learning/store.py:45` and `src/bobbytailor/web/blueprints/verify.py:9-22`
**Issue:** `SCOPE_NAME` ("item rename raw → canonical") is a first-class distillation input (`VOCAB_SCOPES`), but no endpoint ever records it — the verify blueprint's scope table maps only item/unit/missed_item/scale/wall_height. Rename vocabulary can currently only accrete indirectly via `unit` corrections whose canonical_name falls back to the raw pattern, so the "correction made once never recurs" naming loop is only partially wired.
**Fix:** Either add a rename capture path in the verify UI/endpoints or document that scope 'name' is reserved for a future phase.

---

_Reviewed: 2026-07-15_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

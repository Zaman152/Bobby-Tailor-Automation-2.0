---
phase: 21-accuracy-learning-engine
fixed_at: 2026-07-15T00:00:00Z
review_path: .planning/phases/21-accuracy-learning-engine/21-REVIEW.md
iteration: 1
findings_in_scope: 10
fixed: 10
skipped: 0
status: all_fixed
---

# Phase 21: Code Review Fix Report

**Fixed at:** 2026-07-15
**Source review:** `.planning/phases/21-accuracy-learning-engine/21-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 10 (2 Critical + 8 Warning; 6 Info findings excluded by `fix_scope=critical_warning`)
- Fixed: 10
- Skipped: 0
- Suite: full non-golden suite run and green after EVERY fix commit; final state **854 passed, 5 skipped** (baseline 828 passed, 5 skipped — +26 new regression tests). No golden (paid API) tests were run.

## Fixed Issues

### CR-01: Hardcoded admin credentials committed in seed_admin.py

**Files modified:** `src/bobbytailor/web/seed_admin.py`, `tests/test_seed_admin.py` (new), `docs/DEPLOYMENT.md`, `README.md`
**Commit:** d9949d5
**Applied fix:** Removed the plaintext credential literal from source. Seeding now reads `ADMIN_SEED_PASSWORD` from the environment (per binding constraint; the review's interactive-getpass suggestion was adapted to the env-var/`--generate` contract) or generates a random password with `--generate` (printed exactly once); it fails loudly with instructions when absent, enforces a 12-char minimum, and no longer executes at import time (the old module seeded `.env` on import). Only the bcrypt hash reaches `.env`. Docs updated.
**REQUIRED MANUAL STEP — credential rotation:** the old literal (`BobbyTheAdmin@1` / `admin@bobbytailor.com`) remains in git history and may be live on any deployment that ran the old script. Rotate the deployed admin password (re-run the new seeder with a fresh `ADMIN_SEED_PASSWORD`, restart the app) — source removal does not rotate deployed credentials.

### CR-02: `job_store` never imported in jobs_runtime.py — job history persistence silently broken

**Files modified:** `src/bobbytailor/web/jobs_runtime.py`, `tests/test_job_history_api.py`
**Commit:** f1d74bf
**Applied fix:** Added `from bobbytailor.stores import job_store` at module top. Narrowed the swallow in `_persist_job_history`: wiring-bug classes (`NameError`/`ImportError`/`AttributeError`) now re-raise instead of masquerading as transient persistence errors; genuine runtime persistence errors still log-and-continue. Added end-to-end regression tests proving a finished `_pdf_job` (success AND error paths) lands a row in `job_runs`, plus a direct `_persist_job_history` unit test.

### WR-01: Learning guardrail and project-type inference silently degrade past 500 corrections

**Files modified:** `src/bobbytailor/learning/store.py`, `src/bobbytailor/learning/retrieval.py`, `tests/test_learning_store.py`, `tests/test_learning_retrieval.py`
**Commit:** 84b1eb7
**Applied fix:** `get_corrections` gained an additive `project_key` filter (SQL-level, backed by a new `ix_corr_project` index created idempotently by the existing `IF NOT EXISTS` schema init — no migration needed). `load_learned_context` now queries `store.get_corrections(project_key=..., limit=500)` instead of scanning the 500 most recent global rows, so other projects' activity can never evict a project's `re_verify` guardrail flags or its project_type inference. Existing API signatures preserved (additive parameter). Regression tests at both store level (query filter) and retrieval level (scan-limit churn survival).

### WR-02: MAX_VALUE_LEN truncation corrupts stored JSON, then distill installs the corrupted fragment

**Files modified:** `src/bobbytailor/learning/store.py`, `src/bobbytailor/learning/distill.py`, `tests/test_learning_store.py`
**Commit:** 22da7dd
**Applied fix:** `_serialize`/`record_correction` now REJECT (raise `ValueError`) any value/item_pattern whose serialized form exceeds `MAX_VALUE_LEN`, instead of truncating mid-token; the capture endpoints already swallow such errors gracefully (21-09 best-effort convention), so a rejected oversized correction never breaks a verify save. Distill added a vocabulary sanity gate (`canonical_name` non-empty and ≤100 chars, `unit` ≤20 chars) so a stuffed payload can never be installed as learned vocabulary that would flow into prompt hints and aggregation renames. `_deserialize`'s raw-text fallback is retained for legacy pre-fix rows. The old truncation test was replaced with rejection + distill-gate regression tests.

### WR-03: Duplicate Flask route makes the legacy report download endpoint unreachable

**Files modified:** `src/bobbytailor/web/blueprints/reports.py`, `tests/test_blueprint_parity.py`
**Commit:** 030e936
**Applied fix:** Deleted `download_report_legacy` (`GET /api/reports/<filename>`). Verified against templates/static JS before choosing deletion over re-pathing: no caller uses a flat report download — all downloads go through `/api/reports/<run_folder>/<filename>` (`static/app.js:1196`), and no `url_for("reports.download_report_legacy")` exists. Live-route parity is unchanged because the rule could never match (structurally identical to `get_report`'s rule, registered second). Added a shadowed-duplicate-URL-rule tripwire test so any future identical rule fails CI; updated the parity route inventory.

### WR-04: Uploads use the raw client filename and no request size cap

**Files modified:** `src/bobbytailor/web/blueprints/runs.py`, `src/bobbytailor/web/app.py`, `src/bobbytailor/config.py`, `.env.example`, `tests/test_blueprint_parity.py`
**Commit:** 174266a
**Applied fix:** `upload_pdf` and `run_pdf` compose save paths via `werkzeug.utils.secure_filename` (with a safe fallback for fully-hostile names); extension validation runs on the original filename first. `create_app` sets `MAX_CONTENT_LENGTH` from the new `MAX_UPLOAD_MB` config (default 500 MB) so oversize POSTs are rejected 413 before being read. `run_pdf` got the missing None-guard + case-insensitive `.pdf` check (also resolving the crash half of IN-03). Endpoint regression tests: 413 on oversize, sanitized on-disk path, missing/uppercase filename handling.

### WR-05: StackCT path has no run-level API budget cap — per-sheet instead of per-run

**Files modified:** `src/bobbytailor/scrape/scraper.py`, `src/bobbytailor/pipeline/takeoff_pipeline.py` (comment), `tests/test_pipeline_parity.py`, `tests/test_scraper_analyze_manifest.py`, `tests/test_scraper_pipeline.py`, `tests/test_scraper_two_phase.py`
**Commit:** 7f4d6a9
**Applied fix:** `run_project_scrape` and `run_analyze_from_manifest` each construct ONE `BudgetGuard(settings.budget_usd)` per run and pass `budget=run_budget` into every `run_sheet` call — main analyze pass, analyze-only pass, and the linked-sheet pass (`_discover_and_add_linked_sheets` gained a `run_budget` parameter) — exactly the 21-13 pattern `run_project` uses on the PDF path (V3-PROD-02). Final `_budget_state` is stamped on every sheet dict, matching `run_project`. Parity tests assert a single shared guard instance across all `run_sheet` calls plus source-level guards; scraper test doubles updated to accept the new `budget` kwarg.

### WR-06: Shared mutable pipeline singleton + unbounded concurrent job threads → cross-run bleed

**Files modified:** `src/bobbytailor/web/jobs_runtime.py`, `src/bobbytailor/web/blueprints/runs.py`, `tests/test_blueprint_parity.py`
**Commit:** 5825f27
**Applied fix:** Chose the minimal correct option sanctioned by the review that preserves the 21-15 LOCKED-adjacent decision ("scraper keeps `_pipeline` singleton" — the test patch seam): a single-active-job guard. New `jobs_runtime.register_job()` atomically checks-and-registers under the previously never-acquired `job_lock`; all three run endpoints (`/api/run/stackct`, `/api/pdf/run`, `/api/run/pdf`) refuse a second concurrent job with `409 + active_job_id` while any job is queued/running (the legacy `run_pdf` also deletes its just-saved file on rejection). With runs serialized, the singleton's per-run state (`LearnedContext`, manifest, settings, schedules cache) can no longer bleed across overlapping runs. Regression test covers reject → slot-release → accept across both entry points.

### WR-07: Benchmark `--rescore` of a --report-json artifact silently scores an empty summary

**Files modified:** `scripts/vision_only_benchmark.py`, `tests/test_benchmark_scoring.py`
**Commit:** 264091b
**Applied fix:** Both halves of the suggested fix: `main()` now embeds the pipeline result (`"result": result`) in the `--report-json` artifact so the documented rescore path actually works, AND `_load_rescore` exits 2 with an explicit "pass takeoff_result.json instead" message when handed a gate report without an embedded result — or any dict lacking `takeoff_summary` — instead of fabricating a confident 0% score from an empty summary. CLI regression tests (subprocess, zero API): embedded-result rescore reproduces the score; legacy report and wrong-artifact dicts exit 2.

### WR-08: Manifest auto-discovery contradicts the LOCKED plans-only contract

**Files modified:** `src/bobbytailor/devtools/object_manifest.py`, `src/bobbytailor/pipeline/pdf_analyzer.py`, `src/bobbytailor/scrape/scraper.py`, `src/bobbytailor/web/blueprints/runs.py` (comment), `scripts/vision_only_benchmark.py`, `tests/test_object_manifest.py`, `tests/test_pipeline_parity.py`
**Commit:** 8f50be6
**Applied fix:** `resolve_project_manifest` gained `allow_discovery` (additive, default True so devtools/tests keep working). ALL THREE production call sites — `run_pdf_analysis`, `run_project_scrape`, `run_analyze_from_manifest` — pass `allow_discovery=False`, removing `manifests/`-dir slug discovery AND the catch-all `default.json` from the production path on both entry points (plans-only LOCKED contract + endpoint-parity LOCKED). Note: the review's `search_dirs=[]` suggestion would NOT have worked (empty list is falsy and falls back to the default dirs) — the explicit flag is the correct mechanism. Decoy tripwire extended per constraint: the benchmark's `run_vision` now plants a discoverable `manifests/default.json` decoy (guarded, cleaned up in `finally`) and `_assert_no_ground_truth_leakage` asserts its sentinel item never surfaces; pytest tripwires cover both production entry points (spy asserts `discover_manifest_path` is never called with a discoverable catch-all present, and `run_project` receives `manifest=None`).

## Skipped Issues

None — all in-scope findings fixed.

(Info findings IN-01…IN-06 were out of scope per `fix_scope=critical_warning`. Incidental overlap: WR-06 put `job_lock` to real use (part of IN-01) and WR-04 fixed the `run_pdf` filename crash/case bug (part of IN-03); the remaining Info items — unused imports, `VALID_MODELS` sync, `SCREENSHOTS_DIR` makedirs, gate-script temp-dir cleanup / bare asserts, unreachable scope `name` — remain open.)

## Verification

- Full non-golden suite (`python3 -m pytest -q -m "not golden"`) executed after each of the 10 fix commits — green every time; golden tests never run.
- Final: **854 passed, 5 skipped, 2 deselected** (baseline 828 passed, 5 skipped — 26 regression tests added).
- Synthetic fixture PDFs (`tests/fixtures/synthetic/*.pdf`) regenerated as a test side effect were restored via `git checkout` before every commit — no fixture churn in any commit.
- Fixes were applied in an isolated git worktree on a temp branch and fast-forwarded onto `main` (e18c0b4 → 8f50be6); worktree, temp branch, and recovery sentinel cleaned up.

---

_Fixed: 2026-07-15_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_

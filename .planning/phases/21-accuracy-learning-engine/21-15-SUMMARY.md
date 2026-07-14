---
phase: 21-accuracy-learning-engine
plan: 15
subsystem: pipeline
tags: [plans-only, entry-point-parity, blob-retention, vector-probe, runsettings, isolation-test]

# Dependency graph
requires:
  - phase: 21-13
    provides: RunSettings + deterministic-first run_sheet routing (pdf_path/page_index contract)
  - phase: 21-11
    provides: ensemble_settings() reader RunSettings.from_env consumes
provides:
  - Plans-only production input contract — sibling *takeoff*.pdf and sibling manifest auto-discovery removed from pdf_analyzer (V3-LEARN-04)
  - companion_takeoff demoted to DEV/BENCHMARK ONLY (zero production imports; grep-audited)
  - plan_deterministic_legends dev-kwarg contract (dev_manifest=None, dev_companion_present=False); footprint legend gated dev-only
  - StackCT per-page vector PDF blobs retained under {run_dir}/blobs/ with legacy pdfs/ fallback + REUSE_SCREENSHOTS-style blob cache reuse
  - probe_page_vector() runtime vector/raster probe, stored as PageEntry.is_vector in the capture manifest
  - RunSettings parity — both entry points construct RunSettings.from_env() at run start (scraper singleton refresh via new settings setter)
  - Extended test_pipeline_parity.py — RunSettings/deterministic/learning call-site parity + companion isolation tests
affects: [21-16 learning runtime retrieval, 21-17 benchmark gate, 21-18]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Plans-only production input: no auto-discovery of ground-truth-adjacent siblings; dev inputs are explicit kwargs/params only"
    - "Per-run settings refresh: module-singleton pipelines rebuild RunSettings.from_env() at run start for entry-point parity"
    - "run_sheet.__globals__ patch.dict spying — order-robust cross-module call-site parity tests"

key-files:
  created: []
  modified:
    - src/bobbytailor/pipeline/pdf_analyzer.py
    - src/bobbytailor/scrape/scraper.py
    - src/bobbytailor/deterministic/plan_deterministic_legends.py
    - src/bobbytailor/devtools/companion_takeoff.py
    - src/bobbytailor/scrape/capture_manifest.py
    - src/bobbytailor/pipeline/takeoff_pipeline.py
    - tests/test_pipeline_parity.py
    - tests/test_companion_takeoff.py
    - tests/test_plan_deterministic_legends.py

key-decisions:
  - "Sibling object-manifest auto-discovery (_find_manifest) removed alongside companion discovery — explicit manifest_path is the only manifest input to run_pdf_analysis (same leakage class as *takeoff*.pdf siblings)"
  - "Blob dir renamed pdfs/ → blobs/ with _page_blob_path legacy fallback so resumed pre-21-15 runs keep vector data"
  - "companion_present renamed to explicit dev_companion_present (kept for benchmark scoring where the companion carries exact areas); footprint legend requires dev_manifest — production footprint comes from the 21-13 pipeline flow"
  - "Scraper keeps its module singleton but refreshes settings per run via a public TakeoffPipeline.settings setter — identical RunSettings.from_env() construction to pdf_analyzer without breaking scraper._pipeline test patches"
  - "Parity spies patch run_sheet.__globals__ via patch.dict — immune to the spec-load vs package-import dual-module ambiguity in the parity test harness"

patterns-established:
  - "Isolation testing: global fitz.open spy + devtools wraps-spy + namespace/source greps lock the plans-only contract at three layers"

requirements-completed: [V3-STRUCT-02, V3-LEARN-04]

coverage:
  - id: D1
    description: "Production path never auto-discovers companion take-off PDFs or sibling manifests (plans-only input contract)"
    requirement: V3-LEARN-04
    verification:
      - kind: unit
        ref: "tests/test_pipeline_parity.py#TestCompanionIsolation::test_sibling_takeoff_pdf_never_opened"
        status: pass
      - kind: unit
        ref: "tests/test_pipeline_parity.py#TestCompanionIsolation::test_companion_discovery_absent_from_production_namespaces"
        status: pass
      - kind: other
        ref: "grep -rl find_companion_takeoff_pdf src/bobbytailor/ → only devtools/companion_takeoff.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "StackCT and PDF-upload paths construct identical RunSettings and fire the same deterministic + learning call-sites"
    requirement: V3-STRUCT-02
    verification:
      - kind: unit
        ref: "tests/test_pipeline_parity.py#TestRunSettingsParity::test_both_entry_points_receive_identical_settings"
        status: pass
      - kind: unit
        ref: "tests/test_pipeline_parity.py#TestDeterministicCallSiteParity (4 tests)"
        status: pass
      - kind: unit
        ref: "tests/test_pipeline_parity.py#TestLearningCallSiteParity::test_learning_seam_exists_and_is_shared"
        status: pass
    human_judgment: false
  - id: D3
    description: "StackCT runs retain per-page vector PDF blobs (blobs/{page_id}.pdf) with a runtime vector/raster probe stored in the capture manifest"
    requirement: V3-STRUCT-02
    verification:
      - kind: unit
        ref: "tests/test_scraper_pipeline.py + tests/test_scraper_two_phase.py (16 tests, blob-aware paths)"
        status: pass
      - kind: unit
        ref: "tests/test_plan_deterministic_legends.py#test_from_run_dir_reads_blobs_dir / test_from_run_dir_falls_back_to_legacy_pdfs_dir"
        status: pass
      - kind: manual_procedural
        ref: "probe_page_vector smoke: vector 220-drawings → is_vector=True; empty page → False; unreadable → False"
        status: pass
    human_judgment: false

# Metrics
duration: 27min
completed: 2026-07-14
status: complete
---

# Phase 21 Plan 15: Plans-Only Entry Points & Blob Retention Summary

**Companion take-off auto-discovery structurally removed from production (test-enforced isolation), StackCT now retains per-page vector PDF blobs under blobs/ with a runtime vector probe, and both entry points construct identical RunSettings firing the same deterministic + learning call-sites**

## Performance

- **Duration:** 27 min
- **Started:** 2026-07-14T18:18:06Z
- **Completed:** 2026-07-14T18:45:00Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments

- **Plans-only production contract (V3-LEARN-04, LOCKED):** `pdf_analyzer.run_pdf_analysis` no longer calls `find_companion_takeoff_pdf` and no longer auto-discovers sibling manifest files (`_find_manifest` deleted). `companion_takeoff.py` carries a "DEV/BENCHMARK ONLY" docstring and has zero imports outside `devtools/` + `scripts/` (grep-audited). An isolation test places `Isolation Project-Take offs.pdf` beside the plans PDF, spies on the global `fitz.open` while the REAL legends flow runs, and proves the sibling is never opened.
- **Manifest requirements demoted:** `build_deterministic_legends(_from_run_dir)` signatures renamed to explicit dev kwargs (`dev_manifest=None`, `dev_companion_present=False`); the manifest-required footprint legend is dev-only — production footprint quantities come from the 21-13 deterministic pipeline flow.
- **StackCT blob retention (RESEARCH Open Q1):** per-page vector PDF blobs are saved to `{run_dir}/blobs/{page_id}.pdf` (legacy `pdfs/` fallback via `_page_blob_path` for resumed old runs) and reused from prior runs under REUSE_SCREENSHOTS caching, so cached pages keep vector data for the deterministic engine. Screenshots remain UI/preview only.
- **Runtime vector probe:** `probe_page_vector()` returns `{is_vector, drawing_items, words}` using the `is_vector_sheet` thresholds, is logged per page, and is persisted as `PageEntry.is_vector` in the capture manifest. Raster blobs route to the ensemble fallback exactly like raster uploads (same heuristic inside `run_sheet`).
- **RunSettings parity (V3-STRUCT-02):** the scraper constructs `RunSettings.from_env()` identically to `pdf_analyzer` and refreshes its module singleton at the start of every run (`_refresh_pipeline_settings()` + new public `TakeoffPipeline.settings` setter). `companion_present=False` hardcodes are gone from scraper.py (0 grep matches).
- **Extended parity suite:** 9 new tests — RunSettings identity across both entry points, deterministic call-site parity (a synthetic vector page fires `extract_dimension_samples` + `fuse_sheet` through the REAL `run_sheet` flow from BOTH paths), blob → `pdf_path`/`page_index` kwargs threading, hasattr-guarded learning-seam parity that strengthens automatically after 21-16, and the companion isolation pair.

## Task Commits

Each task was committed atomically:

1. **Task 1: Kill companion auto-discovery + demote manifest requirements** - `64c811c` (feat)
2. **Task 2: StackCT blob retention + RunSettings parity** - `75a18ff` (feat)
3. **Task 3: Extended parity + isolation tests** - `0722ecb` (test)

## Files Created/Modified

- `src/bobbytailor/pipeline/pdf_analyzer.py` - companion + sibling-manifest auto-discovery removed; plans-only legends call; docstring states the LOCKED input contract
- `src/bobbytailor/deterministic/plan_deterministic_legends.py` - dev-kwarg signatures; footprint gated on `dev_manifest`; blobs/ scan with pdfs/ fallback
- `src/bobbytailor/devtools/companion_takeoff.py` - DEV/BENCHMARK ONLY module docstring
- `src/bobbytailor/scrape/scraper.py` - blobs/ retention + cached-blob reuse + `probe_page_vector` + `_probe_and_record_vector` + per-run `_refresh_pipeline_settings()`; plans-only legends call sites
- `src/bobbytailor/scrape/capture_manifest.py` - `PageEntry.is_vector` field (save/load round-trip)
- `src/bobbytailor/pipeline/takeoff_pipeline.py` - public `settings` setter (parity enabler)
- `tests/test_pipeline_parity.py` - 9 new parity/isolation tests (+407 lines)
- `tests/test_companion_takeoff.py` - imports target `bobbytailor.devtools.companion_takeoff` explicitly
- `tests/test_plan_deterministic_legends.py` - 6 new tests for the plans-only/dev-kwarg contract + blobs/pdfs dir scanning

## Decisions Made

- **Sibling manifest auto-discovery removed too:** `_find_manifest` (sibling `*manifest*.json/csv` scan) is the same leakage class as `*takeoff*.pdf` discovery, and the plan's objective text mandates killing "manifest requirements on the production path". Explicit `manifest_path` (web upload flow) remains the only manifest input to `run_pdf_analysis`; `resolve_project_manifest`'s app-managed `manifests/` dir lookup is untouched.
- **`dev_companion_present` kept (not deleted):** preserves the benchmark semantic "companion carries exact areas → skip footprint" while removing the production parameter, matching the plan's "renamed dev kwarg" language.
- **Blob dir is `blobs/` (plan-mandated) with legacy `pdfs/` fallback** in `_page_blob_path` and `build_deterministic_legends_from_run_dir` so pre-21-15 run folders resumed via `run_analyze_from_manifest` keep their vector data.
- **Scraper singleton + per-run settings refresh** instead of per-run pipeline construction: keeps the `scraper._pipeline` patch seam all scraper tests rely on, while making settings construction identical (and simultaneous-patchable) with pdf_analyzer.
- **Parity spies patch `run_sheet.__globals__` via `patch.dict`** — robust against the parity harness's dual takeoff_pipeline module objects (spec-loaded vs package import), independent of collection order.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] scraper call sites updated in Task 1 (not Task 2) to keep the commit green**
- **Found during:** Task 1 (plan_deterministic_legends signature change)
- **Issue:** Renaming `companion_present` → dev kwargs would break scraper's two call sites (`companion_present=False`) and fail `test_scraper_pipeline.py` mid-plan
- **Fix:** Moved the two-call-site kwarg rename into the Task 1 commit; Task 2 kept blob/probe/RunSettings scope
- **Files modified:** src/bobbytailor/scrape/scraper.py
- **Verification:** 48 affected tests green after Task 1 commit
- **Committed in:** 64c811c

**2. [Rule 2 - Missing Critical] `PageEntry.is_vector` field added to capture_manifest.py (file not in plan's files_modified)**
- **Found during:** Task 2 (probe storage)
- **Issue:** Plan mandates "store `is_vector` in the capture manifest" but PageEntry had no such field; without it the probe result dies with the log line
- **Fix:** Added optional `is_vector: Optional[bool] = None` with load() round-trip (old manifests → None)
- **Files modified:** src/bobbytailor/scrape/capture_manifest.py
- **Verification:** test_capture_manifest.py + scraper suites green
- **Committed in:** 75a18ff

**3. [Rule 3 - Blocking] Public `settings` setter added to TakeoffPipeline (file not in plan's files_modified)**
- **Found during:** Task 2 (RunSettings parity)
- **Issue:** Per-run settings refresh on the module singleton needed a public mutation seam; only a read-only property existed
- **Fix:** Added `@settings.setter` on TakeoffPipeline with a parity docstring
- **Files modified:** src/bobbytailor/pipeline/takeoff_pipeline.py
- **Verification:** test_takeoff_pipeline.py + full suite green
- **Committed in:** 75a18ff

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 missing critical)
**Impact on plan:** All three were necessary enablers of the plan's own mandates; no scope creep.

## Verification Results

- `grep -rl find_companion_takeoff_pdf src/bobbytailor/` → only `devtools/companion_takeoff.py` (PASS)
- `grep -rl find_companion_takeoff_pdf src/bobbytailor/pipeline src/bobbytailor/scrape src/bobbytailor/web` → empty (PASS)
- `grep -c companion_present src/bobbytailor/scrape/scraper.py` → 0 (PASS)
- Both entry points contain `RunSettings.from_env()`; scraper contains `blobs/` writing + `probe_page_vector` (PASS)
- `python3 -m pytest tests/test_pipeline_parity.py -q` → 26 passed, incl. 9 new (PASS; ≥4 required)
- `python3 -m pytest tests/test_scraper_pipeline.py tests/test_scraper_two_phase.py -q` → 16 passed (PASS)
- `python3 -m pytest -q -m "not golden"` → **789 passed** (774 baseline + 15 new), 0 failed (PASS)

## Issues Encountered

None beyond the documented deviations. Synthetic fixture PDFs regenerated as a test side effect were restored before each commit (per executor instructions).

## Known Stubs

None — no placeholder values or unwired data paths were introduced. The learning-retrieval hook intentionally does not exist yet (lands in 21-16); the parity test asserts the seam with a hasattr guard exactly as the plan specifies.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plans-only contract is structurally enforced and test-locked — 21-17's benchmark gate can pass the take-off explicitly via `--takeoff-pdf` knowing the runtime can never see it.
- Learning-seam parity test strengthens automatically once 21-16 lands `retrieve_learning_hints`/`apply_learning_hints` on the shared pipeline module.
- StackCT path is vector-capable end-to-end (blob → run_sheet pdf_path → deterministic engine); manifest records per-page `is_vector` for run diagnostics.

---
*Phase: 21-accuracy-learning-engine*
*Completed: 2026-07-14*

## Self-Check: PASSED

- SUMMARY.md on disk; task commits 64c811c / 75a18ff / 0722ecb verified in git log
- All key modified files exist; acceptance-criteria greps re-verified; full suite 789 passed

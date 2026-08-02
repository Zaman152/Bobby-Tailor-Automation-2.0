# src/ Architecture Map — Bobby Tailor Automation 2.0

Audit date: 2026-08-02 · branch `accuracy/flag-dont-guess-coincidental-detections` · read-only analysis.
Scope: `src/bobbytailor` (72 .py files incl. `__init__.py`s, ~30,550 LOC) + entry points `app.py`, `main.py`, `pyproject.toml`, `requirements.txt`.

## TL;DR

- The package is a **coherent, deliberately layered pipeline** — `pipeline/` orchestrates, `deterministic/` measures, `vision/` labels, `learning/` remembers, `web/` + `scrape/` + `stores/` are delivery/IO. **No module-level circular imports exist**; four known cycles are all broken by documented lazy imports.
- **There are effectively zero orphan modules.** Every non-`__init__` module is imported by src, scripts, tests, or an entry point. The only src=0 modules are `web/seed_admin.py` (ops CLI, run via `python -m`, documented in docs/DEPLOYMENT.md:16) and `devtools/companion_takeoff.py` (evaluation-only by design, used by scripts/vision_only_benchmark.py and 2 test files).
- The **two front doors** (PDF upload via `pipeline/pdf_analyzer.run_pdf_analysis`, StackCT scrape via `scrape/scraper.run_project_scrape`) **share TakeoffPipeline for per-sheet extraction but NOT for project-level orchestration**: the scraper re-implements ~100 lines of `run_project`'s tail (project-type detect, learning refresh, wall height, estimation, budget stamping) and **never runs the autonomous project-vocabulary/naming pass at all** — the single biggest V3-STRUCT-02 parity gap.
- The worst structural debts: (1) `takeoff_pipeline.py` is a 3,209-line god-module doing settings + orchestration + hints + wall-height NLP + voting + rendering; (2) **config sprawl across 5 readers** (`config.py`, `RunSettings.from_env`, `pipeline/accuracy_config.py`, `vision/ensemble.ensemble_settings`, `web/settings.py` — the last with a **stale model list**); (3) the shared render primitive `render_clip_crop` lives in the entry-point module `pdf_analyzer.py`, forcing `vision/` to depend upward on `pipeline/` and creating the lazy-import knot; (4) `config.py` validates required env **at import time** (src/bobbytailor/config.py:140), so importing almost anything requires StackCT credentials.
- Layout verdict: the package boundaries are ~80% right. The fixes are extractions and relocations (split `takeoff_pipeline`, move `render_clip_crop` + sheet-ID parsing to a `pdfio`/`rendering` module, promote `object_manifest` out of `devtools/`, unify config), not a rewrite.

---

## (a) Per-module responsibility table

Line counts from `wc -l`. "Importers (src)" = count of src-internal importer files (from the grep edge list, §c).

### Entry points (repo root)

| File | LOC | Responsibility |
|---|---|---|
| `app.py` | 5 | Flask front door — `from bobbytailor.web.app import create_app`, runs on :5050 |
| `main.py` | 64 | CLI/cron front door for the StackCT scraper (`run_all_projects` / `run_project_scrape`, APScheduler via `RUN_SCHEDULE`) |
| `pyproject.toml` | 33 | setuptools src-layout package `bobbytailor` 2.0.0, py>=3.9, 14 runtime deps |
| `requirements.txt` | 16 | Same 14 deps duplicated for pip installs (must be kept in sync with pyproject manually) |

### `bobbytailor/` top level

| Module | LOC | Responsibility |
|---|---|---|
| `__init__.py` | 0 | Empty package marker |
| `config.py` | 140 | All env-derived constants (models, budgets, StackCT URLs, output dirs) + `validate_required_env()` **executed on import** (line 140) |

### `pipeline/` — orchestration + report generation

| Module | LOC | src importers | Responsibility |
|---|---|---|---|
| `takeoff_pipeline.py` | 3209 | 3 (pdf_analyzer, scraper, web/verify) | THE orchestrator: `RunSettings`, `TakeoffPipeline.run_project/run_sheet`, deterministic-first routing, budget guard threading, wall-height/scale/hint resolution, vocabulary build, `QuantityVerifier` |
| `pdf_analyzer.py` | 403 | 6 | **Front door #1** (PDF upload): page→PNG render, sheet-ID extraction, title-block text; also owns the shared `render_clip_crop` zoom primitive |
| `sheet_pass_matrix.py` | 330 | 3 | Sheet-type classifier (`classify_sheet_type_from_text`) + pass matrix (`plan_passes`) + model routing (`pick_model_for_pass`) |
| `accuracy_config.py` | 40 | 2 | Env-read accuracy mode toggles (`takeoff_accuracy_mode`, count tiling) |
| `calculator.py` | 1530 | 4 | Estimation tables: extracted dicts → quantity line items (`apply_estimation_tables`, `_detect_project_type`, `resolve_spec_lookups`) |
| `aggregator.py` | 449 | 1 (reporter) | Per-sheet items → project-level StackCT-style summary (`aggregate_takeoff`), name normalization, library binding |
| `reporter.py` | 987 | 3 | `generate_report` → the output run dir (takeoff.json, raw_items.csv, calculations.csv, takeoff_summary.csv, summary.txt, spec_tables.json, scale_calibration.json) |
| `cross_references.py` | 90 | 2 | Resolve "see detail 3/A5.1" refs across sheets in the same run |
| `page_text_enrichment.py` | 43 | 2 | Lump-sum component hints from the PDF text layer |

### `deterministic/` — vector-geometry measurement engine (API-free)

| Module | LOC | Responsibility |
|---|---|---|
| `viewports.py` | 753 | Viewport segmentation — split a sheet into drawing regions / title block / legends |
| `dimensions.py` | 708 | Recipe A: dimension-line samples (printed dims ↔ measured pt-lengths) |
| `walls.py` | 802 | Recipe B: wall segment extraction, LF by thickness class |
| `rooms.py` | 538 | Recipe C: room polygon closure → deterministic room/floor SF |
| `symbols.py` | 657 | Recipe D: symbol instance clustering → deterministic EA counts |
| `room_fill.py` | 277 | Recipe E: raster flood-fill enclosed-region room measurement |
| `scale_solver.py` | 492 | RANSAC per-viewport scale solve, main-plan selection, `resolve_scale_v2` |
| `printed_scale.py` | 459 | PRIMARY scale source: read printed scale labels, bind to viewports |
| `scale_extraction.py` | 261 | Printed-scale regex harvest from text layer (`dominant_scale`) |
| `scale_utils.py` | 123 | Parse one scale notation → ratio (`parse_scale`) |
| `scale_recalc.py` | 73 | Verify-workflow scale recomputation (`recompute`, `apply_overrides`) |
| `takeoff_measurements.py` | 189 | Verify-UI measurement engine (two-point calibration, polygon/polyline quantities) |
| `geometry_takeoff.py` | 374 | Legacy whole-page geometry measure (`measure_geometry`) — verify-UI reference layer |
| `footprint_takeoff.py` | 264 | Building footprint from printed overall dimensions |
| `tables.py` | 457 | Generalized deterministic schedule extraction (`extract_schedules`) |
| `schedule_extraction.py` | 306 | Door-schedule specialization (`extract_door_schedule`) |
| `component_library.py` | 1223 | Plans-only naming authority: abbreviation-key/keynote harvest → object names + aliases (`harvest_component_library`, `distill_naming_text`) |
| `plan_deterministic_legends.py` | 258 | Shared deterministic legend build for both front doors (`build_deterministic_legends[_from_run_dir]`) |

### `vision/` — Claude vision passes

| Module | LOC | Responsibility |
|---|---|---|
| `claude_analyzer.py` | 656 | Anthropic API wrapper: `analyze_drawing`, model pick, `merge_passes`, `apply_accuracy_rules` |
| `prompts.py` | 404 | Pass-scoped prompt constants |
| `schemas.py` | 439 | Structured-output JSON schemas (semantic/symbol-gallery/verify-retry/vocabulary/raster) |
| `object_vocabulary.py` | 671 | Autonomous project-vocabulary + naming-convention passes (voted, manifest replacement) |
| `overlay.py` | 385 | Set-of-Mark overlay renderer + crop-gallery builder (imports `pdf_analyzer.render_clip_crop` **top-level**) |
| `ensemble.py` | 693 | `BudgetGuard` (per-run spend cap) + self-consistency voting for raster numbers (`run_ensemble`, `vote`) |
| `fusion.py` | 1954 | V3-ACC-01 core: `build_registry` + `fuse_sheet` — vision labels bind to deterministic candidate IDs; `merge_with_provenance` |
| `verify_retry.py` | 375 | Targeted-crop verify-retry arbitration for flagged items (`retry_flagged_items`) |

### `learning/` — durable cross-run learning

| Module | LOC | Responsibility |
|---|---|---|
| `store.py` | 679 | SQLite learning store (corrections log, vocabulary, assumptions, manifests; `record_correction`, `record_ai_manifest`) |
| `retrieval.py` | 440 | Run-start `load_learned_context` → `LearnedContext` + anti-amplification guardrail (`apply_learned_quantity_flags`) |
| `distill.py` | 464 | Idempotent distillation job: corrections log → distilled tables |

### `scrape/` — StackCT browser automation (front door #2)

| Module | LOC | Responsibility |
|---|---|---|
| `scraper.py` | 1502 | **Front door #2**: `run_project_scrape` / `run_all_projects` / `run_analyze_from_manifest` — login, capture, per-sheet `_pipeline.run_sheet`, then its own project-level estimation + report |
| `browser.py` | 1186 | Playwright `StackCTBrowser` (login, catalog, page blobs, screenshots) |
| `stackct_sync.py` | 291 | Serialized browser sync → `stackct_store` (one login at a time) |
| `capture_manifest.py` | 89 | Per-run capture manifest (`RunManifest`) for re-analysis without re-scraping |
| `linked_sheets.py` | 175 | Map cross-ref sheet codes to catalog page_ids |
| `sheet_preview.py` | 146 | Match sheets to HD screenshots from past runs (web preview) |

### `stores/` — SQLite persistence

| Module | LOC | Responsibility |
|---|---|---|
| `stackct_store.py` | 585 | StackCT catalog DB (projects/plan sets/plans, freshness metadata) — `output/stackct.db` |
| `job_store.py` | 242 | Job run history (same stackct.db) |
| `project_cache.py` | 274 | DB-first catalog facade with background `stackct_sync` refresh (imports `scrape/` — layering smell, §d) |

### `web/` — Flask app

| Module | LOC | Responsibility |
|---|---|---|
| `app.py` | 131 | `create_app` factory: CSRF, login, limiter, upload cap, blueprint registration |
| `auth.py` | 110 | Flask-Login/Bcrypt/Limiter single-admin auth |
| `jobs_runtime.py` | 382 | In-memory job tracker + background threads `_stackct_job` / `_pdf_job`; single-active-job lock (WR-06) |
| `settings.py` | 164 | Read/validate/persist settings **to .env** via dotenv `set_key`; own `ALLOWED_FIELDS` + **stale** `VALID_MODELS` list |
| `seed_admin.py` | 91 | One-time admin credential seeding CLI (`python -m bobbytailor.web.seed_admin`) |
| `blueprints/__init__.py` | 18 | Blueprint re-exports |
| `blueprints/auth.py` | 55 | Login/logout routes |
| `blueprints/projects.py` | 169 | StackCT catalog + dashboard routes |
| `blueprints/runs.py` | 315 | Run initiation: `run_stackct`, `upload_pdf`, `run_pdf`, manifest upload |
| `blueprints/jobs.py` | 117 | Job status/cancel/history routes |
| `blueprints/reports.py` | 318 | Report listing/download/preview + sheet-image serving |
| `blueprints/verify.py` | 821 | Scale calibration, verify, measurement routes + learning capture (`_capture_learning`) |
| `blueprints/settings.py` | 41 | Settings page + API |

### `devtools/` — dev/eval-only inputs

| Module | LOC | Responsibility |
|---|---|---|
| `object_manifest.py` | 409 | Optional explicit object-vocabulary manifest (`resolve_project_manifest`, `allow_discovery=False` on all production paths) — **imported by 3 production modules** despite the `devtools` home |
| `companion_takeoff.py` | 312 | Parse companion take-off PDFs — evaluation-only (ground-truth scoring), src importers: 0 |

---

## (b) End-to-end takeoff data flow (with actual symbols)

### Front door #1 — PDF upload (web) 

```
POST /run-pdf  (web/blueprints/runs.py:run_pdf)
  └─ threading.Thread → web/jobs_runtime.py:_pdf_job (line 320)
       └─ pipeline/pdf_analyzer.py:run_pdf_analysis (line 251)
```

1. **PDF in → pages**: `run_pdf_analysis` renders each selected page via `_page_to_image` (PyMuPDF, long edge ≈ `RENDER_TARGET_PX`=1568, hard-capped 8000px), extracts `_sheet_name_from_doc` (title-block regex + `SHEET_ID_NOISE_PATTERNS`) and `get_title_block_text`.
2. **Sheet classify (pre-pass)**: `pipeline/sheet_pass_matrix.py:classify_sheet_type_from_text` per page → `sheet_type_hint`.
3. **Project-level pre-work** (`TakeoffPipeline.run_project`, takeoff_pipeline.py:2652):
   - `load_learning(project_key)` → `learning/retrieval.py:load_learned_context` (LearnedContext bundle: prompt hints, scale priors, wall height).
   - `_resolve_project_wall_height` (plan-text callout > learned > flagged 30 ft default).
   - Naming authority: `deterministic/component_library.py:harvest_component_library` + `distill_naming_text`, then the AI naming pass `TakeoffPipeline._build_naming_conventions` → `vision/object_vocabulary.py:extract_naming_conventions` (voted), merged by `merge_with_naming_conventions` → `self._project_vocabulary` / `_project_vocab_labels`.
   - Deterministic legends: `deterministic/plan_deterministic_legends.py:build_deterministic_legends` (called in pdf_analyzer before run_project).
4. **Per sheet** (`TakeoffPipeline.run_sheet`, line 1171):
   - classify (`classify_sheet_type_from_text`) → `plan_passes` (title_sheet → skip sentinel, zero API).
   - **Deterministic-first routing** (`_route_deterministic` → `_run_sheet_vector`, line 1966) for vector plan/schedule sheets:
     - `_deterministic_bundle` (line 1587), in order: `_sheet_schedules` (`deterministic/tables.py:extract_schedules`) → `deterministic/viewports.py:segment_viewports` → `deterministic/dimensions.py:extract_dimension_samples` → per-viewport `deterministic/scale_solver.py:solve_viewport_scale` (RANSAC) → `select_main_plan` → printed-scale primary (`deterministic/printed_scale.py:extract_printed_scales` / `match_scales_to_viewports` / `identify_main_plan_scale`) → `resolve_scale_v2` (override > printed > solved > learned prior) → off-scale-viewport geometry mask → `deterministic/walls.py:extract_walls` + `wall_lf_by_class` → `deterministic/rooms.py:extract_rooms` → `deterministic/symbols.py:cluster_symbols` → `deterministic/footprint_takeoff.py:footprint_from_page` → `_measure_room_fills` (`deterministic/room_fill.py`, per-viewport printed scale).
     - **Vision passes (labels only)**: `vision/fusion.py:build_registry` → Set-of-Mark overlay (`vision/overlay.py:render_overlay` via lazy `_render_overlay`) → `_voted_structured_vision_call` with `vision/schemas.py:semantic_labeling_schema` (main-plan + wall classes) and `symbol_gallery_schema` (symbol clusters × legend/vocab labels) → all calls charged to `vision/ensemble.py:BudgetGuard`.
     - **Fusion**: `vision/fusion.py:fuse_sheet(bundle, vision_labels, registry, vocabulary, wall_height…)` — quantities come only from geometry; then `merge_with_provenance`.
     - **Verify**: `QuantityVerifier().verify` (takeoff_pipeline.py:965) → `_verify_retry_pass` → `vision/verify_retry.py:retry_flagged_items` (bounded targeted-crop arbitration).
   - **Raster fallback**: `_run_sheet_raster` (line 2326) → `vision/ensemble.py:run_ensemble` + `vote` (self-consistency, N=3→5).
   - **Legacy vision path** (elevations/details/MEP, image-only callers): `_run_pass` per pass → `vision/claude_analyzer.py:analyze_drawing` → `merge_passes` → `apply_accuracy_rules` → `pipeline/page_text_enrichment.py:enrich_components_from_page_text`; geometry assist `_measure_geometry_safe` → `deterministic/geometry_takeoff.py:measure_geometry`.
   - Learned guardrail everywhere: `_apply_learned_flags_safe` → `learning/retrieval.py:apply_learned_quantity_flags` (re_verify flags, never substitution).
5. **Project tail** (run_project, lines 2885–2956): `pipeline/calculator.py:_detect_project_type` (once, all sheets) → `load_learning(project_key, project_type)` refresh → `learning/store.py:record_ai_manifest` (persist AI vocabulary, source='ai') → `_resolve_wall_height` → **calculator**: `apply_estimation_tables(extracted, project_type, wall_height…)` per sheet → budget stamp `_budget_state`.
6. **Post-pipeline** (back in `run_pdf_analysis`, lines 396–403): `pipeline/cross_references.py:resolve_cross_references` → `pipeline/calculator.py:resolve_spec_lookups` → **reporter**: `pipeline/reporter.py:generate_report`.
7. **Reporter/aggregator → output run dir** (reporter.py:54–189): `aggregate_takeoff` (pipeline/aggregator.py, called at reporter.py:71) builds the project summary; writes `output/<Project>_<ts>/` with `takeoff.json`, `raw_items.csv`, `calculations.csv`, `takeoff_summary.csv`, `summary.txt`, `spec_tables.json`, `scale_calibration.json`. Web serves these via `web/blueprints/reports.py`; verify/corrections flow back through `web/blueprints/verify.py:_capture_learning` → `learning/store.py:record_correction` → `learning/distill.py:distill`.

### Front door #2 — StackCT scrape

```
main.py / POST /run (runs.py:run_stackct) → jobs_runtime._stackct_job (line 202)
  └─ scrape/scraper.py:run_project_scrape (line 545)
```

- `_refresh_pipeline_settings()` (`RunSettings.from_env`, parity with pdf path), ONE `BudgetGuard`, `_pipeline.load_learning(project_name)`.
- `StackCTBrowser` (scrape/browser.py) logs in, discovers pages, downloads page blobs/screenshots into `output/screenshots/<Project>_<ts>/` + `capture_manifest.RunManifest`.
- Per sheet: `probe_page_vector` → `_pipeline.run_sheet(...)` — **same per-sheet engine as the PDF path** (module-level singleton `_pipeline = TakeoffPipeline(settings=RunSettings.from_env())`, scraper.py:46).
- Project tail is scraper-local (lines 945–1039): `_detect_project_type` → `build_deterministic_legends_from_run_dir` + `inject_project_legends` → `load_learning(project_name, type)` → `_resolve_wall_height` → `apply_estimation_tables` → `_budget_state` stamp → `resolve_cross_references` → `resolve_spec_lookups` → `generate_report`. Optional linked-sheet auto-follow via `linked_sheets.py` (`AUTO_INCLUDE_LINKED_SHEETS`).

---

## (c) Orphan detection

Method: `grep -rn -E "^\s*(from|import)\s+bobbytailor" src/ scripts/ tests/ app.py main.py` (407 hits) resolved to a target-module → importer-files edge list, cross-checked against dynamic loads (`grep importlib|spec_from_file`).

**Dynamic-import caveats found (these do NOT show in the static edge list):**
- `tests/test_takeoff_pipeline.py:49`, `tests/test_pipeline_parity.py:95`, `tests/test_sheet_pass_matrix.py:52` spec-load `takeoff_pipeline.py` / `sheet_pass_matrix.py` from file paths (hermetic solo-run pattern; see tests/conftest.py docstring).
- `tests/test_vision_schemas.py:371` uses `importlib.import_module("bobbytailor.vision.claude_analyzer")`.
- `tests/conftest.py:77` pre-imports a module list via importlib to defeat sys.modules stubs.

**Result: no true orphans.** Every non-package module has at least one static importer. The complete list of modules with **zero src-internal importers** and their actual consumers:

| Module | src | tests | scripts | entry | Verdict |
|---|---|---|---|---|---|
| `web/app.py` | 0 | 4 | 0 | 1 (`app.py`) | entry point — fine |
| `web/seed_admin.py` | 0 | 1 | 0 | 0 | **ops CLI**, run via `python -m bobbytailor.web.seed_admin` (docs/DEPLOYMENT.md:16, README.md:301) — NOT removable |
| `devtools/companion_takeoff.py` | 0 | 2 | 1 (`vision_only_benchmark.py`) | 0 | evaluation-only ground-truth parser — by design (plans-only LOCKED contract); keep, but it is dead on all production paths |
| `learning/__init__.py` | 0 | 1 | 0 | 0 | docstring-only package init |
| 7 empty package `__init__.py`s | — | — | — | — | package markers, expected |

Near-orphans worth knowing (exactly one src importer): `deterministic/scale_utils.py` (reporter only), `deterministic/takeoff_measurements.py` (web/verify only), `deterministic/geometry_takeoff.py` (scale_solver + takeoff_pipeline; verify-UI reference layer — flagged elsewhere as legacy vs. the newer solver stack), `pipeline/aggregator.py` (reporter only), `learning/distill.py` (web/verify only). All are alive; none safe to delete.

`devtools/object_manifest.py` is **mis-homed rather than orphaned**: imported by production modules `pipeline/pdf_analyzer.py:350`, `scrape/scraper.py:578`, `web/blueprints/runs.py` (manifest upload endpoint).

---

## (d) Coupling problems

1. **Circular-import knots (all currently broken by lazy imports — none broken at runtime, but fragile):**
   - `pipeline/takeoff_pipeline` ⇄ `pipeline/pdf_analyzer` via `vision/overlay` — overlay imports `render_clip_crop` from pdf_analyzer **top-level** (overlay.py:32), pdf_analyzer imports takeoff_pipeline top-level (pdf_analyzer.py:18), so takeoff_pipeline must lazy-wrap the overlay renderers (`_render_overlay`/`_build_crop_gallery`, takeoff_pipeline.py:129–134 comment). Same knot pulls in `vision/ensemble.py:564` and `vision/verify_retry` (lazy `render_clip_crop` imports).
   - `pipeline/sheet_pass_matrix` ⇄ `vision/claude_analyzer` — each defers the other (`claude_analyzer.py:73` "deferred to avoid circular import"; `sheet_pass_matrix.py:34` optional import of `_pick_model`).
   - `pipeline/takeoff_pipeline` ⇄ `pipeline/calculator` — lazy import inside `run_project` (takeoff_pipeline.py:2691, documented in the docstring).
   - Root cause of the first knot: **the low-level render primitive lives in a front-door module**. `render_clip_crop` + `_effective_render_scale` belong in a dependency-free `rendering`/`pdfio` module; that one move deletes the whole lazy-import lattice and the `vision → pipeline` upward dependency.
2. **Entry-point duplication (V3-STRUCT-02 only partially achieved):** the scraper calls `run_sheet` per sheet but re-implements `run_project`'s project tail (scraper.py:945–1039 vs takeoff_pipeline.py:2885–2956): project-type detection, second-stage learning refresh, wall-height resolve, `apply_estimation_tables` loop, budget stamping. Kept in sync only by parity tests (`tests/test_pipeline_parity.py`, `tests/test_blueprint_parity.py`). Concretely diverged already: **StackCT runs never build the autonomous project vocabulary / AI naming manifest** — `run_project` builds `_project_vocabulary` before the sheet loop (takeoff_pipeline.py:2713–2812) and persists it via `record_ai_manifest` (2899–2924); scraper.py only reads it via `getattr(_pipeline, "_project_vocabulary", None)` (scraper.py:1038, 1434), which is always the previous PDF run's value or None. Also scraper's `_resolve_wall_height` path skips the plan-text `_resolve_project_wall_height` used by run_project.
3. **Stateful module-level singleton:** `scrape/scraper.py:46` `_pipeline = TakeoffPipeline(...)` carries per-run mutable state (`_manifest`, `_learned_context`, `_schedules_cache`, `_run_budget`), which is why the web layer must enforce ONE active job (`jobs_runtime.register_job` WR-06 docstring). Fine for the single-admin product today, but it forbids concurrent runs by construction.
4. **Config sprawl — five independent env readers:**
   - `config.py` (constants at import; **hard-fails import** without STACKCT/ANTHROPIC/admin env — config.py:140);
   - `pipeline/accuracy_config.py` (reads env at call time);
   - `RunSettings.from_env` (takeoff_pipeline.py:182 — DETERMINISTIC_ENABLED, LEARNING_ENABLED, VERIFY_RETRY_ENABLED, RASTER_FORCE flags not in config.py);
   - `vision/ensemble.py:ensemble_settings` (deferred `from bobbytailor import config` at line 297);
   - `web/settings.py` (its own `ALLOWED_FIELDS` whitelist, writes .env; `VALID_MODELS` at line 24 lists only `claude-haiku-4-5 / claude-sonnet-4-6 / claude-opus-4-7` — **stale vs. config.py's Phase-21 routing models** `claude-sonnet-5 / claude-opus-4-8 / claude-fable-5`, and the settings UI cannot edit the Phase-21 knobs at all: CLAUDE_MODEL_SEMANTIC/DENSE/ESCALATION/CLASSIFY, API_BUDGET_PER_RUN_USD, ENSEMBLE_N).
5. **Two-jobs modules:** `takeoff_pipeline.py` (3,209 LOC) mixes orchestration, settings, wall-height text NLP (`_resolve_project_wall_height` + parsers, ~lines 705–918), manifest hint builders, vote helpers, tile/legend rendering, and `QuantityVerifier`. `pdf_analyzer.py` mixes front-door orchestration with the shared render/sheet-ID utility layer. `web/blueprints/verify.py` (821 LOC) mixes 3 route families + learning capture.
6. **Package-layering violations:** `stores/project_cache.py` imports `scrape/stackct_sync` (a store reaching into browser automation — the facade direction should be inverted or the sync module moved); `vision/overlay.py` imports `pipeline/` (upward, per item 1); `learning/retrieval.py` imports `vision/prompts` (learning → vision, mild).
7. **Duplicated dependency manifests:** `requirements.txt` and `pyproject.toml [project].dependencies` are identical 14-package lists maintained by hand.

## (e) Verdict: current layout vs. professional target

**Already right (keep):**
- src-layout package with setuptools config (pyproject.toml:29–33) — correct modern shape; tests import the installed/`src`-pathed package.
- The five-domain split — `deterministic/` (pure geometry, no API), `vision/` (Claude), `learning/`, `pipeline/` (orchestration), `web/`+`scrape/`+`stores/` (delivery/IO) — is a genuinely good, explainable architecture, matched by the docstring conventions (every module states its recipe/phase/requirement IDs).
- Both front doors share `TakeoffPipeline.run_sheet`, `RunSettings.from_env`, one `BudgetGuard` per run, the learning seam, and the same report tail functions (`resolve_cross_references` → `resolve_spec_lookups` → `generate_report`) — the parity foundation is real, and is even test-enforced (test_pipeline_parity.py: `test_scraper_has_pipeline_import`, `test_*_does_not_import_analyze_drawing`).
- Blueprint-per-concern web layer with an app factory; jobs isolated from Flask objects (jobs_runtime docstring).

**Should change (ranked):**
1. **Split `takeoff_pipeline.py`** into ~4 modules: `run_settings.py` (RunSettings + env flags), `orchestrator.py` (TakeoffPipeline run_project/run_sheet/routing), `project_context.py` (wall-height resolver, vocabulary build, hint builders), `quantity_verifier.py`. The patchability convention (`takeoff_pipeline.X` module-level names) means the split must keep re-export shims or update ~14 test files.
2. **Extract a `rendering`/`pdfio` module** (from pdf_analyzer: `render_clip_crop`, `_effective_render_scale`, `_page_to_image`, sheet-ID/title-block extraction) → removes every lazy-import cycle and the `vision → pipeline` upward edge; `pdf_analyzer.py` then shrinks to the true front door (`run_pdf_analysis`, `get_pdf_metadata`).
3. **Close the front-door parity gap**: move the scraper's project tail (scraper.py:945–1039) into `TakeoffPipeline` (e.g. a `finalize_project(...)` used by both paths) and run the vocabulary/naming pass on StackCT runs too — this is a behavior gap today, not just hygiene.
4. **Unify config**: one typed settings module (or extend RunSettings) as the single env reader; make `config.py` import side-effect-free (call `validate_required_env()` from the entry points, not at import — config.py:140); regenerate `web/settings.py`'s ALLOWED_FIELDS/VALID_MODELS from it (fixes the stale model list).
5. **Re-home `devtools/object_manifest.py`** (it is a production input surface — `pipeline/inputs/` or similar), leaving `devtools/` genuinely dev-only (`companion_takeoff.py`).
6. Minor renames for honesty: `stores/project_cache.py` → owns catalog reads (invert its dependency on `scrape/stackct_sync`); `deterministic/geometry_takeoff.py` is a legacy verify-reference layer and should either be labeled as such or folded into the solver stack; `web/settings.py` vs `bobbytailor/config.py` naming collision with `pipeline/accuracy_config.py` disappears under item 4.
7. Pick one dependency manifest (pyproject) and generate/constrain the other.

**What NOT to do:** do not merge `deterministic/` and `vision/` or flatten packages — the API-free/API-paid boundary is the product's core economic invariant (BudgetGuard, plans-only contract) and the current package line mirrors it exactly.

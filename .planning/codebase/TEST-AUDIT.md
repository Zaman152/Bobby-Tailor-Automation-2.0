# tests/ Audit — Bobby Tailor 2.0

Audit date: 2026-08-02. Scope: `tests/` (66 `test_*.py` files + `conftest.py`, `golden_validator.py`, `replay_analyzer.py`, `fixtures/` 8.9 MB / 30 git-tracked files). Static analysis only — the suite was NOT run.

## TL;DR

- **All 66 test files map to modules that still exist** (verified by resolving every `bobbytailor.*` import against `src/`). **Zero DELETE verdicts.** 64 KEEP, 2 soft CONSOLIDATE (two sub-1 KB files that could fold into siblings — optional).
- **Paid-API exposure is real and one flag away:** the two `@pytest.mark.golden` end-to-end tests (`test_golden_takeoff.py:146,173`) call `run_pdf_analysis` on the committed Crow/Bob's PDFs — and those PDFs ARE present in `tests/fixtures/`, so their `skipif` guards pass. `pytest.ini` has **no `addopts` deselecting `golden`**; exclusion relies entirely on developers typing `-m "not golden"` (documented only in `docs/DEPLOYMENT.md:154`). A bare `pytest tests/` spends credits.
- **Root-level `MagicMock/` is a dead unittest.mock artifact — 0 bytes, empty dirs only, safe to delete.** Cause identified: module-level `sys.modules.setdefault("bobbytailor.config", MagicMock())` stubs in `test_pipeline_parity.py` / `test_takeoff_pipeline.py` / `test_sheet_pass_matrix.py`; `os.fspath(MagicMock().SCREENSHOTS_DIR)` literally returns `'MagicMock/mock.SCREENSHOTS_DIR/<id>'`, which `pdf_analyzer.py:280-281` then `mkdir -p`'s. Dated Jul 14–15, predating the Jul 17 conftest fix. Solo-file runs can still recreate it.
- **Replay system reads NOTHING from `output/`:** `ReplayAnalyzer` resolves fixtures only from its constructor `fixture_dir` (canonically `tests/fixtures/replay/`, which is currently **empty** — just `.gitkeep`). No `output/` run dirs need preserving for the replay layer. Its only consumer today is `test_fusion.py:584-653` using `tmp_path`.
- **Fixture dead weight is small:** 4 unreferenced JSON files (~16 KB total: `sheet_coverage.json` + the three `*_manifest.json`). The two multi-MB take-off PDFs (`crow_cass_takeoff.pdf`, `bobs_discount_takeoff.pdf`, 3.3 MB combined) have zero code references but are deliberate ground-truth companions (added in phase 20-14, consumable via `vision_only_benchmark.py --takeoff-pdf`) — KEEP per the "take-offs are ground-truth-only" mission rule.
- **conftest pinning fragility:** everything uses `os.environ.setdefault`, so any developer-exported `CLAUDE_MODEL*` / `LEARNING_DB_PATH` silently overrides the pins and can break routing assertions or write to a real learning DB. The stub-neutralizing pre-import list in `conftest.py:92-103` must be manually extended whenever a test file stubs a new module — the exact failure mode that produced `MagicMock/`.

---

## (a) Test file → module table

Legend — Markers: `off` = fully offline; `golden` = paid end-to-end (marker-gated); `gen` = `generalization` marker (offline, synthetic); `skipif-local` = some tests skip unless local PDFs exist (offline PyMuPDF parsing, no API). Fixtures: `fx` = reads `tests/fixtures/`, `uploads` = reads git-ignored `uploads/` (guarded). All "module exists" checks passed — every imported `bobbytailor.*` module resolves under `src/`.

| Test file | Module(s) under test | Exists? | Markers | Fixtures | Verdict |
|---|---|---|---|---|---|
| test_aggregator.py | pipeline.aggregator | yes | off | – | KEEP |
| test_benchmark_scoring.py | scripts/vision_only_benchmark.py, scripts/accuracy_gate.sh (structural) | yes | off (canned data, subprocess `--rescore` only) | tmp-built | KEEP |
| test_blueprint_parity.py | web.app, web.auth, web.blueprints.runs, pipeline.pdf_analyzer | yes | off | writes real `uploads/` (cleaned) | KEEP |
| test_calculator_accuracy.py | pipeline.calculator | yes | off | – | KEEP |
| test_capture_manifest.py | scrape.capture_manifest | yes | off | – | KEEP |
| test_companion_takeoff.py | devtools.companion_takeoff | yes | off | – | KEEP |
| test_component_library.py | deterministic.component_library | yes | off, skipif-local | uploads (Crow, guarded :257,:275) | KEEP |
| test_confidence_flagging.py | pipeline.aggregator, calculator, reporter | yes | off | – | KEEP |
| test_count_tiling.py | pipeline.takeoff_pipeline, devtools.object_manifest | yes | off | – | KEEP |
| test_cross_references.py | pipeline.cross_references | yes | off | – | KEEP |
| test_dimensions.py | deterministic.dimensions | yes | off, skipif-local | fx (synthetic + crow/bobs PDFs) | KEEP |
| test_ensemble.py | vision.ensemble | yes | off | – | KEEP |
| test_extraction_prompt.py | vision.claude_analyzer (prompt text) | yes | off | – | CONSOLIDATE (633 B, 1 concern → fold into test_vision_schemas.py) |
| test_footprint_takeoff.py | deterministic.footprint_takeoff | yes | off, skipif-local | fx (crow PDF :112) | KEEP |
| test_fusion.py | vision.fusion, vision.overlay, pipeline.takeoff_pipeline, tests/replay_analyzer.py | yes | off | tmp replay dirs | KEEP |
| test_geometry_takeoff.py | deterministic.geometry_takeoff | yes | off | – | KEEP |
| test_golden_takeoff.py | pipeline.pdf_analyzer E2E + tests/golden_validator.py | yes | **golden (PAID)** + off unit tests | fx (crow/bobs PDFs + golden CSVs) | KEEP (must stay marker-excluded) |
| test_job_history_api.py | web.app, stores.job_store, web.auth | yes | off | – | KEEP |
| test_job_store.py | stores.job_store | yes | off | – | KEEP |
| test_learning_ai_manifest.py | learning.distill, learning.retrieval, pipeline.takeoff_pipeline | yes | off | – | KEEP |
| test_learning_capture.py | learning (capture via web endpoints), deterministic.scale_recalc | yes | off | tmp | KEEP |
| test_learning_retrieval.py | learning.retrieval, learning.distill, pipeline seams | yes | off | – | KEEP |
| test_learning_store.py | learning (store), learning.distill | yes | off | tmp | KEEP |
| test_linked_sheets.py | scrape.linked_sheets, scrape.scraper, scrape.capture_manifest | yes | off | tmp | KEEP |
| test_measure_basis.py | deterministic.component_library (measure basis) | yes | off | – | KEEP |
| test_measure_hints.py | pipeline.takeoff_pipeline, pipeline.calculator, devtools.object_manifest | yes | off | – | KEEP |
| test_naming_conventions.py | vision.object_vocabulary, fusion, aggregator, calculator, reporter, component_library | yes | off, skipif-local | fx (crow/bobs PDFs) + uploads (Chelsea/Moxy, `pytest.skip` :682) | KEEP |
| test_object_manifest.py | devtools.object_manifest, pipeline.aggregator | yes | off | – | KEEP |
| test_object_vocabulary.py | vision.object_vocabulary, vision.schemas, pipeline.takeoff_pipeline | yes | off | – | KEEP |
| test_pipeline_deterministic.py | pipeline.takeoff_pipeline, deterministic.printed_scale, viewports, vision.fusion | yes | off, skipif-local | fx (crow PDF, scale_truth.json) | KEEP |
| test_pipeline_parity.py | pipeline.pdf_analyzer, scrape.scraper, pipeline.takeoff_pipeline (parity contracts) | yes | off | tmp | KEEP (source of MagicMock/ artifact — see (c)) |
| test_plan_deterministic_legends.py | deterministic.plan_deterministic_legends | yes | off | – | KEEP |
| test_plan_sets.py | scrape.browser | yes | off | – | KEEP |
| test_printed_scale.py | deterministic.printed_scale, scale_solver, viewports, geometry_takeoff | yes | off | – | KEEP |
| test_reliability_voting.py | vision.ensemble, object_vocabulary, pipeline.takeoff_pipeline | yes | off | – | KEEP |
| test_render_fidelity.py | pipeline.pdf_analyzer (render) | yes | off, skipif-local | fx (crow PDF) | KEEP |
| test_reporter_accuracy.py | pipeline.reporter | yes | off | – | KEEP |
| test_room_fill.py | deterministic.room_fill | yes | off | synthetic in-test | KEEP |
| test_rooms.py | deterministic.rooms, walls, dimensions | yes | off, skipif-local | fx (synthetic + crow PDF) | KEEP |
| test_scale_extraction.py | deterministic.scale_extraction | yes | off, skipif-local | uploads (Moxy, skipif :106,:120) | KEEP |
| test_scale_module.py | web scale endpoints, deterministic.scale_recalc, pipeline.reporter | yes | off | tmp | KEEP |
| test_scale_recalc.py | deterministic.scale_recalc | yes | off | – | KEEP |
| test_scale_solver.py | deterministic.scale_solver, dimensions, viewports | yes | off, skipif-local | fx (crow/bobs PDFs, scale_truth.json) | KEEP |
| test_scale_utils.py | deterministic.scale_utils | yes | off | – | KEEP |
| test_schedule_extraction.py | deterministic.schedule_extraction | yes | off, skipif-local | uploads (Moxy, skipif :58) | KEEP |
| test_scraper_analyze_manifest.py | scrape.scraper (run_analyze_from_manifest), capture_manifest | yes | off | tmp | KEEP |
| test_scraper_errors.py | scrape.scraper (error paths) | yes | off | – | CONSOLIDATE (676 B → fold into test_scraper_pipeline.py) |
| test_scraper_pipeline.py | scrape.scraper, capture_manifest | yes | off | tmp | KEEP |
| test_scraper_reuse.py | scrape.scraper (screenshot reuse) | yes | off | tmp | KEEP |
| test_scraper_two_phase.py | scrape.scraper (two-phase + manifest.json) | yes | off | tmp | KEEP |
| test_seed_admin.py | web (admin seeding) | yes | off | – | KEEP |
| test_sheet_name.py | pipeline.pdf_analyzer (sheet naming/noise) | yes | off | – | KEEP |
| test_sheet_pass_matrix.py | pipeline.sheet_pass_matrix (via claude_analyzer routing) | yes | off | – | KEEP (stubs config w/ bare MagicMock — see (c)) |
| test_sheet_preview.py | scrape.sheet_preview | yes | off | tmp | KEEP |
| test_stackct_store.py | stores.stackct_store | yes | off | tmp | KEEP |
| test_symbol_binding.py | vision.fusion, aggregator, calculator, reporter (symbol binding) | yes | off | – | KEEP |
| test_symbol_identification.py | vision.fusion, pipeline.takeoff_pipeline | yes | off, skipif-local | fx (crow PDF) | KEEP |
| test_symbols.py | deterministic.symbols | yes | off, skipif-local | fx (synthetic + crow PDF) | KEEP |
| test_tables.py | deterministic.tables, schedule_extraction | yes | off, skipif-local | fx (synthetic + crow/bobs PDFs) | KEEP |
| test_takeoff_generalization.py | pipeline.aggregator, calculator (per sheet_type) | yes | gen (offline) | fx (generalization/*.json) | KEEP |
| test_takeoff_measurements.py | bobbytailor.deterministic (measurements API) | yes | off | – | KEEP |
| test_takeoff_pipeline.py | pipeline.takeoff_pipeline | yes | off | – | KEEP (bare `_CONFIG_MOCK` — see (c)) |
| test_verify_retry.py | vision.verify_retry, ensemble, pipeline.takeoff_pipeline | yes | off | – | KEEP |
| test_vision_schemas.py | vision.schemas, claude_analyzer, overlay, pipeline.sheet_pass_matrix | yes | off | – | KEEP |
| test_wall_height_resolver.py | pipeline.takeoff_pipeline (wall heights) | yes | off, skipif-local | fx (crow PDF) | KEEP |
| test_walls.py | deterministic.walls, dimensions | yes | off, skipif-local | fx (synthetic + crow PDF) | KEEP |

Support files (not tests): `conftest.py` (KEEP — session env pinning + stub neutralization, see (f)), `golden_validator.py` (KEEP — used by test_golden_takeoff.py and 4 scripts), `replay_analyzer.py` (KEEP — the offline vision seam, see (e)).

Marker census (grep `pytest.mark` across tests): 66× `generalization`, 34× `parametrize`, 22× `skipif`, **2× `golden`** (both in test_golden_takeoff.py). `pytest.ini` registers only `golden` and `generalization`.

## (b) fixtures/ inventory (8.9 MB, 30 git-tracked files)

| Fixture | Size | Referenced by | Status |
|---|---|---|---|
| bobs_discount/bobs_discount_plans.pdf | 4.4 M | 5 test files; scripts/diagnose_fixture.py, setup_golden_fixtures.sh, golden_convergence.py | KEEP — live |
| bobs_discount/bobs_discount_takeoff.pdf | 2.2 M | **0 code refs** (only .planning/phases/20-…/20-14-SUMMARY.md) | KEEP — deliberate ground-truth companion for `vision_only_benchmark.py --takeoff-pdf`; take-offs are ground-truth-only per mission |
| crow_cass/crow_cass_plans.pdf | 1.1 M | 13 test files; 4 scripts | KEEP — most-used fixture in the suite |
| crow_cass/crow_cass_takeoff.pdf | 1.1 M | **0 code refs** (only .planning 20-13/20-14) | KEEP — same rationale as Bob's takeoff |
| synthetic/ (gen_synthetic.py + 3 PDFs + truth.json) | ~48 K | 12 test files (grep "synthetic": dimensions, walls, rooms, symbols, tables, printed_scale, component_library, footprint, golden, parity, reliability, generalization) | KEEP — the offline geometry ground truth |
| generalization/*.json (7 inputs + 3 expected/) | ~40 K | test_takeoff_generalization.py (each input referenced; expected/ loaded with skip-if-absent at :81,:181,:288) | KEEP |
| crow_cass/scale_truth.json, bobs_discount/scale_truth.json | 8 K | test_pipeline_deterministic.py, test_scale_solver.py | KEEP |
| crow_cass/crow_cass_golden.csv | 4 K | test_golden_takeoff.py, golden_validator.py docstring; scripts diagnose/vision_only/score_report_dir/golden_convergence | KEEP |
| bobs_discount/bobs_discount_golden.csv | 4 K | test_golden_takeoff.py; scripts diagnose/golden_convergence | KEEP |
| moxy/moxy_golden.csv | 4 K | scripts/diagnose_fixture.py only | KEEP (golden = ground truth) |
| chelsea/chelsea_golden.csv | 4 K | scripts/diagnose_fixture.py only | KEEP (golden = ground truth) |
| **sheet_coverage.json** | 4 K | **No code reads it.** Phase 20-07 scope-documentation artifact (.planning/phases/20-…/20-07-PLAN.md:42) | UNREFERENCED — doc, not fixture; candidate to move to docs/ or delete |
| **moxy/moxy_manifest.json** | 4 K | **0 refs anywhere** (code, scripts, docs) | UNREFERENCED dead weight |
| **crow_cass/crow_cass_manifest.json** | 4 K | Only reports/vision_only/RESULTS.md:103 (a historical `--manifest` command example) | Manifest-era legacy; plans-only mission deprecates manifest-propped runs |
| **bobs_discount/bobs_discount_manifest.json** | 4 K | **0 refs anywhere** | UNREFERENCED dead weight |
| replay/.gitkeep | 0 B | Canonical ReplayAnalyzer fixture dir (replay_analyzer.py:5,:21) | KEEP — currently empty, awaiting first REPLAY_RECORD=1 session |

Net dead weight: ~16 KB of JSON (negligible). The 3.3 MB of take-off PDFs are unreferenced-by-code but mission-protected ground truth — do not delete without an explicit decision.

## (c) Root-level `MagicMock/` — cause found

**Contents:** ONLY empty directories, 0 bytes, 0 files. `MagicMock/mock.OUTPUT_DIR/4432562352/` (Jul 15 00:21) and `MagicMock/mock.SCREENSHOTS_DIR/{4485586800,4420694704,4428258128,4427539648}/{Test|Test_Project}_20260714_*/` (Jul 14 17:31–22:18). Untracked, NOT git-ignored — invisible in `git status` only because git never shows empty directories.

**Mechanism (verified locally):** `os.fspath(MagicMock().SCREENSHOTS_DIR)` returns the literal string `'MagicMock/mock.SCREENSHOTS_DIR/<id>'` (mock's `__fspath__` default). So any production code doing `Path(CONFIG_ATTR) / ... .mkdir(parents=True)` with a mocked config creates this tree relative to cwd (repo root).

**Offending tests:** the module-level stub `sys.modules.setdefault("bobbytailor.config", MagicMock())` in:
- `tests/test_pipeline_parity.py:57-63` (`_CONFIG = MagicMock()`; sets `SCREENSHOTS_DIR="/tmp/test_screens"` **today**, but `OUTPUT_DIR` is still an unset child mock) — its calls `pdf_analyzer.run_pdf_analysis("/fake.pdf", "Test Project"/"Test")` at :217/:243/:273 match the `Test_*`/`Test_Project_*` dir names exactly.
- `tests/test_takeoff_pipeline.py:27-32` (`_CONFIG_MOCK = MagicMock()` — completely bare, every attr is a child mock).
- `tests/test_sheet_pass_matrix.py:27-40` (same bare pattern).

**Create sites in src:** `pipeline/pdf_analyzer.py:280-281` (`img_dir = Path(SCREENSHOTS_DIR)/f"{safe}_{ts}"; img_dir.mkdir(parents=True)`) produced the SCREENSHOTS leg; `pipeline/reporter.py:54-55` (`Path(OUTPUT_DIR).mkdir`) produced the OUTPUT leg.

**Status:** the artifact dates (Jul 14–15) predate the Jul 17 `conftest.py` fix that pre-imports the real modules (making the stubs no-ops in full-suite runs). Residual risk remains for **solo-file runs** (`pytest tests/test_takeoff_pipeline.py` alone), where the bare `_CONFIG_MOCK` still wins. Durable fix: set explicit tmp-path strings on every dir attribute of the stub configs (as parity already does for `SCREENSHOTS_DIR`), or add a conftest autouse guard. The `MagicMock/` directory itself is safe to delete.

## (d) Tests touching untracked local state / machine paths

- **No absolute machine paths** — grep for `/Users/`, `/private/tmp`, `Documents/Projects` across `tests/*.py` returns nothing.
- **No test reads repo `output/` run dirs.** All `output`-shaped paths are `tmp_path`-isolated (`test_blueprint_parity.py:184`, `test_learning_capture.py:46`, `test_learning_store.py:118`) with `config.OUTPUT_DIR` monkeypatched (e.g. `test_blueprint_parity.py:161-165`).
- **`uploads/` (git-ignored) readers — all skip-guarded, suite stays green on clean checkout, but coverage silently shrinks without the local PDFs:**
  - `test_component_library.py:25-26` (Crow full plans; skipif :257,:275)
  - `test_scale_extraction.py:18-20` (Moxy; skipif)
  - `test_schedule_extraction.py:19-20` (Moxy; skipif :58)
  - `test_naming_conventions.py:661-674` (Chelsea + Moxy; in-test `pytest.skip` :682)
- **`test_blueprint_parity.py` WRITES into the real `uploads/` directory** through the upload/run endpoints (save path asserted `dirname == "uploads"` :242), with `finally`-block cleanup at :247, :304-306, :336-338. Depends on cwd being repo root; one test also does `os.chdir(tmp_path)` (:189-195). Self-cleaning but a genuine side effect on a protected directory — worth isolating during restructure (point `uploads` dir at tmp in the app factory).
- **cwd dependence:** the MagicMock artifact (c) and the uploads writes both assume `pytest` runs from repo root.

## (e) Replay/record system — what must be preserved

- **Canonical fixture location:** `tests/fixtures/replay/{sha256}.json` (`replay_analyzer.py:5`). Key = SHA256 of `(model, pass_type, prompt text, image_count)` (:63-74). **The directory is currently EMPTY (only `.gitkeep`) — no recorded API responses exist in the repo yet.**
- **It reads NO `output/` directories.** `ReplayAnalyzer` resolves exclusively against its constructor `fixture_dir` (:180, :223-233). Conclusion for cleanup planning: **no `output/` run dir needs to be preserved for the replay layer.** (Run dirs matter to other consumers — scripts/web — not to replay.)
- **Record mode** requires `REPLAY_RECORD=1` env (or `record=True`) and lazily imports the real `analyze_drawing` (:185) — paid API; never triggered in CI or by default (`REPLAY_RECORD` appears nowhere in scripts/CI).
- **Consumers:** only `tests/test_fusion.py:584-653` (harness self-tests with `tmp_path` fixture dirs and fake analyzers, incl. the `TakeoffPipeline(analyzer=...)` injection seam test at :649). No `src/` or `scripts/` code imports it.
- Fixture-poisoning threat model is documented in the module docstring (:14-17): fixtures are repo-committed test data; CI never records.

## (f) conftest.py env pinning — fragility notes

`tests/conftest.py` pins, all via `os.environ.setdefault` (lines cited):

| Pin | Line | Purpose | Fragility |
|---|---|---|---|
| `TAKEOFF_ACCURACY_MODE=standard` | 30 | keep unit tests on 3-pass floor_plan | shell-exported var overrides it |
| `LEARNING_DB_PATH=<mkdtemp>/learning.db` | 38-41 | isolate session from real `output/learning.db` (read once at `learning.store` import) | **setdefault: a developer-exported `LEARNING_DB_PATH` would make endpoint tests write to that real DB**; also leaks one tmpdir per session (harmless) |
| `CLAUDE_MODEL=claude-haiku-4-5`, `CLAUDE_MODEL_SCHEDULES=claude-sonnet-4-5` | 48-49 | deterministic model routing | overridden by exported env / CI secrets → routing assertions break |
| `CLAUDE_MODEL_SEMANTIC/DENSE/ESCALATION/CLASSIFY` (throwaway distinct slugs, incl. fictional `claude-sonnet-5`, `claude-opus-4-8`, `claude-fable-5`) | 56-59 | tell every MODEL_ROUTING v2 route apart in assertions | same override risk; the values are intentionally fake — any code path that ever sends them to the API would 404 (fine for offline suite, a trap if a test's mock seam breaks) |
| `ENSEMBLE_N=3`, `API_BUDGET_PER_RUN_USD=10.0` | 64-65 | deterministic fan-out counts / budget assertions | same |
| Pre-import of 9 real modules | 92-103 | neutralize `sys.modules.setdefault(…, MagicMock())` stubs in parity/pipeline/pass-matrix test files under full-suite collection | **maintenance trap: any NEW module stubbed by a test file must be manually added to this list** or full-suite runs can be poisoned by the stub (the exact bug class documented in the docstring, and the cause of the MagicMock/ artifact). `_ensure_real` swallows all import errors silently. |

Additional structural fragility (not conftest): `pytest.ini` registers the `golden` marker but does **not** exclude it via `addopts`. With the golden PDFs committed in `tests/fixtures/`, `pytest tests/` runs the two paid E2E tests. Recommend `addopts = -m "not golden"` in `pytest.ini` (developers then opt IN with `-m golden`) during the restructure.

## Verdict summary

- KEEP: 64 test files + conftest.py + golden_validator.py + replay_analyzer.py + all PDFs/goldens/synthetic/generalization fixtures.
- CONSOLIDATE (optional, low value): `test_extraction_prompt.py` (633 B) → `test_vision_schemas.py`; `test_scraper_errors.py` (676 B) → `test_scraper_pipeline.py`.
- DELETE: nothing inside `tests/`. Outside: root `MagicMock/` (empty-dir artifact).
- UNSURE (needs a decision, ~16 KB total): `tests/fixtures/sheet_coverage.json` (doc masquerading as fixture), `tests/fixtures/moxy/moxy_manifest.json`, `tests/fixtures/bobs_discount/bobs_discount_manifest.json`, `tests/fixtures/crow_cass/crow_cass_manifest.json` (manifest-era legacy vs plans-only mission; crow's is cited in a historical RESULTS.md command).

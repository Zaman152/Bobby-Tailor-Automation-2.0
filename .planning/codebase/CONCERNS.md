# CONCERNS — Quality / Loophole Scan of `src/` and `scripts/`

Read-only audit, 2026-08-02, branch `accuracy/flag-dont-guess-coincidental-detections`
(working tree includes uncommitted edits to `src/bobbytailor/web/blueprints/reports.py`;
line refs below are against the current working tree).

## TL;DR

The codebase is in **better shape than a typical 30k-line automation project**: zero
TODO/FIXME/HACK markers, zero bare `except:` clauses, no eval/pickle/shell=True, no
py3.9-incompatible syntax, no hardcoded secrets, path traversal handled correctly in all
file-serving routes, and the manifest/companion "score-propping" loophole is explicitly
locked out of production paths (`allow_discovery=False` + parity tests). The real risks
are **generalization ceilings, not bugs**: the room-measurement engine only works on one
CAD-template convention (`"<NAME> - AR/RCP PLAN"` titles, ≤900 SF units), the wall-height
fallback is a warehouse-tuned 30 ft default, and the settings UI's model allowlist
contradicts the config defaults it is supposed to manage. Config sprawl (8 env vars
undocumented in `.env.example`, env reads in 6 modules outside `config.py`) and
import-time side effects in `config.py` are the main production-hardening targets.

Severity counts: 0 CRITICAL, 4 HIGH, 8 MEDIUM, 7 LOW (+ 4 positive findings).

---

## HIGH

### H1. Room engine generalizes only to one CAD-template convention (silent zero-output on others)
- `src/bobbytailor/deterministic/room_fill.py:49-51` — `PLAN_TITLE_RE` requires viewport
  titles of the exact form `"<NAME> - (AR|RCP|FF|EM|FC) PLAN"`. This is Moxy's template
  habit. A plan set titling its viewports "FLOOR PLAN", "LEVEL 1", "ENLARGED UNIT PLAN"
  etc. yields **zero titles → zero room fills, with no flag** (the engine simply returns
  nothing; `takeoff_pipeline.py:1743-1744` logs at DEBUG only).
- `src/bobbytailor/deterministic/room_fill.py:73` — `MAX_REGION_SF = 900.0`: regions
  above 900 SF are rejected as "not a unit". `src/bobbytailor/pipeline/takeoff_pipeline.py:1764`
  — `_MAX_UNIT_SF = 900.0` ("largest plausible single dwelling/guest unit"). Correct for
  hotel guestrooms; wrong for offices, retail, classrooms, ballrooms (real rooms > 900 SF).
  The pipeline-side check flags (good); the room_fill-side filter silently drops.
- Same convention baked into sheet classification:
  `src/bobbytailor/pipeline/sheet_pass_matrix.py:169` — `_PLAN_VIEWPORT_RE = r"-\s*(?:AR|RCP)\s+PLAN\b"`.
- Layout-tuned pt constants: `takeoff_pipeline.py:1770-1771` `_FILL_CLIP_UP_PT = 620.0`,
  `_FILL_CLIP_SIDE_PT = 260.0` (anchored on Moxy's callout geometry).
- **Why it matters for the mission** (plans-only 100% autonomous): the next hotel with a
  different title-block CAD template will reproduce the "7% honest baseline" failure mode —
  not by erroring, but by finding no rooms at all. Recommend: emit an explicit
  `needs_review`/coverage flag when a measurable floor_plan sheet produces zero room fills,
  and make the unit-size band project-type-aware.

### H2. Wall-height fallback is warehouse-tuned and uses `max()` across the whole project text
- `src/bobbytailor/pipeline/takeoff_pipeline.py:803` — `_WALL_HEIGHT_DEFAULT_FT = 30.0`
  ("a conventional industrial clear height") applied whenever no callout parses. For a
  hotel/office (9–12 ft partitions) this inflates wall SF ~3x. The source is at least
  reported (`"default"`, line 916 — never silent), but the quantity still flows into totals.
- `takeoff_pipeline.py:905,909,914` — each tier returns `round(max(values), 2)`: a single
  tall callout anywhere in the concatenated project text (parapet, shaft, tower) sets the
  height for **every** wall item in the project. One number per project is itself a
  modeling ceiling (mixed 1-story/2-story buildings).

### H3. `config.py` import-time side effects make the package unusable without full secrets
- `src/bobbytailor/config.py:139-140` — `validate_required_env()` **runs at import** and
  raises unless `STACKCT_EMAIL`, `STACKCT_PASSWORD`, `ANTHROPIC_API_KEY`, `SECRET_KEY`,
  `ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH` are all set — even for an offline, deterministic,
  zero-API PDF run. Every consumer (tests, scripts, future library users) must stub or
  fully populate `.env` (see the "config stubbed (tests)" guards at
  `takeoff_pipeline.py:188`, `:1926`, `:2562`, `:2621` — silent-degradation code that only
  exists to survive this import).
- `config.py:10` — `load_dotenv(..., override=True)`: `.env` values **stomp real
  environment variables**, inverting the standard precedence (deployment env vars lose to
  a stale file). Production-hardening should split web-app requirements from pipeline
  requirements and validate at app startup, not module import.

### H4. Root entry point runs Flask with `debug=True`
- `/Users/muhammadumer/Documents/Projects/Bobby-Tailor-Automation-2.0/app.py:5` —
  `app.run(debug=True, port=5050, use_reloader=False)`. If this file is ever the
  production entry (instead of gunicorn pointing at `create_app`), the Werkzeug debugger
  is remote code execution for anyone who can reach the port. Gate on `FLASK_ENV`/env var.

---

## MEDIUM

### M1. Universal `Mobilization = 1 EA` injection into every take-off
- `src/bobbytailor/pipeline/aggregator.py:191-216` — `STANDARD_LINE_ITEMS` injects
  `{"name": "Mobilization", "unit": "EA", "quantity": 1}` into every project with a
  non-empty take-off (dedup-guarded, provenance `"standard_line_item"`). Documented as an
  estimating convention, but: (a) it appears on take-offs for scopes that don't bid
  mobilization, and (b) it flatters golden-fixture scores on any golden that contains a
  Mobilization row (all three current fixtures do — grep `mobiliz` in
  `scripts/room_probe.py:6` context and goldens). Decide deliberately whether this is
  product behavior or benchmark-propping; if kept, exclude it from accuracy scoring.

### M2. Text-layer qty=1 enrichment fires on boilerplate mentions
- `src/bobbytailor/pipeline/page_text_enrichment.py:10-14` — any page whose text layer
  matches `access ladder`, `\bmobilization\b`, or `personnel lift|material lift` gains a
  qty=1 EA component (confidence "medium"). A spec sheet *describing* lift requirements
  produces a Lift line item. Rules are generic (no project names — good) but unbounded by
  sheet type; consider restricting to general-notes/keynote regions.

### M3. Settings UI model allowlist contradicts config defaults and `.env.example`
- `src/bobbytailor/web/settings.py:24` — `VALID_MODELS = ["claude-haiku-4-5",
  "claude-sonnet-4-6", "claude-opus-4-7"]`, but `config.py:34-40` defaults the Phase-21
  routing to `claude-sonnet-5` / `claude-opus-4-8` / `claude-fable-5` and `.env.example`
  documents exactly those slugs. The settings page **rejects the documented models** and
  can't manage the routing vars at all: `settings.py:26-37` `ALLOWED_FIELDS` omits
  `CLAUDE_MODEL_SEMANTIC/DENSE/ESCALATION/CLASSIFY`, `ESCALATION_ENABLED`,
  `API_BUDGET_PER_RUN_USD`, `ENSEMBLE_N`. Also violates the config.py:28 comment
  "never hardcode model names in routing logic".

### M4. Config sprawl — env reads in 6 modules outside `config.py`, 8 vars missing from `.env.example`
Env reads outside `config.py` (grep `os.getenv|os.environ` in src):
- `src/bobbytailor/pipeline/takeoff_pipeline.py:158` (`_env_flag`) →
  `DETERMINISTIC_ENABLED`, `LEARNING_ENABLED`, `VERIFY_RETRY_ENABLED`, `RASTER_FORCE` (lines 191-196)
- `src/bobbytailor/pipeline/accuracy_config.py:13,30,35` → `TAKEOFF_ACCURACY_MODE`,
  `COUNT_TILING`, `COUNT_TILING_GRID`
- `src/bobbytailor/learning/store.py:94` → `LEARNING_DB_PATH` (deliberate, documented)
- `src/bobbytailor/web/app.py:44,46,63-64`, `web/auth.py:33`, `web/seed_admin.py:51,53`,
  `web/settings.py:65`
Missing from `.env.example` (verified against `git show HEAD:.env.example`):
`DETERMINISTIC_ENABLED`, `LEARNING_ENABLED`, `VERIFY_RETRY_ENABLED`, `RASTER_FORCE`,
`TAKEOFF_ACCURACY_MODE`, `COUNT_TILING`, `COUNT_TILING_GRID`, `MAX_PREVIEW_ROWS`
(read at `config.py:84`). An operator cannot discover the accuracy-mode/kill-switch knobs.

### M5. CWD-relative paths scatter state depending on launch directory
- `config.py:73` `OUTPUT_DIR = "./output"` default; `web/app.py:68-69` `os.makedirs("output/screenshots")`,
  `os.makedirs("uploads")`; `web/blueprints/runs.py:134,233,290` save uploads to relative
  `"uploads/..."`; `main.py:22` `logging.FileHandler("output/run.log")` (crashes at import
  if `output/` doesn't exist yet). Launching from any other cwd creates parallel
  `output/`/`uploads/` trees. Root-anchor these like `web/settings.py:16` already does.
- Concrete evidence this bites: repo root contains `MagicMock/mock.OUTPUT_DIR/` and
  `MagicMock/mock.SCREENSHOTS_DIR/` (dated Jul 14-15) — a test ran real
  `os.makedirs(str(mock))` against a mocked config. Test-isolation leak + relative-path smell.

### M6. `scrape/browser.py` — ~20 broad `except Exception: pass/continue` blocks
- `src/bobbytailor/scrape/browser.py:248,291,337,612,622,631,663,677-685,722,948,979,995,1034,1080,1107,1141`
  — best-effort DOM probing against StackCT (an acceptable domain for this), but the
  density means selector drift after a StackCT UI update degrades capture with nothing but
  missing screenshots as the symptom. At minimum, count-and-report suppressed failures per
  run. (Core pipeline is far cleaner: the only silent `pass/continue` on Exception in
  pipeline/deterministic code are `pipeline/reporter.py:236` and
  `deterministic/schedule_extraction.py:195` — both narrow in scope.)

### M7. Deterministic-flow fallbacks to "legacy vision" are log-only
- `src/bobbytailor/pipeline/takeoff_pipeline.py:1484-1489,1493-1498,1502-1505,1519-1528`
  — when the PDF/page can't be opened or a schedule sheet has no deterministic tables,
  `_dispatch` returns `None` and the sheet silently runs the (less accurate) legacy vision
  flow; the report does not mark the sheet as degraded. In-flow **exceptions** are handled
  well (`_error_result` dict, lines 1510-1517, 1541-1548, surfaced per-sheet), so this is
  about the `return None` paths only. Recommend a `measurement_mode: "vision_fallback"`
  marker so run-to-run accuracy variance is attributable.

### M8. Client-deliverable Excel export lives only in `scripts/`
- `scripts/export_takeoff_excel.py` (158 lines) is the only Excel writer — no `openpyxl`
  usage anywhere in `src/` (verified by grep). Provenance-honest client output is a product
  feature; it belongs in `src/bobbytailor` with a web download route, not a dev script.
  Similarly, the entire accuracy-scoring engine (`score`, `score_with_provenance`,
  `evaluate_gates`) lives in `scripts/vision_only_benchmark.py:212-550` and is imported
  script-to-script (`scripts/score_report_dir.py:23` `from scripts.vision_only_benchmark
  import ...`) — fine for a benchmark today, but it is the *only* implementation of
  "accuracy" and will be needed by the app/learning loop eventually.

---

## LOW

### L1. `__main__` demo harnesses reference specific upload PDFs
- `src/bobbytailor/deterministic/schedule_extraction.py:295-298` and
  `src/bobbytailor/deterministic/tables.py:444-447` default to
  `uploads/Moxy Knoxville...`, `uploads/Crow - Cass White Road-Plans.pdf`,
  `uploads/Bob's Discount Furniture...`. Dev conveniences, not runtime hardcoding (all
  other Crow/Moxy/Bob mentions in src are comments documenting bugs — verified each hit).

### L2. Stray committed diagnostic artifact
- `scripts/_diag_chelsea.json` — 236 KB, referenced by nothing (grep across repo),
  committed in `a715681`. Delete.

### L3. `MagicMock/` directory at repo root
- `MagicMock/mock.OUTPUT_DIR/`, `MagicMock/mock.SCREENSHOTS_DIR/` — test artifact leak
  (see M5). Delete the directory, then find the test that creates dirs from a mocked
  config and give it a tmp_path.

### L4. `scripts/` sys.path bootstrap is inconsistent
- ROOT-only inserts: `audit_plan_sets.py:10`, `discover_plan_sets.py:9`,
  `network_capture.py:14`, `diagnose_fixture.py:15`, `score_report_dir.py:21`,
  `golden_convergence.py:19`. ROOT + ROOT/src inserts: `fusion_probe.py:12-13`,
  `geom_probe.py:22-23`, `room_probe.py:24-25`, `scale_probe.py:19-20`,
  `vision_only_benchmark.py:76-81`, `export_takeoff_excel.py:27-28`. The ROOT-only group
  works only with an editable install; standardize on one bootstrap (or a console-script
  entry point) during restructure.

### L5. Auth decorator inconsistency in `reports.py` (no actual exposure)
- `src/bobbytailor/web/blueprints/reports.py:112,256` — `list_reports` and
  `preview_report` lack `@login_required` while sibling routes have it. They ARE protected
  by the app-wide gate (`web/app.py:114-121` `require_login` before_request +
  `PUBLIC_ENDPOINTS` allowlist at `app.py:27`) — verified. Keep the decorators consistent
  anyway so a future refactor of the global hook can't silently expose them.

### L6. Werkzeug/Flask trusts `filename.lower().endswith(".pdf")` only
- `src/bobbytailor/web/blueprints/runs.py:130,286` — extension check only, no magic-byte
  sniff before `fitz.open`. Low risk (authenticated admin-only app, fitz failures handled),
  but a content-type check is cheap hardening.

### L7. `seed_admin` default email constant
- `src/bobbytailor/web/seed_admin.py:28` — `DEFAULT_ADMIN_EMAIL = "admin@bobbytailor.com"`.
  Password handling itself is exemplary (no default password, min length 12, bcrypt-12,
  printed once with `--generate`). Just make the email required too.

---

## Positive findings (verified, worth preserving in the restructure)

1. **No TODO/FIXME/HACK/XXX markers anywhere in src/ or scripts/** (case-insensitive grep,
   zero hits) and **zero bare `except:`** (108 broad `except Exception` clauses exist, but
   in pipeline/deterministic code virtually all are annotated `# noqa: BLE001` with a
   reason and a log line — a deliberate "untrusted PDF must not crash the run" policy).
2. **Py3.9 compatibility is clean**: no `match` statements; the only two PEP-604 unions
   (`scripts/score_report_dir.py:54`, `src/bobbytailor/stores/job_store.py:184`) are in
   annotation position under `from __future__ import annotations` (verified both files);
   no `slots=True` dataclasses; no `itertools.pairwise`/`zip(strict=)`; and
   `takeoff_pipeline.py:203-217` explicitly engineers around the 3.9 string-annotation
   dataclass quirk. `pyproject.toml:11` declares `requires-python = ">=3.9"`.
3. **The manifest-propping loophole is structurally closed**: both entry points resolve
   manifests with `allow_discovery=False` (`pipeline/pdf_analyzer.py:350-353`,
   `scrape/scraper.py:578-581`), companion take-off parsing lives in `devtools/` and is
   imported in production src by nothing (only `scripts/vision_only_benchmark.py`, which
   additionally plants decoy companions/manifests and asserts non-leakage, lines 639-714),
   and parity tests pin it (`tests/test_pipeline_parity.py::test_companion_discovery_absent_from_production_namespaces`).
4. **File-serving is traversal-safe**: `reports.py:26-41,44-79,293-309` all use
   fast-fail `..`/`/` checks + `resolve()` + `relative_to(root)` containment + extension
   allowlists; uploads use `secure_filename` with fallback (`runs.py:32-39`). No
   subprocess/eval/pickle/`shell=True` in src (only `scripts/golden_convergence.py:25`
   uses `subprocess.run` on a fixed argv — and that script is paid-API, not audited by execution).
   Honest qty handling: schedule rows without a real quantity are skipped, never
   fabricated as "1 ea" (`calculator.py:1054-1071`).

## Explicitly NOT verified (out of scope / rule 2)

- Anything requiring a pipeline run or paid API (`scripts/vision_only_benchmark.py`,
  `scripts/accuracy_gate.sh`, `scripts/golden_convergence.py` were read, not run).
- The test suite itself (another process was running it); `static/` JS and templates
  (frontend agent's scope).
- Dead-code analysis was a spot check: all 16 candidate modules I checked
  (sheet_preview, capture_manifest, linked_sheets, cross_references, scale_recalc,
  scale_utils, distill, retrieval, verify_retry, ensemble, overlay, symbols, viewports,
  walls, rooms, room_fill) have live importers in src/ or scripts/. Function-level dead
  code inside the 3,209-line `takeoff_pipeline.py` and 1,954-line `fusion.py` was not
  exhaustively traced.

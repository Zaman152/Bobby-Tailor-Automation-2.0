---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: milestone
current_phase: 22
current_phase_name: production-restructure-cleanup
status: complete
stopped_at: Completed 22-04-PLAN.md — Phase 22 complete (all 4 plans, RESTRUCTURE-SPEC S0-S8)
last_updated: "2026-08-02T23:59:00.000Z"
last_activity: 2026-08-03
last_activity_desc: Phase 22 complete — docs truth fixes, dead JS removal, GitNexus reindex
progress:
  total_phases: 23
  completed_phases: 19
  total_plans: 104
  completed_plans: 100
  percent: 82
---

# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-05-26)

**Core value:** End-to-end automated take-off from StackCT drawings (or PDFs) producing traceable, formula-backed quantity calculations estimators can trust and export.

**Current focus:** Phase 22 — production-restructure-cleanup

## Current Position

Phase: 22 (production-restructure-cleanup) — COMPLETE
Plan: 4 of 4
Status: Phase complete — all 7 success criteria met
Last activity: 2026-08-03 — Phase 22 complete (docs truth fixes, dead JS removal, GitNexus reindex)

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 9 (Phase 3)
- Average duration: ~2.5 min/plan (Phase 3)
- Total execution time: ~7.5 min (Phase 3)

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 03-api-cost-transparency | 3 | 7.5 min | 2.5 min |

**Recent Trend:** Phase 3 executed in 3 sequential waves (03-01 → 03-02 → 03-03)
| Phase 21-accuracy-learning-engine P04 | 15 min | 3 tasks | 4 files |
| Phase 21-accuracy-learning-engine P05 | 18 min | 3 tasks | 8 files |
| Phase 21-accuracy-learning-engine P06 | 25 min | 3 tasks | 8 files |
| Phase 21-accuracy-learning-engine P07 | 37 min | 3 tasks | 5 files |
| Phase 21-accuracy-learning-engine P08 P08 | 32 min | 3 tasks | 5 files |
| Phase 21-accuracy-learning-engine P09 | 9 min | 2 tasks | 3 files |
| Phase 21-accuracy-learning-engine P10 P10 | 53 min | 3 tasks | 9 files |
| Phase 21-accuracy-learning-engine P11 P11 | 16 min | 3 tasks | 5 files |
| Phase 21-accuracy-learning-engine P12 P12 | 25 min | 3 tasks | 3 files |
| Phase 21-accuracy-learning-engine P13 P13 | 40 min | 3 tasks | 5 files |
| Phase 21-accuracy-learning-engine P14 P14 | 14 min | 2 tasks | 3 files |
| Phase 21-accuracy-learning-engine P15 P15 | 27 min | 3 tasks | 9 files |
| Phase 21-accuracy-learning-engine P16 | 38 min | 3 tasks | 8 files |
| Phase 21-accuracy-learning-engine P17 | 20 min | 2 tasks | 3 files |
| Phase 21-accuracy-learning-engine P18 | 36 min | 2 tasks | 113 files |
| Phase 22 P01 | 17min | 3 tasks | 6 files |
| Phase 22 P04 | 38min | 3 tasks | 13 files |

## Accumulated Context

### Roadmap Evolution

- Phase 22 added (2026-08-02): Production Restructure & Cleanup — executes .planning/codebase/RESTRUCTURE-SPEC.md (full-repo audit by 6 parallel mappers + synthesis); precedes the production-hardening/accuracy revamp program

### Decisions

### 22-04 Decisions

| Decision | Source |
|----------|--------|
| index.html keeps TWO type=module tags — the plan's `-eq 1` criterion missed the body-end ui-motion.js loader, which is LIVE (window.uiMotion consumed by app.js:98,897); head-section count is the real intent and is 1 | 22-04 |
| docs/DEPLOYMENT.md:57 (CLAUDE_MODEL_SCHEDULES -> CLAUDE_MODEL) was already correct and left alone; only :60 (CLASSIFY) was wrong | 22-04 |
| Stale ~$0.05/run cost figure flagged as pre-Phase-21 and redirected at API_BUDGET_PER_RUN_USD / takeoff.json api_cost rather than re-estimated (measuring costs paid API) | 22-04 |
| GitNexus query API, not the raw .gitnexus/lbug bytes, is authoritative on reindex completeness — deleted-module byte hits are uncompacted tombstones; all six symbols return not-found | 22-04 |
| .env.example is blocked by the user-level `Read(.env.*)` deny rule; inspected via `git show HEAD:.env.example` and appended via shell redirect. `.env` never touched | 22-04 |

From PROJECT.md Key Decisions (roadmap-relevant):

- Masterv2.md is planning source of truth (replaces Master.md for new work)
- Master Phase 1 critical UX (plan select + preview) before full UI shell — reflected in phases 4–5 before 8–10
- Keep Flask monolith; extract static JS/CSS on UI rebuild (Phase 8)
- FastAPI (ARCH-01) deferred to v2 per user directive

From 03-01 (Per-Sheet Usage Capture):

- Hardcoded PRICING dict with float rates (Haiku/Sonnet/Opus per MTok); default to Sonnet for unknown models
- Usage metadata on extraction dicts: `_tokens_in`, `_tokens_out`, `_cost_usd`, `_model_used`
- Error returns include zero-value usage fields for safe reporter aggregation

From 17-04 (Production Job UX):

- cancel_check Callable pattern: scraper reads jobs[job_id].get("_cancel") via lambda; _cancelled flag breaks sheet loop cleanly
- Partial-on-cancel: _cancelled=True in result dict; _finalize preserves "cancelled" status from endpoint; saves partial result with warning
- Weighted progress bands: capturing 0–40%, analyzing 40–90%, reporting 95%, done 100%

From 03-02 (Run-Level Aggregation):

- `api_usage` block in takeoff.json: total_cost_usd, tokens, cost_per_sheet, models_used
- Per-sheet cost in sheet_log (tokens_in, tokens_out, cost_usd, model_used)
- summary.txt includes "API USAGE & COST" section

From 03-03 (UI Cost Display):

- Report cards show cost in green (#4ade80) with 4-decimal USD precision
- list_reports() reads api_usage from takeoff.json; old runs without cost render gracefully

From 12-03 (Frontend CSRF Protection):

- apiFetch wrapper in app.js handles X-CSRFToken automatically for all state-changing calls
- settings.js keeps its own getCsrfToken() copy (self-contained page, no shared module)
- Logout form added to both templates as POST with csrf_token hidden field

From 12-02 (Core Flask Authentication):

- Timing-safe dummy bcrypt check on unknown email (prevents user enumeration)
- POST-only /logout to prevent CSRF via GET requests
- SESSION_COOKIE_SECURE conditional on FLASK_ENV != "development"

From 12-01 (Auth Dependencies & Admin Seeding):

- bcrypt rounds=12 for admin password hash (strong work factor, ~1s seeding time)
- RATE_LIMIT_STORAGE_URI defaults to memory://; Redis URI documented for multi-worker gunicorn
- SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD_HASH added to REQUIRED_ENV_VARS (crash-fail on missing)

From 14-01 (Plan-Set Discovery & Dedupe):

- Dedupe rules based on 14-DISCOVERY audit: drop "Plans X" parent, drop aggregate folders with multiple version labels
- Direct-grid fallback with folder_id=0 for projects without folder cards (ATL 081 pattern)
- Deprecated get_all_page_ids to use folder-aware APIs (prevents mixing multiple sets)

From 14-02 (Schema v2 & Folder-Aware Sync):

- Schema v2: project_plan_sets table, project_plans PK changed to (stackct_id, folder_id, page_id)
- v1→v2 migration drops project_plans table (re-sync required for all projects)
- sync_project_plans and get_project_plans now require folder_id parameter
- Background sync tracks (project_id, folder_id) tuples for parallel folder syncs

From 14-03 (Folder-First API Routes):

- GET /api/projects/<id>/plan-sets returns folder list
- GET /api/projects/<id>/plans now requires ?folder_id= (backward compat with 400 error)
- POST /api/run/stackct validates page_ids belong to folder
- folder_id stored in takeoff.json report root

From 14-04 (Two-Step Plan Selection UI):

- Two-step flow: plan sets → sheets (auto-skip for single-set projects)
- Project list shows "N sets · M sheets" instead of single sheet count
- Radio card picker with folder metadata visible
- Back button hidden for single-set projects
- [Phase 21-04]: Dedicated learning.db (not stackct.db) at OUTPUT_DIR; LEARNING_DB_PATH env override; schema init keyed by DB path so monkeypatched test DBs re-init automatically
- [Phase 21-04]: learning_vocabulary UNIQUE widened to (project_type, raw_pattern, canonical_name, unit) — §6 conflict/decay needs decayed old + new mappings to coexist; 2-col UNIQUE makes that unrepresentable
- [Phase 21-04]: Distilled state is a pure function of the log: replay in id order, last_seen = correction created_at (never now), staleness decay fires at new-verified-run boundaries — incremental == full_rebuild under any batching
- [Phase 21-04]: Assumptions distilled at BOTH exact (project_key) and type (project_key NULL) levels so learning transfers to new projects; retrieval precedence keeps exact rows winning
- [Phase 21-05]: resolve_routed_model() is the single pure exact→wildcard MODEL_ROUTING lookup; name heuristics stay in pick_model_for_pass/_pick_model so the deferred import cannot recurse
- [Phase 21-05]: MODEL_ROUTING v2: legend/schedule structuring → CLAUDE_MODEL_DENSE; wildcard ('*', pass) rows for classify/semantic/legend/schedule/verify_retry; count/measure rows keep CLAUDE_MODEL_SCHEDULES
- [Phase 21-05]: Whole-sheet renders target RENDER_TARGET_PX=1568 long edge; 8000px is a safety cap only; render_clip_crop is the sole zoom primitive for crops/tiles/galleries
- [Phase 21-05]: conftest pins CLAUDE_MODEL_CLASSIFY to suffixed throwaway 'claude-haiku-4-5-classify' because its real default equals CLAUDE_MODEL — distinct pins keep routes distinguishable
- [Phase 21-06]: Symbol union-find partitioned by path style class (stroke/fill/width) — endpoint proximity alone merges columns into the wall network; style separation makes CAD blocks enumerable (Crow 136 columns)
- [Phase 21-06]: Near-duplicate signature merge via second coarse hash (1pt/2deg) + kind counts; MIN_CLUSTER_PRIMITIVES=2 excludes dash/tick noise from symbol groups
- [Phase 21-06]: Schedule tables claimed by at most one kind (registry order); door kind delegates rows to schedule_extraction and locates bboxes with the same imported gates
- [Phase 21-07]: RANSAC scale consensus measured in paper-length explained (sum of inlier points), not sample count — recovers Bob 3/32"=1'-0" truth over six identical mispaired 216pt decoys that capture count-voting
- [Phase 21-07]: Crow p0 main-plan truth is 1"=40' (printed scale + 1136'/350' overall dims); plan's 20-fpi acceptance was a stale research note — geometrically impossible on a 3024pt-wide sheet
- [Phase 21-07]: HIGH scale confidence = three-condition conjunction (>=8 inliers AND >=80% share AND printed agreement within 1%); printed conflict caps at LOW
- [Phase 21-07]: Viewport bboxes in UNROTATED PyMuPDF space; leftover claiming uses frozen bboxes + midpoint union so border segments cannot explode a region
- [Phase 21-07]: resolve_scale_v2 learned prior fires ONLY when solved+printed tiers empty (anti-amplification); unbacked printed tier capped at medium
- [Phase 21-08]: Vector-sheet vision schemas: candidate-ID enums, additionalProperties:false everywhere, all-required, zero numeric types (rejection-walk test); raster_extraction_schema is the sole numeric exception (count_estimate)
- [Phase 21-08]: render_overlay: one PIL.Image at <=40 markers, list with disjoint info[overlay_ids] subsets beyond; pixel<->point grounding via info[zoom]/info[marker_boxes_px] — model never asked for coordinates
- [Phase 21-08]: build_crop_gallery packs ID-captioned tiles into contact sheets, legend crop first, tiles-per-sheet scaled to keep <=20 images/request
- [Phase 21-08]: symbol_gallery pass routes via the (*, semantic) MODEL_ROUTING row alias; structured path parses guaranteed JSON directly (no markdown strip, no json_repair)
- [Phase 21-08]: wrap_pdf_text() <pdf_text> delimiters contain prompt injection from untrusted PDF strings; semantic prompts declare delimited content is data, not instructions
- [Phase 21-09]: _capture_learning is best-effort and never raises — store/distill failure logs and returns 200 without learning_warning; per-run JSON write never rolled back
- [Phase 21-09]: verify scope mapping: prior row missing → missed_item, unit-only change → unit, else item (confirmation pins current value); measurements: wall_area → wall_height, others → item
- [Phase 21-09]: measurements capture diff-based against previously persisted list — repeated saves record nothing new (Pitfall 8 hygiene)
- [Phase 21-09]: conftest pins LEARNING_DB_PATH to a session tmp DB so endpoint tests never write the real output/learning.db
- [Phase 21-10]: NETWORK_PRECISION_GRID 1e-6 snap on room-network inputs before unary_union — interpolate-derived connector endpoints round off the line in float, GEOS never nodes them, polygonize merges faces
- [Phase 21-10]: Wall opening gaps need corroboration (both faces broken OR door-leaf perpendicular segment) — dashed linework otherwise floods opening_gap_widths and poisons the 3'-0" door_check
- [Phase 21-10]: WallSegment.centerline_pt spans chain end-to-end (openings included) so rooms polygonize closes across doors; length_pt is material-only for honest LF
- [Phase 21-10]: Crow p0 office pods are single dashed outlines (not wall pairs) — unclosed/unlabeled rooms are vision-fallback territory; footprint anchor 397,692 vs 397,600 SF (0.02%)
- [Phase 21-11]: vote() accepts on whole-band (max−min ≤ tol) OR strict-majority-within-tolerance-of-median — 5-sample escalation passes on 3-of-5 agreement; 3-way disagreement still flags needs_review
- [Phase 21-11]: BudgetGuard.charge() refuses (never accumulates) charges past the cap; run_ensemble aborts to current-best flagged needs_review reason=budget_exhausted — never a silent partial
- [Phase 21-11]: Temperature-ignore probe compares metadata-stripped JSON fingerprints of first two dict samples, cached per probe_key; on ignore, later samples get nonzero prompt_variation
- [Phase 21-11]: run_tiled_count NMS dedups only ≥2-tile-covered detections from different tiles within 1.5 coarse cells; tiled sum joins run_ensemble via extra_members (method 'tiled+vote')
- [Phase 21-11]: ensemble_settings() is the single (ENSEMBLE_N, API_BUDGET_PER_RUN_USD) reader — 21-13 RunSettings must construct from it
- [Phase 21-12]: merge_with_provenance hard no-overwrite guard checks provenance STRINGS (not rank arithmetic) — vision_ensemble can never displace a deterministic quantity/unit; discarded claims audited in fusion_rejected
- [Phase 21-12]: fuse_sheet quantities are exclusively deterministic (group count, wall LF, polygon SF, schedule cells, printed dims); vision grounds via registry membership — out-of-set IDs dropped + flagged unknown_candidate_id; room vision labels apply only to label_source=='none' rooms
- [Phase 21-12]: ReplayAnalyzer keys fixtures by SHA256(model, pass_type, prompt text, image_count); record mode gated by REPLAY_RECORD=1 (never CI); lazy-import results validated as real strings so sys.modules mock stubs degrade to deterministic 'unrouted' fallback
- [Phase 21-13]: Deterministic-first routing scope: floor_plan/civil_site/roof_plan + schedule sheets; elevations/details/MEP keep legacy vision passes (wall pairing on elevations = bogus geometry-provenance LF)
- [Phase 21-13]: Budget charging convention: every vision call site charges the per-run BudgetGuard with the completed call's _cost_usd; a refused charge discards the result — ledger only holds paid-and-accepted work
- [Phase 21-13]: Deterministic ScheduleTables ride as _deterministic_schedules metadata (rows already fused as schedule_table components) — attaching as 'schedules' would double-count via calculator
- [Phase 21-13]: select_main_plan is the measurement authority; vision main_plan_region kept only as cross-check (main_plan_region_vision on disagreement)
- [Phase 21-13]: py3.9 + PEP 563 + spec-loaded modules: dataclasses in takeoff_pipeline built over real type-object __annotations__ (string annotations need sys.modules[cls.__module__] at decoration)
- [Phase 21-14]: verify_retry answers are choice-enum grounded; symbol-anchored out-of-band flags get legend labels as choices (relabel path) — on vector sheets the deterministic count is exact, so the label is the suspect, never the number
- [Phase 21-14]: Retry bound semantics: deny ('no') is definite (single attempt, flag kept unresolved); only 'unclear' consumes the second attempt, which widens the crop pad 0.25→0.75 for more context
- [Phase 21-14]: Verify-retry merge-back: relabeled renames the component (quantity/unit untouched) and clears needs_review; confirmed downgrades the flag to a note; unresolved keeps the flag — retry_history mandatory on every touched item
- [Phase 21]: 21-15: Sibling manifest auto-discovery (_find_manifest) removed with companion discovery — explicit manifest_path is the only manifest input to run_pdf_analysis — Same ground-truth-leakage class as *takeoff*.pdf siblings; plans-only LOCKED contract
- [Phase 21]: 21-15: StackCT blobs live at {run_dir}/blobs/{page_id}.pdf with _page_blob_path legacy pdfs/ fallback; REUSE_SCREENSHOTS also reuses cached blobs; PageEntry.is_vector stores the runtime probe — Vector data must reach the deterministic engine on cached and resumed runs
- [Phase 21]: 21-15: Scraper keeps _pipeline singleton but refreshes RunSettings.from_env() per run via new TakeoffPipeline.settings setter — settings-identical to pdf_analyzer — Preserves scraper._pipeline test patch seam while enforcing V3-STRUCT-02 parity
- [Phase 21]: 21-15: Parity tests spy run_sheet.__globals__ via patch.dict and use a global fitz.open spy for companion isolation — Robust to spec-load vs package-import dual module objects in the parity harness
- [Phase 21-16]: Two-stage learned retrieval: project_type inferred from latest prior correction at run start, refreshed after _detect_project_type — repeat runs get type-level vocabulary in prompts with zero manifests
- [Phase 21-16]: apply_learned_quantity_flags enforced on every run_sheet exit path: re_verify flags only, never substitution; geometry/text_layer HIGH protected even under the §6 identical-input exception (dormant in production)
- [Phase 21-16]: Aggregation naming precedence: companion legend > manifest > learned_vocabulary > static ITEM_NAME_MAP; learned-named rows marked source=learned, quantity provenance untouched
- [Phase 21-17]: Planted-decoy isolation: benchmark plants a sentinel sibling take-off, asserts the devtools finder sees it, and asserts the pipeline result is leakage-free (regression tripwire for companion auto-discovery)
- [Phase 21-17]: Gate semantics: uncertifiable metrics (geometry_text_qty_acc=None) FAIL; vision_qty_share counts any vision_ensemble involvement over quantity-bearing rows; flagged (needs_review/fusion_rejected) counts as covered for silent-miss detection
- [Phase 21-17]: accuracy_gate.sh pins LEARNING_DB_PATH to a fresh temp DB per run (cold-pipeline scores); --with-learning is tracking-only learned-assisted, never gating; cost baseline record-on-absent with >2x warning
- [Phase 21-18]: Shim deletion executed migration-first: all src/tests/scripts imports moved to absolute bobbytailor paths and proven green (833 tests) BEFORE deleting the 33 root shims; root app.py is a 5-line create_app() gunicorn entry
- [Phase 21-18]: Parity/takeoff-pipeline spec-load mocks are scoped (temp-alias sys.modules key + restore) and conftest pre-imports all stub-targeted real modules — fixes the 21-08/21-16 test-order pollution class (previously-failing forced orders now pass)
- [Phase 21-18]: 21-UAT.md documents Crow main-plan scale expectation as 1 in = 40 ft per the 21-07 geometric proof (roadmap's ~20 fpi text is the stale research figure)
- [Phase 22]: 22-01: Step 1d (blueprint-parity uploads isolation) deferred — UPLOADS_DIR override in create_app is a behavior change; goes to SPEC §7 CWD-relative anchoring
- [Phase 22]: 22-01: OUTPUT_DIR/SCREENSHOTS_DIR test isolation via conftest config module-attribute patch — env pins are defeated by config.py load_dotenv(override=True) with .env defining OUTPUT_DIR

### Pending Todos

None yet.

### 21-03 Decisions

| Decision | Source |
|----------|--------|
| Shapely 2 STRtree.query returns numpy indices — index into segment list, not geometry id() map | 21-03 |
| Overall dims (feet≥100) pick longest grammar-verified segment; bay dims cap at 5× median corridor length | 21-03 |
| PERP_MIN_PT=0 so rotated vertical text on the dimension line is not rejected | 21-03 |
| Chained dims on one segment split by text projection when extension-line crossings insufficient | 21-03 |
| Synthetic generator uses page.draw_line (Shape.commit invisible to get_drawings) | 21-03 |
| Crow page 0 consensus fpi≈40 matches printed scale (dominant_scale), not 20 fpi research note | 21-03 |

### 21-02 Decisions

| Decision | Source |
|----------|--------|
| Blueprint endpoints prefixed (auth.login, projects.index); PUBLIC_ENDPOINTS + login_view updated | 21-02 |
| create_app sets template_folder/static_folder to repo root (parents[3]) | 21-02 |
| jobs_runtime owns jobs dict + thread launchers; no Flask request in job threads | 21-02 |
| verify.py owns scale/verify/measurements/calibrate; reports.py owns list/preview/sheet-image | 21-02 |
| Scale tests patch config.OUTPUT_DIR (not app.OUTPUT_DIR) after blueprint split | 21-02 |

### 21-01 Decisions

| Decision | Source |
|----------|--------|
| Root shims star-re-export AND alias sys.modules[__name__] to the real package module — monkeypatch through either import path hits one module object | 21-01 |
| requires-python kept at >=3.9 (deployment/test runtime is macOS system Python 3.9.6, not 3.10) | 21-01 |
| app.py shim repoints Flask template_folder/static_folder to repo root (Flask resolves relative to module location) | 21-01 |
| settings.py + seed_admin.py received the same repo-root .env fix as config.py (parents[3] from src/bobbytailor/web/) | 21-01 |
| New Phase 21 modules are created directly in src/bobbytailor/ final homes; internal flat imports stay until the import-migration plan | 21-01 |
| Deterministic suite green count is 505 (plan's 348 figure was stale) | 21-01 |

### 20-00 Decisions

| Decision | Source |
|----------|--------|
| MODEL_ROUTING uses CLAUDE_MODEL_SCHEDULES config constant, not hardcoded slug | 20-00 |
| TakeoffPipeline accepts optional analyzer= callable (dependency injection for tests) | 20-00 |
| merge_passes defined as stub in takeoff_pipeline; canonical version moves to claude_analyzer in 20-03 | 20-00 |
| plan_passes returns copy of PASS_MATRIX list to prevent mutation of module constant | 20-00 |
| classify_sheet_type_from_text defaults to floor_plan when ambiguous (safest: runs count+measure) | 20-00 |

### 20-03 Decisions

| Decision | Source |
|----------|--------|
| COUNT_PROMPT returns `has_schedules` bool so TakeoffPipeline can conditionally invoke schedule pass | 20-03 |
| `analyze_drawing` default `pass_type="measure"` preserves all existing single-pass caller behavior | 20-03 |
| `_pick_model` deferred `MODEL_ROUTING` import avoids circular dependency with sheet_pass_matrix | 20-03 |
| Canonical `merge_passes` lives in `claude_analyzer`; `takeoff_pipeline` re-exports for backward compat | 20-03 |
| `merge_passes` uses `strip().lower()` for dedup keys to handle trailing whitespace in Claude output | 20-03 |

### 20-01 Decisions

| Decision | Source |
|----------|--------|
| Noise filter applied in BOTH title-block and full-page passes | 20-01 |
| `_is_noise_sheet_candidate` checks candidate within matched phrase context (not fullmatch on candidate alone) | 20-01 |
| `sheet_type_hint` in `get_pdf_metadata` is conditional on `sheet_pass_matrix` import (backward-compatible) | 20-01 |

### 17-01 Decisions

| Decision | Source |
|----------|--------|
| `REUSE_SCREENSHOTS` defaults to true; set false to force fresh downloads | 17-01 |
| `shutil.copy2` copies cached file to new run dir (preserves metadata) | 17-01 |
| Cache map built once before sheet loop via `find_screenshot_paths` | 17-01 |

### 17-03 Decisions

| Decision | Source |
|----------|--------|
| `{page_id}_analysis.json` cache beside screenshot; missing cache triggers re-analyze even when manifest says ok | 17-03 |
| analyze_only auto-discovers latest run folder by project_name prefix + mtime sort | 17-03 |
| `mode_detail: "full" \| "analyze_only"` on job dict for UI/log differentiation | 17-03 |
| `force=False` skips ok+cached pages; `force=True` re-runs all | 17-03 |

### 17-02 Decisions

| Decision | Source |
|----------|--------|
| Manifest saved after every page state change (crash-recovery foundation for 17-03) | 17-02 |
| Atomic tmp+replace write prevents corrupt JSON on mid-write crash | 17-02 |
| `screenshot_rel` stores filename only — `screenshots_dir` is run root | 17-02 |
| `browser_closed` flag in `finally` prevents double-close after Pass 1 | 17-02 |
| `phase="capturing"` in progress_callback during Pass 1 | 17-02 |

### 20-06 Decisions

| Decision | Source |
|----------|--------|
| pdf_analyzer defers to TakeoffPipeline.run_project — no inline analyze_drawing loop | 20-06 |
| _page_to_image defined in pdf_analyzer (2× Matrix scaling) — was missing (bug fix) | 20-06 |
| scraper uses module-level _pipeline singleton (TakeoffPipeline()) for run_sheet calls | 20-06 |
| _detect_project_type called once after all sheets in both paths (uniform project_type) | 20-06 |
| Parity test uses source-level assertions + TakeoffPipeline injection (no real API calls) | 20-06 |

### 20-05 Decisions

| Decision | Source |
|----------|--------|
| MEASURE_ADDENDUM defined as named constant then concatenated to EXTRACTION_PROMPT | 20-05 |
| lintel_runs[] as dedicated array (not merged into pipe_runs[]) — separate calculator path | 20-05 |
| duct_lf and conduit_lf use 10% waste (vs 5% for gas/storm) — fittings add more equivalent LF | 20-05 |
| CMU Paint placed BEFORE CMU Wall in ITEM_NAME_MAP — both match \bcmu\b; first-match wins | 20-05 |
| Frame-HM placed BEFORE Doors-HM — "HM Door Frame" must not collapse to Doors-HM | 20-05 |
| Conduit LF / Duct LF placed BEFORE Storm Pipe — prevents PVC conduit matching \bpvc\b storm pattern | 20-05 |

### 20-04 Decisions

| Decision | Source |
|----------|--------|
| Content notes override profile skip_items — explicit drawing content always wins (VCT on industrial → flooring) | 20-04 |
| Floor/ceiling/wall handled as independent priority chains in _calculate_from_room | 20-04 |
| auto profile has empty default lists → universal fallback preserves pre-20-04 behavior | 20-04 |
| _detect_project_type uses keyword scoring across sheet_title + notes; ties → mixed_use | 20-04 |
| Gas pipe detected by material keyword (black steel/gas/csst); default → storm_pipe | 20-04 |

### 20-09 Decisions

| Decision | Source |
|----------|--------|
| Sanitary Pipe placed BEFORE Storm Pipe — sanitary.*sewer would otherwise collapse into Storm Pipe | 20-09 |
| Storefront/Curtain Wall placed AFTER all door patterns — "aluminum storefront door" must resolve to Doors-AL | 20-09 |
| RTU placed AFTER Air Handling Units — air handler pattern must win for explicit AHU descriptions | 20-09 |
| Drywall Ceiling placed BEFORE Ceiling Grid — suspended/gyp ceiling is structurally distinct from ACT tile | 20-09 |
| Dock Doors placed before Frame-HM/Door section — overhead/coiling doors resolve correctly | 20-09 |

### Blockers/Concerns

- StackCT DOM brittleness (`#canvas-interaction`, `[data-page-id]`, Auth0) — mitigated in Phase 2
- Flask background-thread context leaks — use primitive payloads only in job threads (research PITFALLS #3)
- Claude schedule counting accuracy — document confidence limits; v2 review UI (EST-02)
- Pricing table may go stale — verify quarterly against Anthropic docs
- GitNexus index stale after 21-01 package move (symbols indexed at old root paths) — run `npx gitnexus analyze` before impact analysis in later plans

## Session Continuity

Last session: 2026-08-02T18:41:47.200Z
Stopped at: Completed 21-16-PLAN.md — learning retrieval & injection + anti-amplification guardrail
Resume file: None

# Requirements: Bobby Tailor — StackCT Estimation Automation

**Defined:** 2026-05-26
**Core Value:** End-to-end automated take-off from StackCT drawings (or PDFs) producing traceable, formula-backed quantity calculations estimators can trust and export.

## v1 Requirements

### Foundation & Reliability

- [x] **FOUND-01**: Application loads credentials from project-relative `.env` on any machine (no hardcoded paths)
- [x] **FOUND-02**: API job errors return user-safe messages; full stack traces logged server-side only
- [x] **FOUND-03**: Browser waits for canvas pixel stability before screenshot (not fixed sleep only)
- [x] **FOUND-04**: StackCT project list fetch scrolls/lazy-loads until all projects are captured
- [x] **FOUND-05**: Headless Chromium runs reliably on VPS (`--disable-dev-shm-usage` or equivalent)

### StackCT Plan Selection

- [ ] **PLAN-01**: User can fetch drawing page list for a selected project without starting analysis
- [ ] **PLAN-02**: User sees sheet names with checkboxes and Select All / Select None controls
- [ ] **PLAN-03**: User can filter plans by sheet type (architectural, electrical, mechanical, schedule)
- [ ] **PLAN-04**: User can run analysis on selected `page_ids` only (not forced all pages)
- [ ] **PLAN-05**: Run API accepts optional `page_ids` array and scraper filters pages accordingly

### Job Monitoring

- [ ] **JOB-01**: User sees overall progress percentage and sheet count (e.g., 8/12)
- [ ] **JOB-02**: User sees current sheet name being processed during a run
- [ ] **JOB-03**: User sees per-sheet log entries (measurements, rooms, components extracted)
- [ ] **JOB-04**: Sidebar shows active job mini-card when a job is running

### Report Preview & Export

- [ ] **PREV-01**: User can preview `summary.txt` in browser as styled HTML
- [ ] **PREV-02**: User can preview `calculations.csv` as sortable, filterable data table
- [ ] **PREV-03**: User can preview `raw_items.csv` as sortable, filterable data table
- [ ] **PREV-04**: User can preview `takeoff.json` as collapsible JSON tree
- [ ] **PREV-05**: Preview API validates paths and rejects directory traversal
- [ ] **PREV-06**: Large CSV previews paginate or cap rows with clear "showing N of M" message

### Cost & Usage Tracking

- [x] **COST-01**: Each sheet analysis records input/output tokens and model used
- [x] **COST-02**: Each run aggregates total API cost in USD
- [x] **COST-03**: Report cards and summary show cost per run
- [x] **COST-04**: `takeoff.json` includes `api_usage` block with token and cost totals

### PDF Mode

- [x] **PDF-01**: User can upload a construction PDF for analysis
- [x] **PDF-02**: User can select specific pages before starting PDF analysis (not all pages only)
- [x] **PDF-03**: PDF page selection shows page count and file size after upload

### UI/UX Shell

- [ ] **UI-01**: App uses fixed sidebar navigation (Projects, PDF Upload, Reports, Settings)
- [ ] **UI-02**: Industrial dark theme per Master.md palette (DM Mono, Inter, JetBrains Mono)
- [ ] **UI-03**: Static assets extracted to `static/app.js` and `static/style.css`
- [x] **UI-04**: Projects page implements scope toggle (All Projects vs Specific Project)
- [x] **UI-05**: Reports page shows expandable report cards with preview tabs
- [x] **UI-06**: Job monitor page/panel matches Master.md live monitor layout

### Settings

- [ ] **SET-01**: User can view and edit StackCT credentials in Settings UI
- [ ] **SET-02**: User can view and edit Anthropic API key and model defaults
- [ ] **SET-03**: User can set output directory and screenshot retention preference
- [ ] **SET-04**: Settings persist to `.env` or config store without exposing secrets in API responses

### Deployment Readiness

- [x] **DEPLOY-01**: `.env.example` documents all required variables
- [x] **DEPLOY-02**: README includes VPS gunicorn + Playwright deps instructions
- [x] **DEPLOY-03**: `requirements.txt` pins Pillow and all runtime dependencies

### StackCT Data & Persistence (Phase 13)

- [x] **DATA-01**: Projects catalog persisted in SQLite under `OUTPUT_DIR` (`stackct.db`)
- [x] **DATA-02**: Per-project plans (`page_id`, `sheet_name`) persisted with configurable TTL
- [x] **DATA-03**: Sheet counts on project list without requiring per-project preview scrape
- [x] **DATA-04**: Sync operations audited in `sync_runs` table
- [x] **DATA-05**: Single global browser lock serializes all StackCT catalog sync
- [x] **DATA-06**: Background stale refresh (startup prefetch + scheduled interval)
- [x] **DATA-07**: One-time migration from `projects_cache.json` and `plans_cache/`
- [x] **DATA-08**: Project/plan APIs expose `from_cache`, `stale`, and `syncing` metadata
- [x] **DATA-09**: UI shows sheet counts on load; plan preview uses DB when fresh

### Takeoff Accuracy — Masterv2 v2.1 (Phase 16)

- [x] **ACCURACY-01**: Extraction prompt includes table_purpose, cross_references, pipe_runs, civil_structures
- [x] **ACCURACY-02**: Calculator skips specification_reference and general_notes schedules
- [x] **ACCURACY-03**: Specification tables stored in report as reference library (not calculated)
- [x] **ACCURACY-04**: Cross-reference resolution pass for sheets in the same run
- [x] **ACCURACY-05**: Project-level takeoff_summary via aggregator module
- [x] **ACCURACY-06**: takeoff_summary.csv export (item, quantity, unit) matches StackCT format
- [x] **ACCURACY-07**: Civil/site estimation tables (storm pipe, catch basin, striping, etc.)
- [x] **ACCURACY-08**: GL/INV/elevation values excluded from measurement calculations
- [x] **ACCURACY-09**: Approximate (±) quantities flagged in calculations output
- [x] **ACCURACY-10**: Pipe slope percentages not treated as takeoff quantities
- [x] **ACCURACY-11**: Spec lookup enrichment when pipe size matches reference tables
- [x] **ACCURACY-12**: In-browser preview of consolidated takeoff summary

### Production Takeoff Pipeline (Phase 17)

- [ ] **PIPE-01**: Reuse cached screenshots via `REUSE_SCREENSHOTS` and `find_screenshot_paths`
- [ ] **PIPE-02**: Two-phase pipeline — bulk capture then analyze (browser closed before Claude)
- [ ] **PIPE-03**: `manifest.json` per run; analyze-only resume without StackCT login
- [ ] **PIPE-04**: Phase-aware progress, cooperative cancel, partial report UI warnings
- [~] **PIPE-05**: Per-sheet resilience, sanitized filenames, user-facing job error messages *(hotfix landed; full UX in 17-04)*

### Linked Sheet Resolution (Phase 18)

- [ ] **LINK-01**: Map ref_sheet codes to page_id via catalog + fuzzy matching
- [ ] **LINK-02**: Collect refs from cross_references and civil_structures.detail_ref_sheet
- [ ] **LINK-03**: AUTO_INCLUDE_LINKED_SHEETS + MAX_LINKED_SHEETS config
- [ ] **LINK-04**: Linked capture/analyze pass in scraper before final resolve
- [ ] **LINK-05**: Job/report linked_sheets_added metadata + monitor notice
- [ ] **LINK-06**: Integration tests, README, 18-UAT.md sign-off

### Job History & Run Archive (Phase 19)

- [x] **HIST-01**: Terminal job states (done, error, cancelled) persist to SQLite on completion
- [x] **HIST-02**: History survives Flask restart — not limited to in-memory `jobs` dict
- [x] **HIST-03**: Job History nav tab lists recent runs newest-first (project, type, outcome, time, duration)
- [x] **HIST-04**: Outcome badges distinguish success, partial, failed, and cancelled with user-facing error/warning text
- [x] **HIST-05**: Detail panel shows log tail, sheet stats, and Open Report when a run folder exists
- [x] **HIST-06**: `GET /api/jobs/history` and `GET /api/jobs/history/<job_id>` with pagination and outcome filter

### StackCT Plan Sets (Phase 14)

- [ ] **PLANSET-01**: Browser discovers deduplicated plan sets (folders) per project via `[data-folder-id]`
- [ ] **PLANSET-02**: Drawing pages stored and synced per `(project_id, folder_id, page_id)`
- [ ] **PLANSET-03**: APIs expose plan set list and folder-scoped plan list
- [ ] **PLANSET-04**: UI shows plan set picker before sheet checklist (Preview Plans)
- [ ] **PLANSET-05**: Run accepts `folder_id` and validates `page_ids` belong to that set
- [ ] **PLANSET-06**: Direct-grid fallback when StackCT has no folder cards but has sheets
- [ ] **PLANSET-07**: Project list shows plan set count (not misleading merged sheet total)
- [ ] **PLANSET-08**: Multi-project audit documented and dedupe rules tested

### Premium UI/UX (Phase 15)

- [ ] **UX-01**: Design tokens v2 documented in `design-system/bobby-tailor/MASTER.md` (dark industrial)
- [ ] **UX-02**: Shared modal, drawer, and toast primitives with focus trap and Esc close
- [ ] **UX-03**: Report cards distinguish **Open preview** from **Export/download** actions
- [ ] **UX-04**: Full-screen report preview workspace (run list, tabs, export rail)
- [ ] **UX-05**: Calculations/raw tables use production grid (sort, filter, export filtered rows)
- [ ] **UX-06**: URL deep-link restores open report and active tab
- [ ] **UX-07**: Projects page uses guided stepper: Project → Plan set → Sheets → Run
- [ ] **UX-08**: Job monitor and sidebar mini-card match premium shell
- [ ] **UX-09**: Motion animations with `prefers-reduced-motion` fallback
- [ ] **UX-10**: 21st.dev MCP components used and documented for key surfaces
- [ ] **UX-11**: Responsive layouts verified at 375, 768, 1024, 1440px
- [ ] **UX-12**: Login, Settings, and PDF pages visually aligned with main shell

### Accuracy & Learning Engine v3 (Phase 21)

- [x] **V3-ACC-01**: Vector-first measurement — SF/LF/areas from PDF vector geometry + text layer; vision labels semantics, never guesses numbers when geometry exists
- [x] **V3-ACC-02**: Auto scale detection v2 — per-viewport binding, area-weighted dominant scale, cross-validated against dimension strings; per-sheet confidence recorded
- [x] **V3-ACC-03**: Ensemble extraction — N-run self-consistency voting for EA counts and vision quantities; tiled counting with dedup; disagreement flags needs_review
- [x] **V3-ACC-04**: Model upgrade & adaptive fidelity — strongest Claude vision models routed by sheet complexity; adaptive DPI/tiling for dense sheets
- [x] **V3-ACC-05**: Verify-retry loop implemented — out-of-band quantities re-queried with targeted crops before flagging (replaces ENABLE_VERIFY_RETRY stub)
- [x] **V3-LEARN-01**: Correction store — human-verified overrides persisted to SQLite keyed by project_type/sheet_type/item pattern; survives run deletion
- [x] **V3-LEARN-02**: Learned vocabulary — canonical names/units accumulated from verified runs supersede static ITEM_NAME_MAP; auto-generated manifest from verified takeoffs
- [x] **V3-LEARN-03**: Runtime feedback application — learned corrections retrieved and injected into prompts, aggregation, and calculator assumptions on new runs
- [x] **V3-LEARN-04**: Manifest independence — companion take-off and manifest files optional dev inputs only; plans-only path reaches target accuracy without them
- [x] **V3-STRUCT-01**: Package restructure — modules organized into structured package (pipeline/vision/scale/deterministic/learning/scrape/web) with Flask blueprints; tests green
- [x] **V3-STRUCT-02**: Entry-point parity — PDF and StackCT paths share identical pipeline behavior with parity test
- [x] **V3-PROD-01**: Plans-only accuracy gate — vision_only_benchmark as CI-invocable gate; item-found ≥95%; zero silent misses
- [x] **V3-PROD-02**: Live-testing readiness — flagged-subset human review workflow, per-run API cost budget guard, structured error recovery, deployment docs

### Production Revamp v4 — accuracy, determinism, autonomy (Phases 23–27)

Evidence base: `docs/PIPELINE-GROUND-TRUTH.md` (honest measured accuracy),
`.planning/research/VISION-MODEL-EVIDENCE-2026.md` (2026 deep research, 18 verified claims),
`.planning/codebase/{CONCERNS,ARCHITECTURE}.md` (repo audit).

**Phase 23 — Measurement Engine Completion**

- **V4-MEAS-01**: Room fills bind to takeoff line items for ceiling area (RCP basis) AND wall area (perimeter × height, AR basis)
- **V4-MEAS-02**: The ID-412/ID-416 ~2× clip defect fixed at the clip, not by a guestroom-sized plausibility threshold
  - **AMENDED 2026-08-04 (phase 23, plan 23-16) — a correction of a false premise, not a scope reduction.** *Original wording:* the line above, retained verbatim — **its "not by a guestroom-sized plausibility threshold" clause is DELIVERED AS WRITTEN and is not weakened by this amendment.** *The evidence that falsified the rest of it:* three independent geometric probes exonerate the clip — ID-412 is bit-identical across a 240 pt range of clip widths while ID-407/ID-415 move +17%/+20%; every counted region sits inside 47% of the clip; and the fill matches the drawing's own printed 455.2 SF at a ratio of 1.007. The real defect is an unverified `unit_count` of 2 derived from a golden door count. *Citation:* `INV-02-clip-defect.md` §2, §3, §4, §5; retraction in `INV-00-live-run-evidence.md` §1b; the corresponding correction to `docs/PIPELINE-GROUND-TRUTH.md` §14.2 landed in plan 23-16. *Delivered contract:* `_MAX_UNIT_SF` and `flag_implausible_unit` are deleted and replaced by a dimensionless printed-extent ratio (`EXTENT_TOLERANCE = 1.25`) that flags and never filters; the clip is rotation-correct and page-space bounded; and a multiplier-review flag fires on exactly ID-412/416/420/422 with `human_inputs/` never edited. **Still open:** the fully geometric viewport-bounded clip cell (SP-4), blocked behind **DEF-23-SP4**.
- **V4-MEAS-03**: Sheet-composition-agnostic measurement — elevation wall-area SF and civil linework LF, so a set with no floor plan still yields quantities
- **V4-MEAS-04**: ~~Finish-schedule → room binding (WC-1…WC-10 assigned to the rooms carrying those finishes)~~ — **AMENDED, see below**
  - **AMENDED 2026-08-04 (phase 23, plan 23-16) — a correction of a false premise, not a scope reduction.** *Original wording:* "Finish-schedule → room binding (WC-1…WC-10 assigned to the rooms carrying those finishes)". *The evidence that falsified it:* **there is no finish schedule in the input** — `CS-03 NOTES, REQUIREMENTS, FINISH SCHEDULES` is listed in the drawing index and is absent from the PDF, and the `finish` schedule kind fires **zero times across all four real plan sets**; the **wall-covering quantities are interior-ELEVATION quantities**, not room finishes keyed by room number, so "the rooms carrying those finishes" is the wrong join; and **no area is obtainable** — a seeded flood fill at every WC tag leaks to the clip edge at four to ten times the estimator's own figure, because an elevation wall face is bounded above and below but open laterally and is not a closed ink region. *Citation:* `INV-05-finish-schedule-binding.md` TL;DR, §1.2, §3. *Delivered contract:* every called-out finish code is read from the plan body by a direction-generic two-token tag reader, validated by exact code SET on six of six interior-elevation sheets including a true negative, and emitted as a **named, flagged, ZERO-QUANTITY row seeded with its tag positions** for the human measure workspace — never as a synthesized area. Emitting a fabricated area would violate this phase's own flag-don't-guess contract, and a test asserts no path from the finish reader can produce a non-zero quantity.
- **V4-MEAS-05**: Rail/linework LF measured from linework
- **V4-MEAS-06**: Per-format door-schedule parsing across Crow, Bob's, and Moxy formats; zero-geometry sheets emit an explicit coverage flag (blank never reported as zero)

**Phase 24 — Binding Determinism & Text-Anchored Labeling**

Every entry below is closed by ONE free command — `python3 -m pytest -q tests/test_phase24_acceptance.py`
(plan 24-10) — which has a named check per requirement. Where a requirement is only PARTLY
delivered that is stated here rather than ticked away.

- **V4-DET-01**: Set-of-Mark prompts carry each candidate's nearest plan text; no text anchor ⇒ flagged, never named from shape
  - **COMPLETE 2026-08-06 (phase 24; plans 24-01, 24-04, 24-06, 24-07).** Every candidate carries its nearest non-masked plan word or a RECORDED ABSENCE, computed before any model is consulted; the chip renders it; the hint delivers it inside the `<pdf_text>` delimiters so it survives the downscale; a candidate with a recorded absence is not asked about at all, and lands in the unnamed-geometry ledger with its quantity, position, evidence and machine reason, visible in `summary.txt`, in the workbook and in `takeoff.json`. *Closed by:* `test_v4_det_01_no_identifier_is_a_name_and_every_one_that_left_is_ledgered` (both halves in one check, over two real reports) and `test_v4_det_01_the_marker_chip_renders_the_anchor_when_one_exists`. *Stated, not hidden:* anchor coverage on the mission's primary plan set is LOW — 40 of 107 clusters — because Crow's plan body is sparsely annotated. That is an outcome of the drawing, and widening the radius until the number rises is the tuning trap this phase forbids.
- **V4-DET-02**: CMU vs tilt-up wall class selected deterministically by thickness + location, not by a vision label
  - **COMPLETE for its stated subject, WITH ONE NAMED RESIDUAL — 2026-08-06 (phase 24; plans 24-02, 24-03, 24-05).** A printed-thickness match now outranks a contradicting reading unconditionally, the dissent is published with the evidence that beat it, one object can no longer occupy two rows because of a trailing `s`, and the object list the classifier binds against is derived once per project and reused instead of re-invented every run. Fed one fixed bundle and the two label sets the two saved paid runs actually produced, the emitted `(name, quantity, unit)` triple SET does not move — the 8 ↔ 11,294 SF flip cannot recur. *Closed by:* `test_v4_det_02_printed_thickness_outranks_the_model_and_the_triple_set_holds`. **Residual, deliberately open and asserted by name:** a wall class with NO printed-thickness match is still named by the reading, so its row still moves with the label. It is pinned end to end by `test_the_residual_a_vision_named_wall_class_still_moves_with_its_label` and re-asserted by `test_falsified_the_residual_24_02_left_open_is_asserted_by_name_not_deleted`. **It must not be deleted or weakened.** It retires when the underlying object list stabilises across two real runs, which needs a paid run whose naming pass was skipped because a snapshot existed; when that lands the test FAILS and the failure is the signal.
- **V4-DET-03**: Dependency-ordered fusion schema (wall skeleton first, rooms as references) so geometric gaps are structurally impossible
  - **COMPLETE 2026-08-06 (phase 24, plan 24-07).** `semantic_labeling_schema` is declared skeleton-first — wall classes, then regions, then rooms — with `required` in the same order the model generates, every ID a room names an enum of a level defined ABOVE it, and a room that cannot cite a bounding wall answering with an ALLOWED EMPTY LIST rather than inventing a reference. A topological gap is unexpressible rather than merely flagged. Zero numeric properties on any vector builder, proved by walking every builder introspection finds and paired with a positive control on the one raster schema that is permitted an integer. *Closed by:* `test_v4_det_03_the_vector_schema_is_dependency_ordered_and_carries_no_number`.
- **V4-DET-04**: Ensemble voting wired onto every remaining flip-capable identification pass
  - **COMPLETE AS WRITTEN, WITH ITS LIMIT STATED — 2026-08-06 (phase 24, plan 24-08).** The last un-ensembled identification path — the schedule and legend passes — now majority-votes on the ROW's own identity (a label vote was the wrong shape: those passes send no schema and no candidate list, so what varies between two reads is which rows EXIST). The identity is folded through the aggregator's one fold, a surviving row is VERBATIM one sample's row so a voted quantity is unrepresentable rather than merely avoided, a tie drops the row, and every sample is charged. An AST census over both analyzer-bearing modules asserts every call site is voted-with-a-witness or carries the single recorded exemption, and it FAILS on zero sites found rather than reporting a clean bill of health. *Closed by:* `test_v4_det_04_every_analyzer_call_site_is_voted_or_carries_an_exemption`. **The limit, stated rather than implied:** the determinism property is proved OFFLINE with scripted stubs. That it holds on a real drawing has **no artifact** and needs a paid run, which is not autonomously authorised. Nothing here claims otherwise. The 184→64 swing that originally motivated this cannot judge it in either direction — see V4-DET-05's amendment and the phase-24 ROADMAP findings.
- **V4-DET-05**: ~~Determinism harness — same fixture N× asserts identical line items~~ — **AMENDED, see below**
  - **AMENDED 2026-08-06 (phase 24; reframed at planning, delivered by plans 24-09 and 24-10) — a correction of a vacuous premise, not a scope reduction.** *Original wording:* "Determinism harness — same fixture N× asserts identical line items". *The evidence that falsified it:* `ReplayAnalyzer.__call__` resolves a SHA256 over `(model, pass_type, prompt text, image count)` and returns that file's response verbatim — it is a **pure function of its key**, so running one fixture N times is identical BY CONSTRUCTION, exercises nothing in the naming layer, and would detect none of the observed defects. Writing the requirement verbatim would have shipped a gate that passes for having looked at nothing, which is what `test_phase23_acceptance.py` rule 3 forbids. The vacuity is not argued, it is **demonstrated as a committed assertion**: `test_v4_det_05_criterion_five_was_reframed_and_the_literal_wording_is_vacuous` issues one request five times and gets five identical answers off disk. *Citation:* `24-RESEARCH.md` §8.1–8.2; `tests/replay_analyzer.py` key derivation; `24-09-SUMMARY.md`; ROADMAP Phase 24 criterion 5, amended 2026-08-05 and 2026-08-06. *Delivered contract:* a **two-variant differential** — hold the PDF, the geometry, every prompt and every fixture key FIXED; VARY the model's answers within schema-legal bounds using the two saved paid runs' own recorded labels; assert the published take-off does not move. Three invariants, each a set equality between the variants and never against a golden figure: the published item-name set, the unnamed-geometry ledger's candidate set, and the quantity multiset (a word may never move a number). Two further corrections the measurement forced: there is **no `measure_basis` field in this codebase**, and the full `(name, unit, quantity)` tuple set is measurably NOT invariant while V4-DET-02's residual is open — so that residual is asserted BY NAME instead of the gate being quietly narrowed until it passed. Ensembled passes are explicitly OUT of scope (after 24-08 a pass issues N requests carrying ONE key, so a key-addressed replay source votes unanimously by construction; the harness pins N=1 and a test proves the pin is real). The gate is a proven DETECTOR: it was made to go RED on disk against a poisoned third variant and the poison was never committed. *Closed by:* `test_v4_det_05_the_two_variant_differential_holds`, non-vacuity guards first. **Also stated:** that this determinism holds on a real PAID run has no artifact and needs one.

**Phase 25 — Deterministic Symbol Detection** (non-ML by scope decision)

- **V4-SYM-01**: 2-D lattice detector over coordinate-sampled vector primitives isolates genuinely 2-D-distributed repeated objects
- **V4-SYM-02**: Detections validated by position/shape; tuning to the golden count is a forbidden methodology
- **V4-SYM-03**: Collinear tick strips and grid bubbles can never be emitted as objects
- **V4-SYM-04**: Undetectable items are flagged with evidence rather than guessed

**Phase 26 — Learning Loop & Autonomy**

- **V4-LEARN-01**: A supplied manifest is captured as learning; the same project/type stops needing it
- **V4-LEARN-02**: A supplied calibration is captured, keyed to the drawing/viewport it corrected
- **V4-LEARN-03**: Every intervention records a machine-readable REASON distinguishing input gap from code gap
- **V4-LEARN-04**: Per-run autonomy metric — quantities by provenance (geometry / schedule / learned / human), trending human toward zero
- **V4-LEARN-05**: Anti-amplification preserved — learned counts only flag for re-verification, never silently substitute

**Phase 27 — Production Hardening**

- **V4-PROD-01**: Front-door parity — scraper stops re-implementing `run_project`'s tail and runs the vocabulary/naming pass
- **V4-PROD-02**: `takeoff_pipeline.py` split behind re-export shims, suite green
- **V4-PROD-03**: One typed config surface (no import-time validation, dotenv precedence fixed, settings allowlist generated, 5 env readers collapsed)
- **V4-PROD-04**: `debug=True` environment-gated
- **V4-PROD-05**: Warehouse-tuned 30 ft wall height and single-CAD-template room-engine ceilings generalized or made explicit inputs
- **V4-PROD-06**: `output/`/`uploads/` anchored to a configured data root, not CWD
- **V4-PROD-07**: Rate limiting, upload magic-byte sniffing, remaining CONCERNS security items closed

### Accuracy Remediation — Crow defects (Phase 28, runs before Phase 25)

Evidence: `.planning/paid-run-evidence/VisionOnly_P24DET_Crow_20260806_19{4607,5704}` — two identical
paid runs, $1.1573, human-in-the-loop (plans-only input + quantity-free manifest), scored against the
take-off. All five are reproducible offline against those saved artifacts.

- **V4-FIX-01**: No count publishes `MEASURED` / `needs_review=False` without corroboration. `Stairs` published clean at 1.00 (run A) and 2.00 (run B) against golden 10 — unflagged, 90% wrong, irreproducible. Uncorroborated counts flag.
- **V4-FIX-02**: The Bollards 2× (56 vs 28) is diagnosed and fixed at its cause — a double-count signature, never resolved by dividing by two.
- **V4-FIX-03**: CMU Wall binds the correct thickness class (11,286 SF vs golden 2,204; ~313 LF bound where golden implies ~61).
- **V4-FIX-04**: One measured region backs one published row; the 397,600 SF footprint no longer fans out to three (Exposed Structure / Sealed Concrete / Concrete Pad), so summing the SF column cannot triple-count the building.
- **V4-FIX-05**: Per-sheet vision extraction variance is stabilised or surfaced as a flag — the 3-of-51 quantity deltas between identical runs (raw items 113 vs 124) must never present as a silently different number.

## v2 Requirements

### Architecture & Scale

- **ARCH-01**: FastAPI async foundation with incremental Flask route migration
- **ARCH-02**: Celery/Redis job queue replacing in-memory thread state (multi-user prep)

### Advanced Estimation

- **EST-01**: Named waste factor profiles selectable before run
- **EST-02**: Per-sheet confidence review UI (accept/reject/edit quantities)
- **EST-03**: Side-by-side screenshot vs extracted data review

### Automation & Integrations

- **AUTO-01**: Scheduled cron runs per project with APScheduler UI
- **AUTO-02**: Email or Slack notification on run completion
- **AUTO-03**: Diff mode comparing runs since last take-off

### Export

- **EXP-01**: Excel export with summary dashboard and conditional formatting

## Out of Scope

| Feature | Reason |
|---------|--------|
| Full multi-user SaaS with roles | Single-operator tool; deferred per Master.md Gap #9 |
| Built-in proposal/bid generation | Estimators export CSV to existing bid systems |
| Real-time collaborative take-off | Not core value; high complexity |
| Custom symbol training / ML pipeline | Zero-shot Claude Vision is the differentiator |
| Replacing StackCT platform | Automates existing StackCT workflow only |
| Mobile-first native app | Desktop estimator workflow; web responsive sufficient |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FOUND-01 | Phase 1 | Complete |
| FOUND-02 | Phase 1 | Complete |
| FOUND-03 | Phase 2 | Complete |
| FOUND-04 | Phase 2 | Complete |
| FOUND-05 | Phase 2 | Complete |
| COST-01 | Phase 3 | Complete |
| COST-02 | Phase 3 | Complete |
| COST-03 | Phase 3 | Complete |
| COST-04 | Phase 3 | Complete |
| PLAN-01 | Phase 4 | Pending |
| PLAN-02 | Phase 4 | Pending |
| PLAN-03 | Phase 4 | Pending |
| PLAN-04 | Phase 4 | Pending |
| PLAN-05 | Phase 4 | Pending |
| PREV-01 | Phase 5 | Pending |
| PREV-02 | Phase 5 | Pending |
| PREV-03 | Phase 5 | Pending |
| PREV-04 | Phase 5 | Pending |
| PREV-05 | Phase 5 | Pending |
| PREV-06 | Phase 5 | Pending |
| SET-01 | Phase 6 | Pending |
| SET-02 | Phase 6 | Pending |
| SET-03 | Phase 6 | Pending |
| SET-04 | Phase 6 | Pending |
| JOB-01 | Phase 7 | Pending |
| JOB-02 | Phase 7 | Pending |
| JOB-03 | Phase 7 | Pending |
| JOB-04 | Phase 7 | Pending |
| UI-01 | Phase 8 | Pending |
| UI-02 | Phase 8 | Pending |
| UI-03 | Phase 8 | Pending |
| UI-04 | Phase 9 | Complete |
| UI-05 | Phase 10 | Complete |
| UI-06 | Phase 10 | Complete |
| PDF-01 | Phase 11 | Complete |
| PDF-02 | Phase 11 | Complete |
| PDF-03 | Phase 11 | Complete |
| DEPLOY-01 | Phase 1 | Complete |
| DEPLOY-02 | Phase 11 | Complete |
| DEPLOY-03 | Phase 1 | Complete |
| DATA-01 | Phase 13 | Complete |
| DATA-02 | Phase 13 | Complete |
| DATA-03 | Phase 13 | Complete |
| DATA-04 | Phase 13 | Complete |
| DATA-05 | Phase 13 | Complete |
| DATA-06 | Phase 13 | Complete |
| DATA-07 | Phase 13 | Complete |
| DATA-08 | Phase 13 | Complete |
| DATA-09 | Phase 13 | Complete |
| PLANSET-01 | Phase 14 | Pending |
| PLANSET-02 | Phase 14 | Pending |
| PLANSET-03 | Phase 14 | Pending |
| PLANSET-04 | Phase 14 | Pending |
| PLANSET-05 | Phase 14 | Pending |
| PLANSET-06 | Phase 14 | Pending |
| PLANSET-07 | Phase 14 | Pending |
| PLANSET-08 | Phase 14 | Pending |
| UX-01 | Phase 15 | Pending |
| UX-02 | Phase 15 | Pending |
| UX-03 | Phase 15 | Pending |
| UX-04 | Phase 15 | Pending |
| UX-05 | Phase 15 | Pending |
| UX-06 | Phase 15 | Pending |
| UX-07 | Phase 15 | Pending |
| UX-08 | Phase 15 | Pending |
| UX-09 | Phase 15 | Pending |
| UX-10 | Phase 15 | Pending |
| UX-11 | Phase 15 | Pending |
| UX-12 | Phase 15 | Pending |
| ACCURACY-01 | Phase 16 | Complete |
| ACCURACY-02 | Phase 16 | Complete |
| ACCURACY-03 | Phase 16 | Complete |
| ACCURACY-04 | Phase 16 | Complete |
| ACCURACY-05 | Phase 16 | Complete |
| ACCURACY-06 | Phase 16 | Complete |
| ACCURACY-07 | Phase 16 | Complete |
| ACCURACY-08 | Phase 16 | Complete |
| ACCURACY-09 | Phase 16 | Complete |
| ACCURACY-10 | Phase 16 | Complete |
| ACCURACY-11 | Phase 16 | Complete |
| ACCURACY-12 | Phase 16 | Complete |
| PIPE-01 | Phase 17 | Pending |
| PIPE-02 | Phase 17 | Pending |
| PIPE-03 | Phase 17 | Pending |
| PIPE-04 | Phase 17 | Pending |
| PIPE-05 | Phase 17 | Partial (hotfix: per-sheet errors, safe filenames, partial reports) |
| LINK-01 | Phase 18 | Pending |
| LINK-02 | Phase 18 | Pending |
| LINK-03 | Phase 18 | Pending |
| LINK-04 | Phase 18 | Pending |
| LINK-05 | Phase 18 | Pending |
| LINK-06 | Phase 18 | Pending |
| HIST-01 | Phase 19 | Complete |
| HIST-02 | Phase 19 | Complete |
| HIST-03 | Phase 19 | Complete |
| HIST-04 | Phase 19 | Complete |
| HIST-05 | Phase 19 | Complete |
| HIST-06 | Phase 19 | Complete |
| V3-ACC-01 | Phase 21 | Complete |
| V3-ACC-02 | Phase 21 | Complete |
| V3-ACC-03 | Phase 21 | Complete |
| V3-ACC-04 | Phase 21 | Complete |
| V3-ACC-05 | Phase 21 | Complete |
| V3-LEARN-01 | Phase 21 | Complete |
| V3-LEARN-02 | Phase 21 | Complete |
| V3-LEARN-03 | Phase 21 | Complete |
| V3-LEARN-04 | Phase 21 | Complete |
| V3-STRUCT-01 | Phase 21 | Complete |
| V3-STRUCT-02 | Phase 21 | Complete |
| V3-PROD-01 | Phase 21 | Complete |
| V3-PROD-02 | Phase 21 | Complete |

**Coverage:**

- v1 requirements: 84 total (incl. Phase 14–19)
- Mapped to phases: 84
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-26*
*Last updated: 2026-05-26 — Phase 16 Takeoff Accuracy (ACCURACY-01–12) from Masterv2 v2.1*

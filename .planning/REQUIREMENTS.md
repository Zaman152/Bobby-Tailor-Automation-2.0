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

- [ ] **V3-ACC-01**: Vector-first measurement — SF/LF/areas from PDF vector geometry + text layer; vision labels semantics, never guesses numbers when geometry exists
- [ ] **V3-ACC-02**: Auto scale detection v2 — per-viewport binding, area-weighted dominant scale, cross-validated against dimension strings; per-sheet confidence recorded
- [ ] **V3-ACC-03**: Ensemble extraction — N-run self-consistency voting for EA counts and vision quantities; tiled counting with dedup; disagreement flags needs_review
- [ ] **V3-ACC-04**: Model upgrade & adaptive fidelity — strongest Claude vision models routed by sheet complexity; adaptive DPI/tiling for dense sheets
- [ ] **V3-ACC-05**: Verify-retry loop implemented — out-of-band quantities re-queried with targeted crops before flagging (replaces ENABLE_VERIFY_RETRY stub)
- [ ] **V3-LEARN-01**: Correction store — human-verified overrides persisted to SQLite keyed by project_type/sheet_type/item pattern; survives run deletion
- [ ] **V3-LEARN-02**: Learned vocabulary — canonical names/units accumulated from verified runs supersede static ITEM_NAME_MAP; auto-generated manifest from verified takeoffs
- [ ] **V3-LEARN-03**: Runtime feedback application — learned corrections retrieved and injected into prompts, aggregation, and calculator assumptions on new runs
- [ ] **V3-LEARN-04**: Manifest independence — companion take-off and manifest files optional dev inputs only; plans-only path reaches target accuracy without them
- [ ] **V3-STRUCT-01**: Package restructure — modules organized into structured package (pipeline/vision/scale/deterministic/learning/scrape/web) with Flask blueprints; tests green
- [ ] **V3-STRUCT-02**: Entry-point parity — PDF and StackCT paths share identical pipeline behavior with parity test
- [ ] **V3-PROD-01**: Plans-only accuracy gate — vision_only_benchmark as CI-invocable gate; item-found ≥95%; zero silent misses
- [ ] **V3-PROD-02**: Live-testing readiness — flagged-subset human review workflow, per-run API cost budget guard, structured error recovery, deployment docs

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
| V3-ACC-01 | Phase 21 | Pending |
| V3-ACC-02 | Phase 21 | Pending |
| V3-ACC-03 | Phase 21 | Pending |
| V3-ACC-04 | Phase 21 | Pending |
| V3-ACC-05 | Phase 21 | Pending |
| V3-LEARN-01 | Phase 21 | Pending |
| V3-LEARN-02 | Phase 21 | Pending |
| V3-LEARN-03 | Phase 21 | Pending |
| V3-LEARN-04 | Phase 21 | Pending |
| V3-STRUCT-01 | Phase 21 | Pending |
| V3-STRUCT-02 | Phase 21 | Pending |
| V3-PROD-01 | Phase 21 | Pending |
| V3-PROD-02 | Phase 21 | Pending |

**Coverage:**
- v1 requirements: 84 total (incl. Phase 14–19)
- Mapped to phases: 84
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-26*
*Last updated: 2026-05-26 — Phase 16 Takeoff Accuracy (ACCURACY-01–12) from Masterv2 v2.1*

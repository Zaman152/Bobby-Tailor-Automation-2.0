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

### Export & Auth

- **EXP-01**: Excel export with summary dashboard and conditional formatting
- **AUTH-01**: Simple password protection or HTTP basic auth for production

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

**Coverage:**
- v1 requirements: 35 total
- Mapped to phases: 35
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-26*
*Last updated: 2026-05-26 after roadmap traceability (11 phases, comprehensive depth)*

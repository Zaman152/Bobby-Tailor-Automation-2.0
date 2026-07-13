# Phase 19 Research: Job History & Run Archive

## Problem

Operators lose visibility when:
- Flask restarts (in-memory `jobs` cleared)
- They navigate away from Job Monitor after completion
- They need to compare yesterday's failed run vs today's partial success

Reports exist on disk under `output/<Project>_<timestamp>/` but there is no index tying **job_id → outcome → report folder**.

## Recommended architecture

### Persistence: `job_store.py`

New module (or extend `stackct_store.py` — prefer **separate module** to keep concerns clean, same SQLite file `data/stackct.db` or `config.JOB_DB_PATH` defaulting to same path).

**Table `job_runs`:**

| Column | Type | Notes |
|--------|------|-------|
| job_id | TEXT PK | 8-char uuid prefix |
| job_type | TEXT | stackct \| pdf |
| project_name | TEXT | |
| status | TEXT | done \| error \| cancelled \| partial* |
| outcome | TEXT | success \| partial \| failed \| cancelled — derived for UI |
| error_message | TEXT | user-facing |
| warning_message | TEXT | partial/cancel |
| mode | TEXT | all \| specific \| analyze_only |
| mode_detail | TEXT | full \| analyze_only |
| started_at | TEXT ISO | |
| finished_at | TEXT ISO | |
| duration_sec | REAL | |
| sheets_total | INTEGER | |
| sheets_succeeded | INTEGER | |
| sheets_failed | INTEGER | |
| linked_sheets_added | INTEGER | |
| progress_final | INTEGER | 0-100 |
| run_folder | TEXT | from result `_run_folder_name` |
| report_json_path | TEXT | optional relative path |
| log_tail_json | TEXT | JSON array last 80 log lines |
| meta_json | TEXT | optional: page_ids count, folder_id |

\*Store terminal `status` from job dict; compute `outcome`:
- `done` + no warning + not partial → success
- `done` + (warning or result.partial) → partial
- `error` → failed
- `cancelled` → cancelled

**Hook points:**
- `_finalize_stackct_job` — always call `job_store.save_job_run(jobs[job_id])`
- `_pdf_job` except block — same on done/error
- Optional: save `queued`→`running` transition (skip for v1 — only terminal states)

**Retention:** `JOB_HISTORY_RETENTION_DAYS=90` env, prune on insert (optional plan 19-04).

### API

| Route | Purpose |
|-------|---------|
| `GET /api/jobs/history?limit=50&offset=0&status=` | Paginated list, summary fields only |
| `GET /api/jobs/history/<job_id>` | Full detail including log_tail, sheet stats |
| `GET /api/jobs/active` | Keep existing — merge doc: active = memory, history = DB |

Auth: same `@login_required` as other API routes.

### UI: History tab

**Nav:** New permanent item `Job History` (always visible), distinct from ephemeral Job Monitor.

**Page `page-job-history`:**
- Filter chips: All \| Success \| Partial \| Failed \| Cancelled
- Table columns: Time, Project, Type, Status, Sheets, Duration, Actions
- Status badges reuse monitor CSS (`badge-done`, `badge-error`, `badge-cancelled`, new `badge-partial`)
- Row expand or slide panel: error/warning text, linked sheets count, log tail (monospace)
- Actions: "Open Report" (if run_folder exists → navigate reports workspace or download JSON link), "View in Monitor" (read-only replay from history API for completed jobs)

**Empty state:** "No job history yet — run a takeoff from Projects."

### Files to touch

- **New:** `job_store.py`, `tests/test_job_store.py`, `tests/test_job_history_api.py`
- **Modify:** `app.py`, `config.py`, `.env.example`, `templates/index.html`, `static/app.js`, `static/style.css`, `README.md`

### Testing

- Unit: save/load round-trip, outcome derivation
- API: list returns newest first, 404 on unknown id
- Integration: mock finalize → row in DB

### UX notes

- Show **outcome** label prominently ("Partial — 42/45 sheets, 3 failed")
- Error column: truncate with expand
- Timestamp in local timezone in UI (ISO from server)
